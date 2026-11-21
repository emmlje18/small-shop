"""Integration tests across the seam: orders talks to a catalog over real HTTP.

The catalog is replaced by a stub server (conftest.build_stub_catalog) that
follows services/catalog/openapi.yaml. The orders app, its CatalogClient, the
HTTP requests and the orders database are all real (ADR-9).
"""

import time

from orders.catalog_client import CatalogClient, CatalogUnavailable
from orders import repository
from tests.conftest import STUB_TOKEN, make_client

ORDER = {"customer_name": "Emma", "customer_email": "emma@example.com", "card_number": "4242"}


def checkout(client, cart, **overrides):
    return client.post("/checkout", json={"cart": cart, **ORDER, **overrides})


def test_paid_checkout_reserves_stock_in_the_catalog(client, stub_catalog, db):
    response = checkout(client, [{"variant_id": 1, "qty": 2}])
    assert response.status_code == 201
    order_id = response.get_json()["order_id"]

    assert stub_catalog["stock"][1] == 1
    assert ("POST", "/internal/variants/1/decrement") in stub_catalog["calls"]
    assert repository.get_order(db, order_id)["status"] == "paid"
    assert repository.get_order_items(db, order_id)[0]["product_name"] == "Keychain"


def test_declined_payment_gives_stock_back_over_http(client, stub_catalog):
    response = checkout(client, [{"variant_id": 1, "qty": 2}], card_number="4242 0000")
    assert response.status_code == 402
    assert response.get_json()["status"] == "cancelled"
    assert stub_catalog["stock"][1] == 3
    assert ("POST", "/internal/variants/1/restore") in stub_catalog["calls"]


def test_sold_out_in_the_catalog_is_a_clear_400(client, stub_catalog):
    stub_catalog["stock"][1] = 1
    response = checkout(client, [{"variant_id": 1, "qty": 2}])
    assert response.status_code == 400
    assert "sold out" in response.get_json()["error"]


def test_cart_endpoints_use_live_catalog_data(client, stub_catalog):
    added = client.post("/cart/add", json={"cart": [], "variant_id": 2, "quantity": 2}).get_json()
    assert added == {"cart": [{"variant_id": 2, "qty": 2}]}
    too_many = client.post("/cart/add", json={"cart": [], "variant_id": 2, "quantity": 3})
    assert too_many.status_code == 400
    summary = client.post("/cart/summary", json={"cart": added["cart"]}).get_json()
    assert summary["total_cents"] == 1400
    updated = client.post("/cart/update", json={"cart": added["cart"], "variant_id": 2, "quantity": 1})
    assert updated.get_json() == {"cart": [{"variant_id": 2, "qty": 1}]}
    removed = client.post("/cart/update", json={"cart": added["cart"], "variant_id": 2, "quantity": 0})
    assert removed.get_json() == {"cart": []}


def test_catalog_stopped_gives_503_but_orders_still_serves_its_own_data(db, stub_catalog):
    """Partial failure: with no catalog, cart and checkout fail clearly; reading an order works."""
    healthy = make_client(db, stub_catalog["url"])
    order_id = checkout(healthy, [{"variant_id": 1, "qty": 1}]).get_json()["order_id"]

    down = make_client(db, "http://127.0.0.1:1")  # nothing listens on port 1
    for response in (
        down.post("/cart/summary", json={"cart": [{"variant_id": 1, "qty": 1}]}),
        checkout(down, [{"variant_id": 1, "qty": 1}]),
    ):
        assert response.status_code == 503
        assert "unavailable" in response.get_json()["error"]

    assert down.get(f"/orders/{order_id}?email=emma@example.com").status_code == 200
    assert down.get("/health").status_code == 200


def test_slow_catalog_times_out_instead_of_hanging(db, stub_catalog):
    stub_catalog["delay_s"] = 1.5
    client = make_client(db, stub_catalog["url"], timeout_s=0.3)
    started = time.monotonic()
    response = client.post("/cart/summary", json={"cart": [{"variant_id": 1, "qty": 1}]})
    assert response.status_code == 503
    assert time.monotonic() - started < 1.2


def test_wrong_token_is_treated_as_unavailable(stub_catalog):
    client = CatalogClient(stub_catalog["url"], "wrong-token", timeout_s=2)
    try:
        client.get_variant_snapshot(1)
        raise AssertionError("expected CatalogUnavailable")
    except CatalogUnavailable:
        pass


def test_client_matches_the_catalog_contract(stub_catalog):
    client = CatalogClient(stub_catalog["url"] + "/", STUB_TOKEN, timeout_s=2)
    assert client.get_variant_snapshot(1)["unit_price_cents"] == 500
    assert client.get_variant_snapshot(99) is None
    assert client.decrement_stock(1, 3) is True
    assert client.decrement_stock(1, 1) is False
    client.restore_stock(1, 3)
    assert stub_catalog["stock"][1] == 3
