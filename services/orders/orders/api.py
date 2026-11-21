"""JSON API of the orders service.

The cart lives in the browser (localStorage) as [{"variant_id": 4, "qty": 2}].
The UI sends it with each request; this service checks it against the catalog
and, at checkout, reserves stock in the catalog and saves the order.

When the catalog cannot be reached, cart and checkout answer 503 with a clear
message; reading an existing order still works, because it only needs this
service's own database.
"""

from flask import Blueprint, current_app, jsonify, request

from orders import repository
from orders.catalog_client import CatalogClient, CatalogUnavailable
from orders.payment import FakePaymentProvider
from orders.service import OrderService

orders_api = Blueprint("orders_api", __name__)

CATALOG_DOWN = "The catalog is unavailable right now, so the cart and checkout cannot be checked. Please try again in a minute."


def _order_service():
    """Wire OrderService to the catalog over HTTP and the fake payment provider."""
    config = current_app.config
    catalog = CatalogClient(
        config["CATALOG_URL"], config["INTERNAL_TOKEN"], timeout_s=config["CATALOG_TIMEOUT_S"]
    )
    return OrderService(catalog, FakePaymentProvider(), config["DATABASE_URL"])


def _error(message, code, **extra):
    return jsonify(error=message, **extra), code


def _body():
    body = request.get_json(silent=True)
    return body if isinstance(body, dict) else {}


def _is_count(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _cart(body):
    """Read the cart list from the body; refuse anything that is not well formed."""
    cart = body.get("cart", [])
    if not isinstance(cart, list):
        raise ValueError("The cart must be a list.")
    for line in cart:
        if not (isinstance(line, dict) and _is_count(line.get("variant_id")) and _is_count(line.get("qty"))):
            raise ValueError("Each cart line needs a whole-number variant_id and qty.")
    return cart


def _run(action):
    """Run a service call; map rule errors to 400 and a missing catalog to 503."""
    try:
        return action()
    except CatalogUnavailable:
        return _error(CATALOG_DOWN, 503)
    except ValueError as error:
        return _error(str(error), 400)


@orders_api.post("/cart/summary")
def cart_summary():
    """Price the cart with current catalog prices and stock. Body: {"cart": [...]}."""
    body = _body()
    return _run(lambda: jsonify(_order_service().cart_summary(_cart(body))))


@orders_api.post("/cart/add")
def cart_add():
    """Add units of an option, merging with an existing line. Returns the new cart."""
    body = _body()
    return _run(lambda: jsonify(cart=_order_service().add_to_cart(
        _cart(body), body.get("variant_id"), body.get("quantity"))))


@orders_api.post("/cart/update")
def cart_update():
    """Set a line's quantity; 0 removes the line. Returns the new cart."""
    body = _body()

    def update():
        service, cart, quantity = _order_service(), _cart(body), body.get("quantity")
        if quantity == 0:
            return jsonify(cart=service.remove_from_cart(cart, body.get("variant_id")))
        return jsonify(cart=service.set_cart_quantity(cart, body.get("variant_id"), quantity))

    return _run(update)


@orders_api.post("/checkout")
def checkout():
    """Reserve stock in the catalog, save the order, and charge the fake card.

    Body: {"cart": [...], "customer_name", "customer_email", "card_number"}.
    201 paid; 402 declined (stock given back, order cancelled); 400 invalid or
    sold out; 503 catalog unavailable (nothing charged).
    """
    body = _body()

    def run_checkout():
        result = _order_service().checkout(
            _cart(body),
            body.get("customer_name", ""),
            body.get("customer_email", ""),
            str(body.get("card_number", "")),
        )
        if result["success"]:
            return jsonify(order_id=result["order_id"], status="paid"), 201
        return _error(
            "The payment was declined. Your cart was not charged.", 402,
            order_id=result["order_id"], status="cancelled",
        )

    return _run(run_checkout)


@orders_api.get("/orders/<int:order_id>")
def get_order(order_id):
    """An order and its items, for the confirmation page.

    The customer's email must be given (?email=...), so order ids alone cannot
    be used to read other people's orders. Works even when the catalog is down.
    """
    email = request.args.get("email", "").strip().lower()
    database_url = current_app.config["DATABASE_URL"]
    order = repository.get_order(database_url, order_id)
    if order is None or not email or order["customer_email"].strip().lower() != email:
        return _error("Order not found.", 404)
    return jsonify(
        id=order["id"],
        customer_name=order["customer_name"],
        status=order["status"],
        total_cents=order["total_cents"],
        created_at=order["created_at"].isoformat(),
        items=repository.get_order_items(database_url, order_id),
    )
