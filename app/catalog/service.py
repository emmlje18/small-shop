"""Catalog rules and the small interface used by the orders domain."""

from app.catalog import repository


class CatalogService:
    """Apply catalog validation before data reaches SQLite."""

    def __init__(self, database_path):
        self.database_path = database_path

    def add_product(self, name, description, price_cents, image_path=None):
        """Validate and save a product with its price in cents."""
        clean_name = name.strip() if isinstance(name, str) else ""
        if not clean_name:
            raise ValueError("Product name is required.")
        if not self._is_nonnegative_integer(price_cents):
            raise ValueError("Price must be a nonnegative integer number of cents.")
        if not isinstance(description, str):
            raise ValueError("Description must be text.")
        return repository.create_product(
            self.database_path,
            clean_name,
            description.strip(),
            price_cents,
            image_path,
        )

    def list_products(self):
        """List active products for the storefront."""
        return repository.list_products(self.database_path)

    def get_product(self, product_id):
        """Return one active product for a public product page."""
        if not self._is_positive_integer(product_id):
            return None
        return repository.get_product(self.database_path, product_id)

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
            self.database_path, product_id, clean_label, stock
        )

    def list_variants(self, product_id):
        """List options and stock for one product."""
        return repository.list_variants(self.database_path, product_id)

    def get_variant_snapshot(self, variant_id):
        """Return the stable catalog details an order must copy."""
        return repository.get_variant_snapshot(self.database_path, variant_id)

    def decrement_stock(self, variant_id, quantity):
        """Atomically reserve stock if the requested quantity is available."""
        if not self._is_positive_integer(variant_id):
            return False
        if not self._is_positive_integer(quantity):
            return False
        return repository.decrement_stock(
            self.database_path, variant_id, quantity
        )

    def restore_stock(self, variant_id, quantity):
        """Return reserved stock after an order cannot be completed."""
        if not self._is_positive_integer(variant_id):
            return
        if not self._is_positive_integer(quantity):
            return
        repository.restore_stock(self.database_path, variant_id, quantity)

    @staticmethod
    def _is_nonnegative_integer(value):
        """Reject booleans because Python treats them as integers."""
        return isinstance(value, int) and not isinstance(value, bool) and value >= 0

    @staticmethod
    def _is_positive_integer(value):
        """Check ids and quantities that must be greater than zero."""
        return isinstance(value, int) and not isinstance(value, bool) and value > 0
