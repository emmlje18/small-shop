"""JSON API of the catalog service.

Three groups of endpoints, each a Flask blueprint:

  public    GET /products, GET /products/<id>        anyone (the static UI)
  admin     /admin/products...                        Authorization: Bearer <ADMIN_PASSWORD>
  internal  /internal/variants/<id>...                X-Internal-Token: <INTERNAL_TOKEN>
            (the three seam operations the orders service calls, ADR-2)
"""

import hmac
from decimal import Decimal, InvalidOperation
from functools import wraps

from flask import Blueprint, Response, current_app, jsonify, request

from catalog.service import CatalogService

public_api = Blueprint("public_api", __name__)
admin_api = Blueprint("admin_api", __name__, url_prefix="/admin")
internal_api = Blueprint("internal_api", __name__, url_prefix="/internal")


# ---------------------------------------------------------------- helpers

def _catalog():
    """Create the catalog service for this request's configured database."""
    return CatalogService(current_app.config["DATABASE_URL"])


def _body():
    """Return the request's JSON object, or {} if it sent none."""
    body = request.get_json(silent=True)
    return body if isinstance(body, dict) else {}


def _error(message, status):
    return jsonify(error=message), status


def _product_json(product, variants=None):
    """Shape a product row for JSON: ISO date and a URL for its picture."""
    data = {
        "id": product["id"],
        "name": product["name"],
        "description": product["description"],
        "price_cents": product["price_cents"],
        "is_active": bool(product["is_active"]),
        "created_at": product["created_at"].isoformat(),
        # Relative to the catalog's base URL; None means "show the placeholder".
        # ?v= changes whenever the picture is replaced, so browsers fetch the
        # new one instead of a cached copy.
        "image_url": (f"/products/{product['id']}/image?v={product['image_version']}"
                      if product["has_image"] else None),
    }
    if variants is not None:
        data["variants"] = variants
    return data


def parse_price_cents(value):
    """Convert a price such as "12.50" or 12.5 to integer cents (1250)."""
    try:
        amount = Decimal(str(value).strip())
        rounded = amount.quantize(Decimal("0.01"))
    except (InvalidOperation, AttributeError):
        raise ValueError("Enter a valid price, such as 12.50.") from None
    if not amount.is_finite() or amount < 0 or amount != rounded:
        raise ValueError("Price must be nonnegative and have at most two decimals.")
    return int(rounded * 100)


def parse_nonnegative_integer(value, field_name):
    """Read a whole number that may arrive as 5 or "5"; reject negatives."""
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a whole number.")
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be a whole number.") from None
    if number < 0:
        raise ValueError(f"{field_name} cannot be negative.")
    return number


def parse_variants(variants):
    """Validate a list of {"option_label", "stock"} objects; at least one."""
    if not isinstance(variants, list) or not variants:
        raise ValueError("Add at least one option.")
    clean = []
    for position, variant in enumerate(variants, start=1):
        if not isinstance(variant, dict):
            raise ValueError(f"Option {position} is not valid.")
        label = str(variant.get("option_label", "")).strip()
        if not label:
            raise ValueError(f"Option {position} needs a label.")
        stock = parse_nonnegative_integer(variant.get("stock"), f"Stock for option {position}")
        clean.append({"option_label": label, "stock": stock})
    return clean


def _secret_matches(given, config_key):
    """Compare a supplied secret in constant time; an unset secret never matches."""
    expected = current_app.config.get(config_key) or ""
    return bool(expected) and hmac.compare_digest(given.encode(), expected.encode())


def admin_required(view):
    """Allow the request only with Authorization: Bearer <ADMIN_PASSWORD>."""
    @wraps(view)
    def check(*args, **kwargs):
        scheme, _, token = request.headers.get("Authorization", "").partition(" ")
        if scheme != "Bearer" or not _secret_matches(token, "ADMIN_PASSWORD"):
            return _error("Admin password required.", 401)
        return view(*args, **kwargs)
    return check


def internal_required(view):
    """Allow the request only from a caller that knows INTERNAL_TOKEN (orders)."""
    @wraps(view)
    def check(*args, **kwargs):
        if not _secret_matches(request.headers.get("X-Internal-Token", ""), "INTERNAL_TOKEN"):
            return _error("Internal token required.", 401)
        return view(*args, **kwargs)
    return check


# ---------------------------------------------------------------- public

@public_api.get("/products")
def list_products():
    """Active products for the shop's home page."""
    return jsonify([_product_json(p) for p in _catalog().list_products()])


@public_api.get("/products/<int:product_id>")
def get_product(product_id):
    """One active product with its options and stock, for the product page."""
    catalog = _catalog()
    product = catalog.get_product(product_id)
    if product is None:
        return _error("Product not found.", 404)
    return jsonify(_product_json(product, catalog.list_variants(product_id)))


def _image_response(image):
    """Send stored image bytes with their type.

    A request with ?v=<image_version> names one exact picture, so browsers may
    keep it for a day; a replaced picture gets a new version and a new URL.
    Without a version (cart thumbnails) browsers must check every time.
    """
    if image is None:
        return _error("No image.", 404)
    cache = "public, max-age=86400" if request.args.get("v") else "no-cache"
    return Response(
        image["image_data"],
        mimetype=image["image_content_type"],
        headers={"Cache-Control": cache},
    )


@public_api.get("/products/<int:product_id>/image")
def product_image(product_id):
    """The product's picture, stored in the catalog database."""
    return _image_response(_catalog().get_product_image(product_id))


@public_api.get("/variants/<int:variant_id>/image")
def variant_image(variant_id):
    """The picture of the product an option belongs to (cart thumbnails)."""
    return _image_response(_catalog().get_variant_image(variant_id))


# ---------------------------------------------------------------- admin

