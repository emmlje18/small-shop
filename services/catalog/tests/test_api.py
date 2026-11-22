"""HTTP endpoints of the catalog, called through Flask's test client."""

import io

import pytest

from catalog import create_app
from catalog.api import parse_nonnegative_integer, parse_price_cents, parse_variants
from tests.conftest import ADMIN, INTERNAL

NEW_PRODUCT = {
    "name": "Musa", "description": "Plush", "price": "2.00",
    "variants": [{"option_label": "Small", "stock": 5}, {"option_label": "Large", "stock": 1}],
}


@pytest.fixture
def product(client):
    """Create a product through the admin API and return its JSON."""
    product_id = client.post("/admin/products", json=NEW_PRODUCT, headers=ADMIN).get_json()["id"]
    return client.get(f"/products/{product_id}").get_json()


# --------------------------------------------------------------- parsing

@pytest.mark.parametrize(("value", "cents"), [("12.50", 1250), ("0", 0), (3, 300), (" 2.5 ", 250)])
def test_parse_price_cents(value, cents):
    assert parse_price_cents(value) == cents


@pytest.mark.parametrize("value", ["abc", "-1", "2.005", "", None, "inf"])
def test_parse_price_cents_rejects(value):
    with pytest.raises(ValueError):
        parse_price_cents(value)


def test_parse_nonnegative_integer():
    assert parse_nonnegative_integer("5", "Stock") == 5
    for bad in (-1, "x", None, True):
        with pytest.raises(ValueError):
            parse_nonnegative_integer(bad, "Stock")


@pytest.mark.parametrize(
    "variants", [None, [], ["x"], [{"option_label": " ", "stock": 1}], [{"option_label": "A", "stock": -1}]]
)
def test_parse_variants_rejects(variants):
    with pytest.raises(ValueError):
        parse_variants(variants)


# --------------------------------------------------------------- public

def test_public_list_and_detail(client, product):
    listed = client.get("/products").get_json()
    assert [p["name"] for p in listed] == ["Musa"]
    assert listed[0]["image_url"] is None
    assert [v["option_label"] for v in product["variants"]] == ["Small", "Large"]
    assert product["price_cents"] == 200


def test_unknown_product_and_route_return_json_404(client):
    assert client.get("/products/999999").status_code == 404
    response = client.get("/nope")
    assert response.status_code == 404
    assert "error" in response.get_json()


# --------------------------------------------------------------- admin

@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer wrong"}, {"Authorization": "test-admin"}])
def test_admin_requires_the_password(client, headers):
    assert client.post("/admin/products", json=NEW_PRODUCT, headers=headers).status_code == 401
    assert client.get("/admin/products", headers=headers).status_code == 401


def test_admin_is_locked_when_no_password_is_configured(db):
    client = create_app({"DATABASE_URL": db, "ADMIN_PASSWORD": "", "TESTING": True}).test_client()
    assert client.get("/admin/products", headers={"Authorization": "Bearer "}).status_code == 401


def test_admin_create_validates_before_saving(client):
    bad = {**NEW_PRODUCT, "price": "2.005"}
    response = client.post("/admin/products", json=bad, headers=ADMIN)
    assert response.status_code == 400
    assert "decimals" in response.get_json()["error"]
    assert client.get("/products").get_json() == []


def test_admin_list_includes_variants(client, product):
    listed = client.get("/admin/products", headers=ADMIN).get_json()
    assert len(listed[0]["variants"]) == 2


def test_admin_update_product(client, product):
    url = f"/admin/products/{product['id']}"
    body = {"name": "Musa XL", "description": "Bigger", "price": "3.50"}
    assert client.put(url, json=body, headers=ADMIN).status_code == 200
    assert client.get(f"/products/{product['id']}").get_json()["price_cents"] == 350
    assert client.put(url, json={**body, "price": "x"}, headers=ADMIN).status_code == 400
    assert client.put("/admin/products/999999", json=body, headers=ADMIN).status_code == 404


def test_admin_delete_hides_product_but_admin_still_sees_it(client, product):
    url = f"/admin/products/{product['id']}"
    assert client.delete(url, headers=ADMIN).status_code == 204
    assert client.get(f"/products/{product['id']}").status_code == 404
    assert client.get(url, headers=ADMIN).get_json()["is_active"] is False
    assert client.delete(url, headers=ADMIN).status_code == 404
    assert client.get("/admin/products/999999", headers=ADMIN).status_code == 404


def test_admin_variant_add_update_remove(client, product):
    base = f"/admin/products/{product['id']}/variants"
    created = client.post(base, json={"option_label": "Giant", "stock": 2}, headers=ADMIN)
    assert created.status_code == 201
    variant_id = created.get_json()["id"]

    assert client.post(base, json={"option_label": "X", "stock": -1}, headers=ADMIN).status_code == 400
    assert client.post("/admin/products/999999/variants", json={"option_label": "X", "stock": 1},
                       headers=ADMIN).status_code == 404

    url = f"{base}/{variant_id}"
    assert client.put(url, json={"option_label": "Huge", "stock": 4}, headers=ADMIN).status_code == 200
    assert client.put(url, json={"option_label": "", "stock": 4}, headers=ADMIN).status_code == 400
    assert client.put(f"{base}/999999", json={"option_label": "A", "stock": 1}, headers=ADMIN).status_code == 404

    assert client.delete(url, headers=ADMIN).status_code == 204
    assert client.delete(f"{base}/999999", headers=ADMIN).status_code == 404
    stocks = {v["option_label"]: v["stock"] for v in client.get(f"/products/{product['id']}").get_json()["variants"]}
    assert stocks["Huge"] == 0


