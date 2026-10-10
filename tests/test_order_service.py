"""Tests for cart, checkout, stock recovery, and order status rules."""

import pytest

from app.orders import repository
from app.orders.payment import FakePaymentProvider
from app.orders.service import OrderService


def make_order_service(fake_catalog, database_path):
    """Build the service with test doubles and a temporary order database."""
    return OrderService(fake_catalog, FakePaymentProvider(), database_path)


def test_cart_total_uses_current_prices(fake_catalog):
    """Cart summary multiplies each fresh price by the selected quantity."""
    service = OrderService(fake_catalog)

    summary = service.cart_summary([
        {"variant_id": 1, "qty": 2},
        {"variant_id": 2, "qty": 1},
    ])

    assert summary["total_cents"] == 1700
    assert summary["items"][0]["line_total_cents"] == 1000


def test_add_to_cart_merges_duplicate_variant_lines(fake_catalog):
    """Adding the same option twice produces one line with a larger quantity."""
    service = OrderService(fake_catalog)

    cart = service.add_to_cart([], 1, 1)
    cart = service.add_to_cart(cart, 1, 2)

    assert cart == [{"variant_id": 1, "qty": 3}]


def test_add_to_cart_refuses_an_oversell(fake_catalog):
    """A cart cannot request more units than the snapshot says are available."""
    service = OrderService(fake_catalog)

    with pytest.raises(ValueError, match="not enough"):
        service.add_to_cart([], 1, 4)


def test_last_item_cannot_be_bought_by_two_customers(fake_catalog, database_path):
    """The second checkout fails after the first buyer uses the final unit."""
    fake_catalog.snapshots[1]["stock"] = 1
    service = make_order_service(fake_catalog, database_path)
    cart = [{"variant_id": 1, "qty": 1}]

    first_result = service.checkout(cart, "First Buyer", "first@example.com", "1234")

    with pytest.raises(ValueError, match="sold out"):
        service.checkout(cart, "Second Buyer", "second@example.com", "5678")

    assert first_result["success"] is True
    assert fake_catalog.snapshots[1]["stock"] == 0


def test_payment_failure_restores_stock_and_cancels_order(fake_catalog, database_path):
    """A declined payment leaves stock available and saves a cancelled order."""
    service = make_order_service(fake_catalog, database_path)

    result = service.checkout(
        [{"variant_id": 1, "qty": 2}],
        "Buyer",
        "buyer@example.com",
        "4242 4242 4242 0000",
    )

    order = repository.get_order(database_path, result["order_id"])
    assert result["success"] is False
    assert order["status"] == "cancelled"
    assert fake_catalog.snapshots[1]["stock"] == 3


def test_cancel_order_restores_stock(fake_catalog, database_path):
    """Cancelling a paid order returns its saved quantities to the catalog."""
    service = make_order_service(fake_catalog, database_path)
    result = service.checkout(
        [{"variant_id": 1, "qty": 1}], "Buyer", "buyer@example.com", "1234"
    )

    service.cancel_order(result["order_id"])

    assert repository.get_order(database_path, result["order_id"])["status"] == "cancelled"
    assert fake_catalog.snapshots[1]["stock"] == 3


def test_invalid_status_transition_is_refused(fake_catalog, database_path):
    """A shipped order cannot later be cancelled."""
    service = make_order_service(fake_catalog, database_path)
    result = service.checkout(
        [{"variant_id": 1, "qty": 1}], "Buyer", "buyer@example.com", "1234"
    )

    service.mark_shipped(result["order_id"])

    with pytest.raises(ValueError, match="cannot be cancelled"):
        service.cancel_order(result["order_id"])