@admin_api.get("/products")
@admin_required
def admin_list_products():
    """Active products with their options, for the admin product list."""
    catalog = _catalog()
    return jsonify([
        _product_json(p, catalog.list_variants(p["id"])) for p in catalog.list_products()
    ])


@admin_api.get("/products/<int:product_id>")
@admin_required
def admin_get_product(product_id):
    """One product for the edit page, even if it was removed from the shop."""
    catalog = _catalog()
    product = catalog.get_product_for_admin(product_id)
    if product is None:
        return _error("Product not found.", 404)
    return jsonify(_product_json(product, catalog.list_variants(product_id)))


@admin_api.post("/products")
@admin_required
def admin_create_product():
    """Create a product with one or more options.

    Body: {"name", "description", "price": "12.50", "variants": [{"option_label", "stock"}]}
    Everything is validated before anything is saved.
    """
    body = _body()
    try:
        price_cents = parse_price_cents(body.get("price", ""))
        variants = parse_variants(body.get("variants"))
        catalog = _catalog()
        product_id = catalog.add_product(
            body.get("name", ""), body.get("description", ""), price_cents
        )
        for variant in variants:
            catalog.add_variant(product_id, variant["option_label"], variant["stock"])
    except ValueError as error:
        return _error(str(error), 400)
    return jsonify(id=product_id), 201


@admin_api.put("/products/<int:product_id>")
@admin_required
def admin_update_product(product_id):
    """Change a product's name, description and price (options are separate)."""
    catalog = _catalog()
    product = catalog.get_product_for_admin(product_id)
    if product is None:
        return _error("Product not found.", 404)
    body = _body()
    try:
        catalog.update_product(
            product_id,
            body.get("name", ""),
            body.get("description", ""),
            parse_price_cents(body.get("price", "")),
        )
    except ValueError as error:
        return _error(str(error), 400)
    return jsonify(id=product_id)


@admin_api.delete("/products/<int:product_id>")
@admin_required
def admin_delete_product(product_id):
    """Hide a product from the shop; the row stays for old order snapshots."""
    if not _catalog().deactivate_product(product_id):
        return _error("Product not found or already removed.", 404)
    return "", 204


@admin_api.put("/products/<int:product_id>/image")
@admin_required
def admin_set_image(product_id):
    """Upload or replace a product's picture: multipart form with an "image" file.

    Requests over 5 MB are refused by Flask (MAX_CONTENT_LENGTH) with 413.
    """
    catalog = _catalog()
    if catalog.get_product_for_admin(product_id) is None:
        return _error("Product not found.", 404)
    upload = request.files.get("image")
    if upload is None or not upload.filename:
        return _error("Choose an image file.", 400)
    try:
        catalog.set_product_image(product_id, upload.filename, upload.read())
    except ValueError as error:
        return _error(str(error), 400)
    return "", 204


@admin_api.post("/products/<int:product_id>/variants")
@admin_required
def admin_add_variant(product_id):
    """Add one option to an existing product. Body: {"option_label", "stock"}."""
    catalog = _catalog()
    if catalog.get_product_for_admin(product_id) is None:
        return _error("Product not found.", 404)
    body = _body()
    try:
        stock = parse_nonnegative_integer(body.get("stock"), "Stock")
        variant_id = catalog.add_variant(product_id, body.get("option_label", ""), stock)
    except ValueError as error:
        return _error(str(error), 400)
    return jsonify(id=variant_id), 201


@admin_api.put("/products/<int:product_id>/variants/<int:variant_id>")
@admin_required
def admin_update_variant(product_id, variant_id):
    """Change one option's label and stock. Body: {"option_label", "stock"}."""
    body = _body()
    try:
        stock = parse_nonnegative_integer(body.get("stock"), "Stock")
        updated = _catalog().update_variant(
            product_id, variant_id, body.get("option_label", ""), stock
        )
    except ValueError as error:
        return _error(str(error), 400)
    if not updated:
        return _error("This option does not belong to the product.", 404)
    return jsonify(id=variant_id)


@admin_api.delete("/products/<int:product_id>/variants/<int:variant_id>")
@admin_required
def admin_remove_variant(product_id, variant_id):
    """Take an option off sale (stock 0); its id stays valid for old orders."""
    if not _catalog().remove_variant_from_sale(product_id, variant_id):
        return _error("This option does not belong to the product.", 404)
    return "", 204


# ---------------------------------------------------------------- internal

def _quantity():
    """Read a positive quantity from the JSON body, or None if invalid."""
    quantity = _body().get("quantity")
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
        return None
    return quantity


@internal_api.get("/variants/<int:variant_id>")
@internal_required
def variant_snapshot(variant_id):
    """Name, option, price and stock that orders copies into an order item."""
    snapshot = _catalog().get_variant_snapshot(variant_id)
    if snapshot is None:
        return _error("Variant not found or no longer for sale.", 404)
    return jsonify(snapshot)


@internal_api.post("/variants/<int:variant_id>/decrement")
@internal_required
def decrement_stock(variant_id):
    """Reserve stock for a checkout. 409 if not enough is left."""
    quantity = _quantity()
    if quantity is None:
        return _error("Quantity must be a positive whole number.", 400)
    if not _catalog().decrement_stock(variant_id, quantity):
        return _error("Not enough stock.", 409)
    return jsonify(variant_id=variant_id, decremented=quantity)


@internal_api.post("/variants/<int:variant_id>/restore")
@internal_required
def restore_stock(variant_id):
    """Give reserved stock back after a failed payment or a cancelled order."""
    quantity = _quantity()
    if quantity is None:
        return _error("Quantity must be a positive whole number.", 400)
    _catalog().restore_stock(variant_id, quantity)
    return jsonify(variant_id=variant_id, restored=quantity)
