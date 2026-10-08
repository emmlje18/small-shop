"""SQLite queries for products and product variants."""

from app.db import database_connection


def create_product(database_path, name, description, price_cents, image_path=None):
    """Save one product and return its new database id."""
    with database_connection(database_path) as connection:
        cursor = connection.execute(
            """INSERT INTO products (name, description, price_cents, image_path)
               VALUES (?, ?, ?, ?)""",
            (name, description, price_cents, image_path),
        )
        return cursor.lastrowid


def list_products(database_path):
    """Return active products in a predictable display order."""
    with database_connection(database_path) as connection:
        rows = connection.execute(
            """SELECT id, name, description, price_cents, image_path,
                      is_active, created_at
               FROM products WHERE is_active = 1 ORDER BY id"""
        ).fetchall()
        return [dict(row) for row in rows]


def get_product(database_path, product_id):
    """Return one active product for the public catalog, or None."""
    with database_connection(database_path) as connection:
        row = connection.execute(
            """SELECT id, name, description, price_cents, image_path,
                      is_active, created_at
               FROM products WHERE id = ? AND is_active = 1""",
            (product_id,),
        ).fetchone()
        return dict(row) if row is not None else None


def create_variant(database_path, product_id, option_label, stock):
    """Save one product option and return its new database id."""
    with database_connection(database_path) as connection:
        cursor = connection.execute(
            """INSERT INTO product_variants (product_id, option_label, stock)
               VALUES (?, ?, ?)""",
            (product_id, option_label, stock),
        )
        return cursor.lastrowid


def list_variants(database_path, product_id):
    """Return the options belonging to one product."""
    with database_connection(database_path) as connection:
        rows = connection.execute(
            """SELECT id, product_id, option_label, stock
               FROM product_variants WHERE product_id = ? ORDER BY id""",
            (product_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def get_variant_snapshot(database_path, variant_id):
    """Read the product details orders need to save at purchase time."""
    with database_connection(database_path) as connection:
        row = connection.execute(
            """SELECT v.id AS variant_id, p.name AS product_name,
                      v.option_label, p.price_cents AS unit_price_cents,
                      v.stock
               FROM product_variants AS v
               JOIN products AS p ON p.id = v.product_id
               WHERE v.id = ? AND p.is_active = 1""",
            (variant_id,),
        ).fetchone()
        return dict(row) if row is not None else None


def decrement_stock(database_path, variant_id, quantity):
    """Reduce stock only when enough units remain."""
    with database_connection(database_path) as connection:
        cursor = connection.execute(
            """UPDATE product_variants SET stock = stock - ?
               WHERE id = ? AND stock >= ?""",
            (quantity, variant_id, quantity),
        )
        return cursor.rowcount == 1


def restore_stock(database_path, variant_id, quantity):
    """Add units back after a checkout is cancelled or payment fails."""
    with database_connection(database_path) as connection:
        connection.execute(
            "UPDATE product_variants SET stock = stock + ? WHERE id = ?",
            (quantity, variant_id),
        )
