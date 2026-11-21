"""SQL Server queries for orders and order items (ported from Assignment 1)."""

from orders.db import transaction


def create_pending_order(database_url, customer_name, customer_email, total_cents, items):
    """Save a pending order and its purchase snapshots in one transaction."""
    with transaction(database_url) as cursor:
        cursor.execute(
            """INSERT INTO orders (customer_name, customer_email, status, total_cents)
               OUTPUT INSERTED.id
               VALUES (%s, %s, 'pending', %s)""",
            (customer_name, customer_email, total_cents),
        )
        order_id = cursor.fetchone()["id"]
        for item in items:
            cursor.execute(
                """INSERT INTO order_items
                   (order_id, variant_id, product_name, option_label, unit_price_cents, quantity)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (
                    order_id, item["variant_id"], item["product_name"],
                    item["option_label"], item["unit_price_cents"], item["quantity"],
                ),
            )
        return order_id


def update_order_status(database_url, order_id, new_status, allowed_old_statuses, payment_ref=None):
    """Change an order only when its current status allows the transition."""
    placeholders = ", ".join("%s" for _ in allowed_old_statuses)
    with transaction(database_url) as cursor:
        if payment_ref is None:
            cursor.execute(
                f"""UPDATE orders SET status = %s
                    WHERE id = %s AND status IN ({placeholders})""",
                (new_status, order_id, *allowed_old_statuses),
            )
        else:
            cursor.execute(
                f"""UPDATE orders SET status = %s, payment_ref = %s
                    WHERE id = %s AND status IN ({placeholders})""",
                (new_status, payment_ref, order_id, *allowed_old_statuses),
            )
        return cursor.rowcount == 1


def get_order(database_url, order_id):
    """Return one order row, or None when its id does not exist."""
    with transaction(database_url) as cursor:
        cursor.execute(
            """SELECT id, customer_name, customer_email, status, total_cents,
                      payment_ref, created_at
               FROM orders WHERE id = %s""",
            (order_id,),
        )
        return cursor.fetchone()


def get_order_items(database_url, order_id):
    """Return saved purchase snapshots for one order."""
    with transaction(database_url) as cursor:
        cursor.execute(
            """SELECT variant_id, product_name, option_label, unit_price_cents, quantity
               FROM order_items WHERE order_id = %s ORDER BY id""",
            (order_id,),
        )
        return cursor.fetchall()
