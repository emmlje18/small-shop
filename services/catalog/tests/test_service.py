"""CatalogService rules against a real SQL Server database (ported from Assignment 1)."""

import pytest

from catalog.service import CatalogService

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"0" * 32


@pytest.fixture
def service(db):
    return CatalogService(db)


@pytest.fixture
def product_id(service):
    return service.add_product("Keychain", "A small keychain", 500)


def test_add_product_trims_and_saves(service):
    """A new product is stored with its trimmed name and is active."""
    product_id = service.add_product("  Keychain  ", "  small  ", 500)
    product = service.get_product(product_id)
    assert product["name"] == "Keychain"
    assert product["description"] == "small"
    assert product["is_active"] is True
    assert product["has_image"] is False


@pytest.mark.parametrize(
    ("name", "price", "message"),
    [("   ", 500, "name"), ("Keychain", -1, "Price"), ("Keychain", True, "Price"), ("Keychain", 1.5, "Price")],
)
def test_add_product_rejects_invalid_details(service, name, price, message):
    """Blank names, negative or non-integer prices are refused before SQL runs."""
    with pytest.raises(ValueError, match=message):
        service.add_product(name, "", price)
    assert service.list_products() == []


def test_variant_stock_must_be_nonnegative(service, product_id):
    with pytest.raises(ValueError, match="Stock"):
        service.add_variant(product_id, "Blue", -1)


def test_add_variant_rejects_blank_label(service, product_id):
    with pytest.raises(ValueError, match="label"):
        service.add_variant(product_id, "   ", 1)


def test_update_product_saves_new_details(service, product_id):
    assert service.update_product(product_id, "  Big keychain ", " larger ", 900) is True
    product = service.get_product_for_admin(product_id)
    assert (product["name"], product["description"], product["price_cents"]) == ("Big keychain", "larger", 900)


def test_update_product_rejects_invalid_details_and_keeps_old_values(service, product_id):
    with pytest.raises(ValueError, match="Price"):
        service.update_product(product_id, "Keychain", "", -5)
    assert service.get_product_for_admin(product_id)["price_cents"] == 500


def test_update_product_reports_missing_product(service):
    assert service.update_product(999999, "Keychain", "", 500) is False


def test_deactivated_product_is_hidden_and_cannot_be_bought(service, product_id):
    """Soft delete: customers no longer see it, but admins still can."""
    variant_id = service.add_variant(product_id, "Blue", 3)
    assert service.deactivate_product(product_id) is True
    assert service.list_products() == []
    assert service.get_product(product_id) is None
    assert service.get_variant_snapshot(variant_id) is None
    assert service.get_product_for_admin(product_id)["is_active"] is False
    assert service.deactivate_product(product_id) is False


def test_update_variant_changes_label_and_stock(service, product_id):
    variant_id = service.add_variant(product_id, "Blue", 3)
    assert service.update_variant(product_id, variant_id, "Navy", 7) is True
    assert service.list_variants(product_id) == [
        {"id": variant_id, "product_id": product_id, "option_label": "Navy", "stock": 7}
    ]


def test_option_cannot_be_changed_through_another_product(service, product_id):
    other_id = service.add_product("Mug", "", 800)
    variant_id = service.add_variant(product_id, "Blue", 3)
    assert service.update_variant(other_id, variant_id, "Hacked", 0) is False
    assert service.remove_variant_from_sale(other_id, variant_id) is False


def test_remove_variant_from_sale_keeps_the_row(service, product_id):
    """Stock goes to 0 but the id stays valid for saved orders."""
    variant_id = service.add_variant(product_id, "Blue", 3)
    assert service.remove_variant_from_sale(product_id, variant_id) is True
    assert service.get_variant_snapshot(variant_id)["stock"] == 0


def test_bad_ids_are_refused_without_touching_the_database(service):
    assert service.get_product(0) is None
    assert service.get_product_for_admin(-1) is None
    assert service.deactivate_product("1") is False
    assert service.remove_variant_from_sale(0, 1) is False
    assert service.decrement_stock(1, 0) is False
    assert service.restore_stock(0, 1) is None


def test_snapshot_has_what_orders_needs(service, product_id):
    variant_id = service.add_variant(product_id, "Blue", 2)
    assert service.get_variant_snapshot(variant_id) == {
        "variant_id": variant_id, "product_name": "Keychain",
        "option_label": "Blue", "unit_price_cents": 500, "stock": 2,
    }


def test_decrement_refuses_more_than_available(service, product_id):
    """The conditional UPDATE never lets stock go negative."""
    variant_id = service.add_variant(product_id, "Blue", 1)
    assert service.decrement_stock(variant_id, 2) is False
    assert service.get_variant_snapshot(variant_id)["stock"] == 1


def test_two_buyers_cannot_both_take_the_last_unit(service, product_id):
    variant_id = service.add_variant(product_id, "Blue", 1)
    assert service.decrement_stock(variant_id, 1) is True
    assert service.decrement_stock(variant_id, 1) is False
    assert service.get_variant_snapshot(variant_id)["stock"] == 0


def test_decrement_and_restore(service, product_id):
    variant_id = service.add_variant(product_id, "Blue", 2)
    assert service.decrement_stock(variant_id, 2) is True
    service.restore_stock(variant_id, 2)
    assert service.get_variant_snapshot(variant_id)["stock"] == 2


def test_image_is_stored_and_read_back(service, product_id):
    variant_id = service.add_variant(product_id, "Blue", 1)
    assert service.set_product_image(product_id, "photo.PNG", PNG_BYTES) is True
    image = service.get_product_image(product_id)
    assert image == {"image_data": PNG_BYTES, "image_content_type": "image/png"}
    assert service.get_variant_image(variant_id) == image
    assert service.get_product(product_id)["has_image"] is True


@pytest.mark.parametrize(
    ("filename", "data", "message"),
    [("notes.txt", PNG_BYTES, "Allowed"), ("noextension", PNG_BYTES, "Allowed"),
     ("photo.png", b"", "empty"), ("photo.png", b"0" * (5 * 1024 * 1024 + 1), "5 MB")],
)
def test_invalid_images_are_refused(service, product_id, filename, data, message):
    with pytest.raises(ValueError, match=message):
        service.set_product_image(product_id, filename, data)
    assert service.get_product_image(product_id) is None
