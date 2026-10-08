"""Cart operations and later checkout and order status operations."""


class OrderService:
    """Apply cart rules while receiving catalog data through the domain seam."""

    def __init__(self, catalog, payment_provider=None):
        self.catalog = catalog
        self.payment_provider = payment_provider

    def add_to_cart(self, cart, variant_id, quantity):
        """Add units to a cart, merging a line for the same product option."""
        self._validate_positive_integer(variant_id, "Variant id")
        self._validate_positive_integer(quantity, "Quantity")
        snapshot = self._get_available_snapshot(variant_id)
        updated_cart = self._copy_cart(cart)

        for line in updated_cart:
            if line["variant_id"] == variant_id:
                new_quantity = line["qty"] + quantity
                self._check_stock(snapshot, new_quantity)
                line["qty"] = new_quantity
                return updated_cart

        self._check_stock(snapshot, quantity)
        updated_cart.append({"variant_id": variant_id, "qty": quantity})
        return updated_cart

    def set_cart_quantity(self, cart, variant_id, quantity):
        """Replace a cart line's quantity after checking current stock."""
        self._validate_positive_integer(variant_id, "Variant id")
        self._validate_positive_integer(quantity, "Quantity")
        snapshot = self._get_available_snapshot(variant_id)
        self._check_stock(snapshot, quantity)
        updated_cart = self._copy_cart(cart)

        for line in updated_cart:
            if line["variant_id"] == variant_id:
                line["qty"] = quantity
                return updated_cart

        raise ValueError("This option is not in the cart.")

    def remove_from_cart(self, cart, variant_id):
        """Return a copy of the cart without one product option."""
        self._validate_positive_integer(variant_id, "Variant id")
        return [
            line for line in self._copy_cart(cart)
            if line["variant_id"] != variant_id
        ]

    def cart_summary(self, cart):
        """Build display-ready cart lines and a total using current prices."""
        items = []
        total_cents = 0

        for line in self._copy_cart(cart):
            snapshot = self.catalog.get_variant_snapshot(line["variant_id"])
            if snapshot is None:
                continue

            line_total_cents = snapshot["unit_price_cents"] * line["qty"]
            items.append(
                {
                    **snapshot,
                    "quantity": line["qty"],
                    "line_total_cents": line_total_cents,
                    "has_enough_stock": line["qty"] <= snapshot["stock"],
                }
            )
            total_cents += line_total_cents

        return {"items": items, "total_cents": total_cents}

    def _get_available_snapshot(self, variant_id):
        """Find an active option or explain why it cannot enter the cart."""
        snapshot = self.catalog.get_variant_snapshot(variant_id)
        if snapshot is None:
            raise ValueError("This product option is no longer available.")
        return snapshot

    @staticmethod
    def _check_stock(snapshot, quantity):
        """Prevent a cart from requesting more units than are available now."""
        if quantity > snapshot["stock"]:
            raise ValueError("There are not enough items in stock.")

    @staticmethod
    def _copy_cart(cart):
        """Copy session data so callers keep control of their original list."""
        return [
            {"variant_id": line["variant_id"], "qty": line["qty"]}
            for line in cart
        ]

    @staticmethod
    def _validate_positive_integer(value, field_name):
        """Reject invalid ids and quantities before using them in cart logic."""
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise ValueError(f"{field_name} must be a positive whole number.")
