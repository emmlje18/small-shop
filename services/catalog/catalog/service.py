"""Catalog rules and the small interface used by the orders domain."""

from catalog import repository

MAX_IMAGE_BYTES = 5 * 1024 * 1024
IMAGE_TYPES = {
    "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
    "gif": "image/gif", "webp": "image/webp",
}


class CatalogService:
    """Apply catalog validation before data reaches SQLite."""

    def __init__(self, database_url):
        self.database_url = database_url

    def add_product(self, name, description, price_cents):
        """Validate and save a product with its price in cents."""
        clean_name = name.strip() if isinstance(name, str) else ""
        if not clean_name:
            raise ValueError("Product name is required.")
        if not self._is_nonnegative_integer(price_cents):
            raise ValueError("Price must be a nonnegative integer number of cents.")
        if not isinstance(description, str):
            raise ValueError("Description must be text.")
        return repository.create_product(
            self.database_url,
            clean_name,
            description.strip(),
            price_cents,
        )

    def list_products(self):
        """List active products for the storefront."""
        return repository.list_products(self.database_url)

    def get_product(self, product_id):
        """Return one active product for a public product page."""
        if not self._is_positive_integer(product_id):
            return None
        return repository.get_product(self.database_url, product_id)

    def get_product_for_admin(self, product_id):
        """Return one product for the protected edit page."""
        if not self._is_positive_integer(product_id):
            return None
        return repository.get_product_for_admin(self.database_url, product_id)

    def update_product(self, product_id, name, description, price_cents):
        """Validate and update one product's name, description and price."""
        clean_name = name.strip() if isinstance(name, str) else ""
        if not self._is_positive_integer(product_id):
            raise ValueError("Product id must be a positive integer.")
        if not clean_name:
            raise ValueError("Product name is required.")
        if not self._is_nonnegative_integer(price_cents):
            raise ValueError("Price must be a nonnegative integer number of cents.")
        if not isinstance(description, str):
            raise ValueError("Description must be text.")
        return repository.update_product(
            self.database_url,
            product_id,
            clean_name,
            description.strip(),
            price_cents,
        )

    def deactivate_product(self, product_id):
        """Remove an active product from customer pages without deleting it."""
        if not self._is_positive_integer(product_id):
            return False
        return repository.deactivate_product(self.database_url, product_id)

    def add_variant(self, product_id, option_label, stock):
        """Validate and save a stock option for an existing product."""
        clean_label = option_label.strip() if isinstance(option_label, str) else ""
        if not clean_label:
            raise ValueError("Option label is required.")
        if not self._is_positive_integer(product_id):
            raise ValueError("Product id must be a positive integer.")
        if not self._is_nonnegative_integer(stock):
            raise ValueError("Stock must be a nonnegative integer.")
        return repository.create_variant(
            self.database_url, product_id, clean_label, stock
        )

    def update_variant(self, product_id, variant_id, option_label, stock):
        """Validate and update an existing product option and its stock level."""
        clean_label = option_label.strip() if isinstance(option_label, str) else ""
        if not self._is_positive_integer(product_id):
            raise ValueError("Product id must be a positive integer.")
        if not self._is_positive_integer(variant_id):
            raise ValueError("Option id must be a positive integer.")
        if not clean_label:
            raise ValueError("Option label is required.")
        if not self._is_nonnegative_integer(stock):
            raise ValueError("Stock must be a nonnegative integer.")
        return repository.update_variant(
            self.database_url, product_id, variant_id, clean_label, stock
        )

    def remove_variant_from_sale(self, product_id, variant_id):
        """Make an option unavailable while preserving its variant id for orders."""
        if not self._is_positive_integer(product_id):
            return False
        if not self._is_positive_integer(variant_id):
            return False
        return repository.remove_variant_from_sale(
            self.database_url, product_id, variant_id
        )

    def list_variants(self, product_id):
        """List options and stock for one product."""
        return repository.list_variants(self.database_url, product_id)

    def get_variant_snapshot(self, variant_id):
        """Return the stable catalog details an order must copy."""
        return repository.get_variant_snapshot(self.database_url, variant_id)

    def set_product_image(self, product_id, filename, image_data):
        """Validate an uploaded picture by extension and size, then store it."""
        if not self._is_positive_integer(product_id):
            raise ValueError("Product id must be a positive integer.")
        extension = filename.rsplit(".", 1)[-1].lower() if "." in (filename or "") else ""
        content_type = IMAGE_TYPES.get(extension)
        if content_type is None:
            raise ValueError("Allowed image types are JPG, PNG, GIF, and WebP.")
        if not image_data:
            raise ValueError("The image file is empty.")
        if len(image_data) > MAX_IMAGE_BYTES:
            raise ValueError("Image uploads must be smaller than 5 MB.")
        return repository.set_product_image(
            self.database_url, product_id, image_data, content_type
        )

    def get_product_image(self, product_id):
        """Return the stored picture of an active product, or None."""
        if not self._is_positive_integer(product_id):
            return None
        return repository.get_product_image(self.database_url, product_id)

    def get_variant_image(self, variant_id):
        """Return the picture of the product an option belongs to, or None."""
        if not self._is_positive_integer(variant_id):
            return None
        return repository.get_variant_image(self.database_url, variant_id)

    def decrement_stock(self, variant_id, quantity):
        """Atomically reserve stock if the requested quantity is available."""
        if not self._is_positive_integer(variant_id):
            return False
        if not self._is_positive_integer(quantity):
            return False
        return repository.decrement_stock(
            self.database_url, variant_id, quantity
        )

    def restore_stock(self, variant_id, quantity):
        """Return reserved stock after an order cannot be completed."""
        if not self._is_positive_integer(variant_id):
            return
        if not self._is_positive_integer(quantity):
            return
        repository.restore_stock(self.database_url, variant_id, quantity)

    @staticmethod
    def _is_nonnegative_integer(value):
        """Reject booleans because Python treats them as integers."""
        return isinstance(value, int) and not isinstance(value, bool) and value >= 0

    @staticmethod
    def _is_positive_integer(value):
        """Check ids and quantities that must be greater than zero."""
        return isinstance(value, int) and not isinstance(value, bool) and value > 0
