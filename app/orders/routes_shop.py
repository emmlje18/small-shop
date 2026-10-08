"""Customer cart pages owned by the orders domain."""

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from app.catalog.service import CatalogService
from app.orders.service import OrderService


shop_blueprint = Blueprint("shop", __name__)


def _order_service():
    """Create an order service with the catalog seam injected into it."""
    catalog = CatalogService(current_app.config["DATABASE_PATH"])
    return OrderService(catalog)


def _cart():
    """Read the cart list from the signed browser session."""
    return session.get("cart", [])


def _save_cart(cart):
    """Store the updated cart list in the signed browser session."""
    session["cart"] = cart


def _form_integer(name):
    """Convert one form field to an integer for the service layer."""
    try:
        return int(request.form.get(name, ""))
    except ValueError:
        readable_name = name.replace("_", " ").capitalize()
        raise ValueError(f"{readable_name} must be a whole number.") from None


@shop_blueprint.post("/cart/items")
def add_to_cart():
    """Add a selected product option to the current browser's cart."""
    product_id = request.form.get("product_id", "")
    try:
        variant_id = _form_integer("variant_id")
        quantity = _form_integer("quantity")
        updated_cart = _order_service().add_to_cart(_cart(), variant_id, quantity)
    except ValueError as error:
        flash(str(error), "error")
    else:
        _save_cart(updated_cart)
        flash("Item added to cart.", "success")

    return redirect(url_for("catalog.product_detail", product_id=product_id))


@shop_blueprint.get("/cart")
def cart():
    """Show the selected options, current prices, and cart total."""
    summary = _order_service().cart_summary(_cart())
    return render_template("shop/cart.html", cart=summary)


@shop_blueprint.post("/cart/items/<int:variant_id>")
def update_cart_item(variant_id):
    """Change a cart line's quantity, or remove it when quantity is zero."""
    try:
        quantity = _form_integer("quantity")
        if quantity == 0:
            updated_cart = _order_service().remove_from_cart(_cart(), variant_id)
        else:
            updated_cart = _order_service().set_cart_quantity(
                _cart(), variant_id, quantity
            )
    except ValueError as error:
        flash(str(error), "error")
    else:
        _save_cart(updated_cart)
        flash("Cart updated.", "success")

    return redirect(url_for("shop.cart"))


@shop_blueprint.post("/cart/items/<int:variant_id>/remove")
def remove_cart_item(variant_id):
    """Remove one product option from the cart."""
    try:
        updated_cart = _order_service().remove_from_cart(_cart(), variant_id)
    except ValueError as error:
        flash(str(error), "error")
    else:
        _save_cart(updated_cart)
        flash("Item removed from cart.", "success")

    return redirect(url_for("shop.cart"))
