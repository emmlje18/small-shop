"""SQLite queries for orders and order items."""

from app.db import database_connection


def create_pending_order(database_path, customer_name, customer_email, total_cents, items):
    """Save a pending order and its purchase snapshots in one transaction."""
    with database_connection(database_path) as connection:
        cursor = connection.execute(
            """INSERT INTO orders
               (customer_name, customer_email, status, total_cents)
               VALUES (?, ?, 'pending', ?)""",
            (customer_name, customer_email, total_cents),
        )
        order_id = cursor.lastrowid

        for item in items:
            connection.execute(
                """INSERT INTO order_items
                   (order_id, variant_id, product_name, option_label,
                    unit_price_cents, quantity)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    order_id,
                    item["variant_id"],
                    item["product_name"],
                    item["option_label"],
                    item["unit_price_cents"],
                    item["quantity"],
                ),
            )
        return order_id


def update_order_status(database_path, order_id, new_status, allowed_old_statuses, payment_ref=None):
    """Change an order only when its current status allows the transition."""
    placeholders = ", ".join("?" for _ in allowed_old_statuses)
    with database_connection(database_path) as connection:
        if payment_ref is None:
            cursor = connection.execute(
                f"""UPDATE orders SET status = ?
                    WHERE id = ? AND status IN ({placeholders})""",
                (new_status, order_id, *allowed_old_statuses),
            )
        else:
            cursor = connection.execute(
                f"""UPDATE orders SET status = ?, payment_ref = ?
                    WHERE id = ? AND status IN ({placeholders})""",
                (new_status, payment_ref, order_id, *allowed_old_statuses),
            )
        return cursor.rowcount == 1


def get_order(database_path, order_id):
    """Return one order row, or None when its id does not exist."""
    with database_connection(database_path) as connection:
        row = connection.execute(
            """SELECT id, customer_name, customer_email, status, total_cents,
                      payment_ref, created_at
               FROM orders WHERE id = ?""",
            (order_id,),
        ).fetchone()
        return dict(row) if row is not None else None


def get_order_items(database_path, order_id):
    """Return saved purchase snapshots for one order."""
    with database_connection(database_path) as connection:
        rows = connection.execute(
            """SELECT variant_id, product_name, option_label, unit_price_cents,
                      quantity
               FROM order_items WHERE order_id = ? ORDER BY id""",
            (order_id,),
        ).fetchall()
        return [dict(row) for row in rows]
