"""Orders endpoints that do not depend on catalog behaviour: input checks, orders, health, CORS, logs."""

import pytest

from orders import create_app
from tests.conftest import make_client


@pytest.mark.parametrize(
    "cart", ["not a list", [{"variant_id": "1", "qty": 1}], [{"variant_id": 1}], [{"variant_id": True, "qty": 1}], [5]]
)
def test_malformed_carts_are_refused(client, cart):
    for path in ("/cart/summary", "/checkout"):
        assert client.post(path, json={"cart": cart}).status_code == 400


def test_checkout_validation_errors_are_400(client):
    response = client.post("/checkout", json={"cart": [], "customer_name": "E",
                                              "customer_email": "e@example.com", "card_number": "1"})
    assert response.status_code == 400
    assert "empty" in response.get_json()["error"]


def test_order_needs_the_matching_email(client):
    order_id = client.post("/checkout", json={
        "cart": [{"variant_id": 1, "qty": 1}], "customer_name": "Emma",
        "customer_email": "Emma@Example.com", "card_number": "4242"}).get_json()["order_id"]
    ok = client.get(f"/orders/{order_id}?email=emma@example.com")
    assert ok.status_code == 200
    body = ok.get_json()
    assert body["status"] == "paid" and body["total_cents"] == 500 and len(body["items"]) == 1
    assert client.get(f"/orders/{order_id}?email=other@example.com").status_code == 404
    assert client.get(f"/orders/{order_id}").status_code == 404
    assert client.get("/orders/999999?email=emma@example.com").status_code == 404


def test_health_ok_and_503(client):
    assert client.get("/health").get_json() == {"status": "ok", "db": "ok", "version": "dev"}
    broken = create_app({"DATABASE_URL": "mssql+pymssql://u:p@127.0.0.1:1/none_test", "TESTING": True})
    response = broken.test_client().get("/health")
    assert response.status_code == 503
    assert response.get_json()["db"] == "unavailable"


def test_unknown_route_is_json_404(client):
    response = client.get("/nope")
    assert response.status_code == 404
    assert "error" in response.get_json()


def test_cors_only_for_the_ui(client):
    assert client.get("/health", headers={"Origin": "http://ui.test"}).headers.get(
        "Access-Control-Allow-Origin") == "http://ui.test"
    assert "Access-Control-Allow-Origin" not in client.get("/health", headers={"Origin": "https://evil.example"}).headers


def test_every_request_is_logged(db, stub_catalog, caplog):
    caplog.set_level("INFO", logger="orders.request")
    make_client(db, stub_catalog["url"]).get("/health")
    assert any("GET /health 200" in record.getMessage() for record in caplog.records)
