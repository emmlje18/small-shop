"""Public catalog pages owned by the catalog domain."""

from flask import Blueprint, current_app, render_template, send_from_directory

from app.catalog.service import CatalogService


catalog_blueprint = Blueprint("catalog", __name__)


def _catalog_service():
    """Create the catalog service using this app's configured database."""
    return CatalogService(current_app.config["DATABASE_PATH"])


@catalog_blueprint.get("/")
def product_list():
    """Show all active products that customers can browse."""
    products = _catalog_service().list_products()
    return render_template("shop/products.html", products=products)


@catalog_blueprint.get("/products/<int:product_id>")
def product_detail(product_id):
    """Show one active product and the options a customer can select."""
    catalog = _catalog_service()
    product = catalog.get_product(product_id)
    if product is None:
        return render_template("shop/not_found.html"), 404

    variants = catalog.list_variants(product_id)
    return render_template(
        "shop/product_detail.html",
        product=product,
        variants=variants,
        has_available_variants=any(variant["stock"] > 0 for variant in variants),
    )


@catalog_blueprint.get("/uploads/<filename>")
def uploaded_file(filename):
    """Send a catalog image to a customer browser."""
    return send_from_directory(current_app.config["UPLOAD_DIR"], filename)


@catalog_blueprint.get("/variant-images/<int:variant_id>")
def variant_image(variant_id):
    """Send an option's product image, or a placeholder when it has none."""
    image_path = _catalog_service().get_variant_image_path(variant_id)
    if image_path:
        return send_from_directory(current_app.config["UPLOAD_DIR"], image_path)
    return send_from_directory(current_app.static_folder, "product-placeholder.svg")