def test_image_upload_and_serving(client, product):
    url = f"/admin/products/{product['id']}/image"
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 16

    assert client.get(f"/products/{product['id']}/image").status_code == 404
    assert client.put(url, headers=ADMIN, data={}).status_code == 400
    bad = client.put(url, headers=ADMIN, data={"image": (io.BytesIO(b"hi"), "notes.txt")})
    assert bad.status_code == 400
    assert client.put(url, data={"image": (io.BytesIO(png), "a.png")}).status_code == 401
    assert client.put("/admin/products/999999/image", headers=ADMIN,
                      data={"image": (io.BytesIO(png), "a.png")}).status_code == 404

    assert client.put(url, headers=ADMIN, data={"image": (io.BytesIO(png), "a.png")}).status_code == 204
    served = client.get(f"/products/{product['id']}/image")
    assert served.status_code == 200
    assert served.mimetype == "image/png"
    assert served.data == png
    assert client.get(f"/variants/{product['variants'][0]['id']}/image").data == png
    first_url = client.get(f"/products/{product['id']}").get_json()["image_url"]
    assert first_url == f"/products/{product['id']}/image?v=1"
    assert client.get(first_url).headers["Cache-Control"] == "public, max-age=86400"
    assert served.headers["Cache-Control"] == "no-cache"

    # Replacing the picture gives it a new URL, so browsers do not show the old one.
    assert client.put(url, headers=ADMIN, data={"image": (io.BytesIO(png), "b.png")}).status_code == 204
    assert client.get(f"/products/{product['id']}").get_json()["image_url"] == f"/products/{product['id']}/image?v=2"


def test_upload_over_the_limit_is_refused_with_413(client, product):
    big = io.BytesIO(b"0" * (6 * 1024 * 1024))
    response = client.put(f"/admin/products/{product['id']}/image", headers=ADMIN,
                          data={"image": (big, "big.png")})
    assert response.status_code == 413


# --------------------------------------------------------------- internal (orders' seam)

def test_internal_requires_the_token(client, product):
    variant_id = product["variants"][0]["id"]
    assert client.get(f"/internal/variants/{variant_id}").status_code == 401
    assert client.get(f"/internal/variants/{variant_id}", headers={"X-Internal-Token": "x"}).status_code == 401


def test_internal_snapshot_decrement_restore(client, product):
    large = product["variants"][1]["id"]
    snapshot = client.get(f"/internal/variants/{large}", headers=INTERNAL).get_json()
    assert snapshot == {"variant_id": large, "product_name": "Musa", "option_label": "Large",
                        "unit_price_cents": 200, "stock": 1}

    decrement = f"/internal/variants/{large}/decrement"
    assert client.post(decrement, json={"quantity": 1}, headers=INTERNAL).status_code == 200
    sold_out = client.post(decrement, json={"quantity": 1}, headers=INTERNAL)
    assert sold_out.status_code == 409
    assert client.post(f"/internal/variants/{large}/restore", json={"quantity": 1},
                       headers=INTERNAL).status_code == 200
    assert client.get(f"/internal/variants/{large}", headers=INTERNAL).get_json()["stock"] == 1


@pytest.mark.parametrize("body", [{}, {"quantity": 0}, {"quantity": -2}, {"quantity": "1"}, {"quantity": True}])
def test_internal_rejects_bad_quantities(client, product, body):
    variant_id = product["variants"][0]["id"]
    for action in ("decrement", "restore"):
        response = client.post(f"/internal/variants/{variant_id}/{action}", json=body, headers=INTERNAL)
        assert response.status_code == 400


def test_internal_snapshot_of_unknown_variant(client):
    assert client.get("/internal/variants/999999", headers=INTERNAL).status_code == 404


# --------------------------------------------------------------- health, CORS, logs

def test_health_ok_writes_and_reads_the_database(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok", "db": "ok", "version": "dev"}


def test_health_503_when_the_database_is_unreachable():
    broken = create_app({"DATABASE_URL": "mssql+pymssql://u:p@127.0.0.1:1/none_test", "TESTING": True})
    response = broken.test_client().get("/health")
    assert response.status_code == 503
    assert response.get_json()["db"] == "unavailable"


def test_cors_allows_only_the_ui_origin(client):
    allowed = client.get("/products", headers={"Origin": "http://ui.test"})
    assert allowed.headers.get("Access-Control-Allow-Origin") == "http://ui.test"
    other = client.get("/products", headers={"Origin": "https://evil.example"})
    assert "Access-Control-Allow-Origin" not in other.headers
    internal = client.get("/internal/variants/1", headers={"Origin": "http://ui.test", **INTERNAL})
    assert "Access-Control-Allow-Origin" not in internal.headers


def test_every_request_is_logged(client, caplog):
    caplog.set_level("INFO", logger="catalog.request")
    client.get("/products")
    assert any("GET /products 200" in record.getMessage() for record in caplog.records)
