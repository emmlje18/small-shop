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


def parse_variants(option_labels, stock_values):
    """Validate matching option and stock fields from the product form."""
    if len(option_labels) != len(stock_values):
        raise ValueError("Each option needs a matching stock value.")

    variants = []
    for position, (option_label, stock_value) in enumerate(
        zip(option_labels, stock_values), start=1
    ):
        clean_label = option_label.strip()
        if not clean_label:
            raise ValueError(f"Option {position} needs a label.")
        stock = parse_nonnegative_integer(stock_value, f"Stock for option {position}")
        variants.append({"option_label": clean_label, "stock": stock})

    if not variants:
        raise ValueError("Add at least one option.")
    return variants


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
    """Validate and save a product, its options, and an optional image."""
    if request.method == "POST":
        name = request.form.get("name", "")
        description = request.form.get("description", "")
        image_path = None

        try:
            price_cents = parse_price_cents(request.form.get("price", ""))
            variants = parse_variants(
                request.form.getlist("option_label"),
                request.form.getlist("stock"),
            )
            image_path = save_uploaded_image(
                request.files.get("image"), current_app.config["UPLOAD_DIR"]
            )
            catalog = _catalog_service()
            product_id = catalog.add_product(
                name, description, price_cents, image_path
            )
            for variant in variants:
                catalog.add_variant(
                    product_id, variant["option_label"], variant["stock"]
                )
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


@admin_blueprint.route("/products/<int:product_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_product(product_id):
    """Show and update one product without changing its existing options."""
    catalog = _catalog_service()
    product = catalog.get_product_for_admin(product_id)
    if product is None:
        return render_template("shop/not_found.html"), 404

    if request.method == "POST":
        image_path = product["image_path"]
        new_image_path = None
        try:
            price_cents = parse_price_cents(request.form.get("price", ""))
            new_image_path = save_uploaded_image(
                request.files.get("image"), current_app.config["UPLOAD_DIR"]
            )
            if new_image_path:
                image_path = new_image_path
            catalog.update_product(
                product_id,
                request.form.get("name", ""),
                request.form.get("description", ""),
                price_cents,
                image_path,
            )
        except ValueError as error:
            if new_image_path:
                (Path(current_app.config["UPLOAD_DIR"]) / new_image_path).unlink(
                    missing_ok=True
                )
            flash(str(error), "error")
        else:
            flash("Product updated.", "success")
            return redirect(url_for("admin.products"))

    product["variants"] = catalog.list_variants(product_id)
    return render_template("admin/edit_product.html", product=product)


@admin_blueprint.post("/products/<int:product_id>/variants")
@admin_required
def add_product_variant(product_id):
    """Add one more option to an existing product from its edit page."""
    try:
        stock = parse_nonnegative_integer(request.form.get("stock"), "Stock")
        _catalog_service().add_variant(
            product_id, request.form.get("option_label", ""), stock
        )
    except ValueError as error:
        flash(str(error), "error")
    else:
        flash("Option added.", "success")
    return redirect(url_for("admin.edit_product", product_id=product_id))


@admin_blueprint.post("/products/<int:product_id>/variants/<int:variant_id>")
@admin_required
def update_product_variant(product_id, variant_id):
    """Update one existing option label and stock number from the edit page."""
    try:
        stock = parse_nonnegative_integer(request.form.get("stock"), "Stock")
        updated = _catalog_service().update_variant(
            product_id, variant_id, request.form.get("option_label", ""), stock
        )
        if not updated:
            raise ValueError("This option does not belong to the product.")
    except ValueError as error:
        flash(str(error), "error")
    else:
        flash("Option updated.", "success")
    return redirect(url_for("admin.edit_product", product_id=product_id))


@admin_blueprint.post("/products/<int:product_id>/variants/<int:variant_id>/remove")
@admin_required
def remove_product_variant(product_id, variant_id):
    """Make one option unavailable without deleting its database record."""
    removed = _catalog_service().remove_variant_from_sale(product_id, variant_id)
    if removed:
        flash("Option removed from sale.", "success")
    else:
        flash("This option does not belong to the product.", "error")
    return redirect(url_for("admin.edit_product", product_id=product_id))


@admin_blueprint.post("/products/<int:product_id>/delete")
@admin_required
def delete_product(product_id):
    """Deactivate a product so existing order snapshots remain valid."""
    if _catalog_service().deactivate_product(product_id):
        flash("Product removed from the storefront.", "success")
    else:
        flash("This product was already removed or does not exist.", "error")
    return redirect(url_for("admin.products"))


@admin_blueprint.get("/uploads/<filename>")
@admin_required
def uploaded_file(filename):
    """Send an uploaded catalog image to the signed-in admin browser."""
    return send_from_directory(current_app.config["UPLOAD_DIR"], filename)
