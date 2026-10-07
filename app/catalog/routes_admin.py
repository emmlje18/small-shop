"""Admin login and pages for managing catalog products."""

import hmac
from decimal import Decimal, InvalidOperation
from functools import wraps
from pathlib import Path
from uuid import uuid4

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from werkzeug.utils import secure_filename

from app.catalog.service import CatalogService


admin_blueprint = Blueprint("admin", __name__, url_prefix="/admin")
ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp"}


def _catalog_service():
    """Create the catalog service using this app's configured database."""
    return CatalogService(current_app.config["DATABASE_PATH"])


def admin_required(view_function):
    """Send visitors to login unless the admin session is active."""
    @wraps(view_function)
    def check_session(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin.login"))
        return view_function(*args, **kwargs)

    return check_session


def parse_price_cents(value):
    """Convert a nonnegative price with at most two decimals to cents."""
    try:
        amount = Decimal(value.strip())
        rounded_amount = amount.quantize(Decimal("0.01"))
    except (InvalidOperation, AttributeError):
        raise ValueError("Enter a valid price, such as 12.50.") from None

    if not amount.is_finite() or amount < 0 or amount != rounded_amount:
        raise ValueError("Price must be nonnegative and have at most two decimals.")

    return int(rounded_amount * 100)


def parse_nonnegative_integer(value, field_name):
    """Read an integer form value and reject missing or negative values."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be a whole number.") from None

    if number < 0:
        raise ValueError(f"{field_name} cannot be negative.")
    return number


def save_uploaded_image(upload, upload_directory):
    """Save an optional image with a safe unique filename."""
    if upload is None or not upload.filename:
        return None

    safe_original_name = secure_filename(upload.filename)
    if "." not in safe_original_name:
        raise ValueError("Choose an image with an allowed file extension.")

    extension = safe_original_name.rsplit(".", 1)[1].lower()
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValueError("Allowed image types are JPG, PNG, GIF, and WebP.")

    stored_name = f"{uuid4().hex}.{extension}"
    upload.save(Path(upload_directory) / stored_name)
    return stored_name


@admin_blueprint.route("/login", methods=["GET", "POST"])
def login():
    """Check the configured admin password and create a session."""
    if request.method == "POST":
        submitted_password = request.form.get("password", "")
        expected_password = current_app.config["ADMIN_PASSWORD"]
        if hmac.compare_digest(submitted_password, expected_password):
            session.clear()
            session["admin_logged_in"] = True
            return redirect(url_for("admin.products"))

        flash("The password was not correct.", "error")

    return render_template("admin/login.html")


@admin_blueprint.post("/logout")
@admin_required
def logout():
    """Clear the admin session and return to the login page."""
    session.clear()
    return redirect(url_for("admin.login"))


@admin_blueprint.get("/")
@admin_required
def index():
    """Send a signed-in admin to the product list."""
    return redirect(url_for("admin.products"))


@admin_blueprint.get("/products")
@admin_required
def products():
    """Show active products with their variants and stock counts."""
    catalog = _catalog_service()
    product_rows = catalog.list_products()
    for product in product_rows:
        product["variants"] = catalog.list_variants(product["id"])
    return render_template("admin/products.html", products=product_rows)


@admin_blueprint.route("/products/new", methods=["GET", "POST"])
@admin_required
def new_product():
    """Validate and save a product, its first variant, and an optional image."""
    if request.method == "POST":
        name = request.form.get("name", "")
        description = request.form.get("description", "")
        option_label = request.form.get("option_label", "")
        image_path = None

        try:
            price_cents = parse_price_cents(request.form.get("price", ""))
            stock = parse_nonnegative_integer(
                request.form.get("stock", ""), "Stock"
            )
            if not option_label.strip():
                raise ValueError("Variant option is required.")

            image_path = save_uploaded_image(
                request.files.get("image"), current_app.config["UPLOAD_DIR"]
            )
            catalog = _catalog_service()
            product_id = catalog.add_product(
                name, description, price_cents, image_path
            )
            catalog.add_variant(product_id, option_label, stock)
        except ValueError as error:
            if image_path:
                (Path(current_app.config["UPLOAD_DIR"]) / image_path).unlink(
                    missing_ok=True
                )
            flash(str(error), "error")
        else:
            flash("Product added.", "success")
            return redirect(url_for("admin.products"))

    return render_template("admin/new_product.html")


@admin_blueprint.get("/uploads/<filename>")
@admin_required
def uploaded_file(filename):
    """Send an uploaded catalog image to the signed-in admin browser."""
    return send_from_directory(current_app.config["UPLOAD_DIR"], filename)
