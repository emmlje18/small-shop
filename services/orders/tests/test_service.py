"""OrderService rules with an in-memory catalog (ported from Assignment 1) and payment."""

import pytest

from orders import repository
from orders.catalog_client import CatalogUnavailable
from orders.payment import FakePaymentProvider
from orders.service import OrderService

CARD = "4242 4242 4242 4242"
DECLINED = "4242 4242 4242 0000"


@pytest.fixture
def service(fake_catalog, db):
    return OrderService(fake_catalog, FakePaymentProvider(), db)


def test_cart_total_uses_current_prices(fake_catalog):
    summary = OrderService(fake_catalog).cart_summary([{"variant_id": 1, "qty": 2}, {"variant_id": 2, "qty": 1}])
    assert summary["total_cents"] == 1700
    assert summary["items"][0]["line_total_cents"] == 1000


def test_cart_summary_skips_options_no_longer_for_sale(fake_catalog):
    summary = OrderService(fake_catalog).cart_summary([{"variant_id": 99, "qty": 1}])
    assert summary == {"items": [], "total_cents": 0}


def test_add_to_cart_merges_duplicate_lines(fake_catalog):
    service = OrderService(fake_catalog)
    cart = service.add_to_cart(service.add_to_cart([], 1, 1), 1, 2)
    assert cart == [{"variant_id": 1, "qty": 3}]


def test_add_to_cart_refuses_an_oversell_and_bad_input(fake_catalog):
    service = OrderService(fake_catalog)
    with pytest.raises(ValueError, match="not enough"):
        service.add_to_cart([], 1, 4)
    with pytest.raises(ValueError, match="no longer available"):
        service.add_to_cart([], 99, 1)
    with pytest.raises(ValueError, match="Quantity"):
        service.add_to_cart([], 1, 0)


def test_set_quantity_and_remove(fake_catalog):
    service = OrderService(fake_catalog)
    cart = [{"variant_id": 1, "qty": 1}, {"variant_id": 2, "qty": 1}]
    assert service.set_cart_quantity(cart, 1, 3)[0]["qty"] == 3
    assert service.remove_from_cart(cart, 2) == [{"variant_id": 1, "qty": 1}]
    with pytest.raises(ValueError, match="not in the cart"):
        service.set_cart_quantity([], 1, 1)


def test_checkout_saves_a_paid_order_with_snapshots(service, fake_catalog, db):
    result = service.checkout([{"variant_id": 1, "qty": 2}], " Emma ", "emma@example.com", CARD)
    order = repository.get_order(db, result["order_id"])
    assert result["success"] is True
    assert (order["status"], order["total_cents"], order["customer_name"]) == ("paid", 1000, "Emma")
    assert order["payment_ref"].startswith("fake-")
    assert repository.get_order_items(db, result["order_id"]) == [
        {"variant_id": 1, "product_name": "Keychain", "option_label": "Blue", "unit_price_cents": 500, "quantity": 2}
    ]
    assert fake_catalog.snapshots[1]["stock"] == 1


def test_last_item_cannot_be_bought_by_two_customers(service, fake_catalog):
    fake_catalog.snapshots[1]["stock"] = 1
    cart = [{"variant_id": 1, "qty": 1}]
    assert service.checkout(cart, "First", "first@example.com", CARD)["success"] is True
    with pytest.raises(ValueError, match="sold out"):
        service.checkout(cart, "Second", "second@example.com", CARD)
    assert fake_catalog.snapshots[1]["stock"] == 0


def test_sold_out_line_gives_back_earlier_lines(service, fake_catalog):
    fake_catalog.snapshots[2]["stock"] = 0
    with pytest.raises(ValueError, match="sold out"):
        service.checkout([{"variant_id": 1, "qty": 2}, {"variant_id": 2, "qty": 1}], "E", "e@example.com", CARD)
    assert fake_catalog.snapshots[1]["stock"] == 3


def test_payment_failure_restores_stock_and_cancels_order(service, fake_catalog, db):
    result = service.checkout([{"variant_id": 1, "qty": 2}], "Buyer", "buyer@example.com", DECLINED)
    assert result["success"] is False
    assert repository.get_order(db, result["order_id"])["status"] == "cancelled"
    assert fake_catalog.snapshots[1]["stock"] == 3


@pytest.mark.parametrize(
    ("cart", "name", "email", "message"),
    [([], "E", "e@example.com", "empty"), ([{"variant_id": 1, "qty": 1}], " ", "e@example.com", "name"),
     ([{"variant_id": 1, "qty": 1}], "E", "not-an-email", "email")],
)
def test_checkout_validation(service, cart, name, email, message):
    with pytest.raises(ValueError, match=message):
        service.checkout(cart, name, email, CARD)


def test_cancel_and_ship_rules(service, fake_catalog, db):
    first = service.checkout([{"variant_id": 1, "qty": 1}], "B", "b@example.com", CARD)["order_id"]
    service.cancel_order(first)
    assert repository.get_order(db, first)["status"] == "cancelled"
    assert fake_catalog.snapshots[1]["stock"] == 3

    second = service.checkout([{"variant_id": 1, "qty": 1}], "B", "b@example.com", CARD)["order_id"]
    service.mark_shipped(second)
    with pytest.raises(ValueError, match="cannot be cancelled"):
        service.cancel_order(second)
    with pytest.raises(ValueError, match="paid"):
        service.mark_shipped(first)


def test_missing_collaborators_are_reported(fake_catalog):
    with pytest.raises(RuntimeError, match="payment provider"):
        OrderService(fake_catalog, None, "x").checkout([], "E", "e@example.com", CARD)
    with pytest.raises(RuntimeError, match="database"):
        OrderService(fake_catalog).cancel_order(1)


def test_catalog_dropping_mid_checkout_gives_back_and_reports(db, fake_catalog, caplog):
    """If the catalog fails part-way, earlier reservations are given back and nothing is charged."""
    calls = {"n": 0}
    real_decrement = fake_catalog.decrement_stock

    def flaky_decrement(variant_id, quantity):
        calls["n"] += 1
        if calls["n"] == 2:
            raise CatalogUnavailable("down")
        return real_decrement(variant_id, quantity)

    fake_catalog.decrement_stock = flaky_decrement
    service = OrderService(fake_catalog, FakePaymentProvider(), db)
    with pytest.raises(CatalogUnavailable):
        service.checkout([{"variant_id": 1, "qty": 1}, {"variant_id": 2, "qty": 1}], "E", "e@example.com", CARD)
    assert fake_catalog.snapshots[1]["stock"] == 3


def test_restore_failure_is_logged_not_raised(db, fake_catalog, caplog):
    def broken_restore(variant_id, quantity):
        raise CatalogUnavailable("down")

    fake_catalog.restore_stock = broken_restore
    service = OrderService(fake_catalog, FakePaymentProvider(), db)
    result = service.checkout([{"variant_id": 1, "qty": 1}], "E", "e@example.com", DECLINED)
    assert result["success"] is False
    assert "Could not restore" in caplog.text


def test_fake_payment_provider():
    provider = FakePaymentProvider()
    assert provider.charge(500, CARD).startswith("fake-")
    assert provider.charge(500, DECLINED) is None
    assert provider.charge(0, CARD) is None
    assert provider.charge(500, "") is None
