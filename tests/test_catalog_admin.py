"""Tests for the admin catalog actions: editing, deactivating, and option changes."""

import pytest

from app.catalog.service import CatalogService


@pytest.fixture
def service(database_path):
    """Provide a real catalog service backed by a temporary SQLite file."""
    return CatalogService(database_path)


@pytest.fixture
def product_id(service):
    """Create one product that each test can edit."""
    return service.add_product("Keychain", "A small keychain", 500, "keychain.png")


def test_update_product_saves_new_details(service, product_id):
    """Editing a product stores the trimmed name, description, price, and image."""
    assert service.update_product(
        product_id, "  Big keychain  ", "  Now larger  ", 900, "big.png"
    ) is True

    product = service.get_product_for_admin(product_id)
    assert product["name"] == "Big keychain"
    assert product["description"] == "Now larger"
    assert product["price_cents"] == 900
    assert product["image_path"] == "big.png"


@pytest.mark.parametrize(
    ("name", "price_cents", "message"),
    [("   ", 500, "name"), ("Keychain", -1, "Price"), ("Keychain", True, "Price")],
)
def test_update_product_rejects_invalid_details(
    service, product_id, name, price_cents, message
):
    """Invalid edits are refused and the saved product is left unchanged."""
    with pytest.raises(ValueError, match=message):
        service.update_product(product_id, name, "", price_cents, None)

    product = service.get_product_for_admin(product_id)
    assert product["name"] == "Keychain"
    assert product["price_cents"] == 500


def test_update_product_reports_missing_product(service):
    """Editing an id that does not exist reports failure instead of crashing."""
    assert service.update_product(999, "Keychain", "", 500, None) is False


def test_deactivated_product_is_hidden_from_customers(service, product_id):
    """A removed product disappears from the shop and cannot be bought."""
    variant_id = service.add_variant(product_id, "Blue", 3)

    assert service.deactivate_product(product_id) is True

    assert service.list_products() == []
    assert service.get_product(product_id) is None
    assert service.get_variant_snapshot(variant_id) is None
    assert service.get_variant_image_path(variant_id) is None
    # The row is kept, so the admin can still see it and old orders keep their ids.
    assert service.get_product_for_admin(product_id)["is_active"] == 0


def test_deactivate_product_only_succeeds_once(service, product_id):
    """Removing an already removed or unknown product reports failure."""
    assert service.deactivate_product(product_id) is True
    assert service.deactivate_product(product_id) is False
    assert service.deactivate_product(999) is False
    assert service.deactivate_product(0) is False


def test_add_variant_rejects_blank_label(service, product_id):
    """An option needs a label such as a colour or size."""
    with pytest.raises(ValueError, match="label"):
        service.add_variant(product_id, "   ", 1)


def test_update_variant_changes_label_and_stock(service, product_id):
    """Editing an option saves its new label and stock level."""
    variant_id = service.add_variant(product_id, "Blue", 3)

    assert service.update_variant(product_id, variant_id, " Navy ", 7) is True

    assert service.list_variants(product_id) == [
        {"id": variant_id, "product_id": product_id, "option_label": "Navy", "stock": 7}
    ]


def test_update_variant_rejects_invalid_values(service, product_id):
    """Blank labels and negative stock are refused before SQLite is used."""
    variant_id = service.add_variant(product_id, "Blue", 3)

    with pytest.raises(ValueError, match="label"):
        service.update_variant(product_id, variant_id, "", 3)
    with pytest.raises(ValueError, match="Stock"):
        service.update_variant(product_id, variant_id, "Blue", -1)
    with pytest.raises(ValueError, match="Option id"):
        service.update_variant(product_id, 0, "Blue", 3)


def test_option_cannot_be_changed_through_another_product(service, product_id):
    """An option is only edited or removed through the product it belongs to."""
    other_product_id = service.add_product("Mug", "A mug", 1200)
    variant_id = service.add_variant(product_id, "Blue", 3)

    assert service.update_variant(other_product_id, variant_id, "Hacked", 99) is False
    assert service.remove_variant_from_sale(other_product_id, variant_id) is False

    assert service.list_variants(product_id)[0]["option_label"] == "Blue"
    assert service.list_variants(product_id)[0]["stock"] == 3


def test_remove_variant_from_sale_keeps_the_option_row(service, product_id):
    """Removing an option sets stock to zero but keeps its id for saved orders."""
    variant_id = service.add_variant(product_id, "Blue", 3)

    assert service.remove_variant_from_sale(product_id, variant_id) is True

    snapshot = service.get_variant_snapshot(variant_id)
    assert snapshot["stock"] == 0
    assert service.decrement_stock(variant_id, 1) is False


def test_remove_variant_from_sale_rejects_bad_ids(service, product_id):
    """Invalid ids are refused without touching the database."""
    assert service.remove_variant_from_sale(0, 1) is False
    assert service.remove_variant_from_sale(product_id, -1) is False
