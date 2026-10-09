"""Cart, checkout, and order status operations."""

from app.orders import repository


class OrderService:
    """Apply cart rules while receiving catalog data through the domain seam."""

    def __init__(self, catalog, payment_provider=None, database_path=None):
        self.catalog = catalog
        self.payment_provider = payment_provider
        self.database_path = database_path

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

    def checkout(self, cart, customer_name, customer_email, card_number):
        """Create, charge, and finish one order while handling stock safely."""
        self._require_checkout_dependencies()
        clean_name = self._clean_customer_name(customer_name)
        clean_email = self._clean_customer_email(customer_email)
        items = self._checkout_items(cart)
        total_cents = sum(item["unit_price_cents"] * item["quantity"] for item in items)

        decremented_lines = []
        for item in items:
            if not self.catalog.decrement_stock(item["variant_id"], item["quantity"]):
                self._restore_lines(decremented_lines)
                raise ValueError("An item sold out before checkout. Your cart was not charged.")
            decremented_lines.append(item)

        try:
            order_id = repository.create_pending_order(
                self.database_path, clean_name, clean_email, total_cents, items
            )
        except Exception:
            self._restore_lines(decremented_lines)
            raise

        payment_ref = self.payment_provider.charge(total_cents, card_number)
        if payment_ref:
            repository.update_order_status(
                self.database_path, order_id, "paid", ("pending",), payment_ref
            )
            return {"success": True, "order_id": order_id}

        self.cancel_order(order_id)
        return {"success": False, "order_id": order_id}

    def cancel_order(self, order_id):
        """Cancel a pending or paid order and return its items to stock."""
        self._require_database_path()
        self._validate_positive_integer(order_id, "Order id")
        changed = repository.update_order_status(
            self.database_path, order_id, "cancelled", ("pending", "paid")
        )
        if not changed:
            raise ValueError("This order cannot be cancelled.")

        self._restore_lines(repository.get_order_items(self.database_path, order_id))

    def mark_shipped(self, order_id):
        """Mark a paid order as shipped; other status changes are refused."""
        self._require_database_path()
        self._validate_positive_integer(order_id, "Order id")
        changed = repository.update_order_status(
            self.database_path, order_id, "shipped", ("paid",)
        )
        if not changed:
            raise ValueError("Only a paid order can be marked as shipped.")

    def _get_available_snapshot(self, variant_id):
        """Find an active option or explain why it cannot enter the cart."""
        snapshot = self.catalog.get_variant_snapshot(variant_id)
        if snapshot is None:
            raise ValueError("This product option is no longer available.")
        return snapshot

    def _checkout_items(self, cart):
        """Take fresh snapshots so an order never trusts old session prices."""
        cart_lines = self._copy_cart(cart)
        if not cart_lines:
            raise ValueError("Your cart is empty.")

        items = []
        for line in cart_lines:
            self._validate_positive_integer(line["variant_id"], "Variant id")
            self._validate_positive_integer(line["qty"], "Quantity")
            snapshot = self._get_available_snapshot(line["variant_id"])
            items.append({**snapshot, "quantity": line["qty"]})
        return items

    def _restore_lines(self, lines):
        """Return every listed quantity to catalog stock after a failed checkout."""
        for line in lines:
            self.catalog.restore_stock(line["variant_id"], line["quantity"])

    def _require_checkout_dependencies(self):
        """Ensure checkout has the injected collaborators it needs."""
        self._require_database_path()
        if self.payment_provider is None:
            raise RuntimeError("A payment provider is required for checkout.")

    def _require_database_path(self):
        """Keep cart-only tests independent from the SQLite order repository."""
        if self.database_path is None:
            raise RuntimeError("A database path is required for order operations.")

    @staticmethod
    def _clean_customer_name(value):
        """Require a readable guest name for the saved order."""
        clean_value = value.strip() if isinstance(value, str) else ""
        if not clean_value:
            raise ValueError("Your name is required.")
        return clean_value

    @staticmethod
    def _clean_customer_email(value):
        """Perform a small check before storing the guest email address."""
        clean_value = value.strip() if isinstance(value, str) else ""
        if "@" not in clean_value or clean_value.startswith("@"):
            raise ValueError("Enter a valid email address.")
        return clean_value

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
