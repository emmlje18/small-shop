"""SQL Server queries for products and product variants.

Ported from the Assignment 1 SQLite repository. Each function is one
transaction (see db.transaction). Values are always passed as parameters
(%s), never pasted into the SQL text, so input cannot change the query.
"""

from catalog.db import transaction

# has_image says whether a picture exists without loading its bytes;
# image_version goes up each time the picture is replaced (migration 004).
PRODUCT_COLUMNS = """id, name, description, price_cents, is_active, created_at, image_version,
    CAST(CASE WHEN image_data IS NULL THEN 0 ELSE 1 END AS BIT) AS has_image"""


def create_product(database_url, name, description, price_cents):
    """Save one product and return its new database id."""
    with transaction(database_url) as cursor:
        # OUTPUT INSERTED.id returns the id SQL Server just generated
        # (SQLite used cursor.lastrowid for this).
        cursor.execute(
            """INSERT INTO products (name, description, price_cents)
               OUTPUT INSERTED.id
               VALUES (%s, %s, %s)""",
            (name, description, price_cents),
        )
        return cursor.fetchone()["id"]


def list_products(database_url):
    """Return active products in a predictable display order."""
    with transaction(database_url) as cursor:
        cursor.execute(
            f"SELECT {PRODUCT_COLUMNS} FROM products WHERE is_active = 1 ORDER BY id"
        )
        return cursor.fetchall()


def get_product(database_url, product_id):
    """Return one active product for the public catalog, or None."""
    with transaction(database_url) as cursor:
        cursor.execute(
            f"SELECT {PRODUCT_COLUMNS} FROM products WHERE id = %s AND is_active = 1",
            (product_id,),
        )
        return cursor.fetchone()


def get_product_for_admin(database_url, product_id):
    """Return one product for editing, including an inactive product if needed."""
    with transaction(database_url) as cursor:
        cursor.execute(
            f"SELECT {PRODUCT_COLUMNS} FROM products WHERE id = %s", (product_id,)
        )
        return cursor.fetchone()


def update_product(database_url, product_id, name, description, price_cents):
    """Update the editable fields for one existing product."""
    with transaction(database_url) as cursor:
        cursor.execute(
            """UPDATE products
               SET name = %s, description = %s, price_cents = %s
               WHERE id = %s""",
            (name, description, price_cents, product_id),
        )
        return cursor.rowcount == 1


def deactivate_product(database_url, product_id):
    """Hide one product from the storefront without deleting old order snapshots."""
    with transaction(database_url) as cursor:
        cursor.execute(
            "UPDATE products SET is_active = 0 WHERE id = %s AND is_active = 1",
            (product_id,),
        )
        return cursor.rowcount == 1


def create_variant(database_url, product_id, option_label, stock):
    """Save one product option and return its new database id."""
    with transaction(database_url) as cursor:
        cursor.execute(
            """INSERT INTO product_variants (product_id, option_label, stock)
               OUTPUT INSERTED.id
               VALUES (%s, %s, %s)""",
            (product_id, option_label, stock),
        )
        return cursor.fetchone()["id"]


def update_variant(database_url, product_id, variant_id, option_label, stock):
    """Update one option only when it belongs to the selected product."""
    with transaction(database_url) as cursor:
        cursor.execute(
            """UPDATE product_variants
               SET option_label = %s, stock = %s
               WHERE id = %s AND product_id = %s""",
            (option_label, stock, variant_id, product_id),
        )
        return cursor.rowcount == 1


def remove_variant_from_sale(database_url, product_id, variant_id):
    """Set an option's stock to zero without deleting its purchase history link."""
    with transaction(database_url) as cursor:
        cursor.execute(
            "UPDATE product_variants SET stock = 0 WHERE id = %s AND product_id = %s",
            (variant_id, product_id),
        )
        return cursor.rowcount == 1


def list_variants(database_url, product_id):
    """Return the options belonging to one product."""
    with transaction(database_url) as cursor:
        cursor.execute(
            """SELECT id, product_id, option_label, stock
               FROM product_variants WHERE product_id = %s ORDER BY id""",
            (product_id,),
        )
        return cursor.fetchall()


def get_variant_snapshot(database_url, variant_id):
    """Read the product details orders need to save at purchase time."""
    with transaction(database_url) as cursor:
        cursor.execute(
            """SELECT v.id AS variant_id, p.name AS product_name,
                      v.option_label, p.price_cents AS unit_price_cents, v.stock
               FROM product_variants AS v
               JOIN products AS p ON p.id = v.product_id
               WHERE v.id = %s AND p.is_active = 1""",
            (variant_id,),
        )
        return cursor.fetchone()


def set_product_image(database_url, product_id, image_data, content_type):
    """Store an uploaded picture on the product row, replacing any earlier one."""
    with transaction(database_url) as cursor:
        cursor.execute(
            """UPDATE products SET image_data = %s, image_content_type = %s,
                      image_version = image_version + 1
               WHERE id = %s""",
            (image_data, content_type, product_id),
        )
        return cursor.rowcount == 1


def get_product_image(database_url, product_id):
    """Return {"image_data", "image_content_type"} for an active product, or None."""
    with transaction(database_url) as cursor:
        cursor.execute(
            """SELECT image_data, image_content_type FROM products
               WHERE id = %s AND is_active = 1 AND image_data IS NOT NULL""",
            (product_id,),
        )
        return cursor.fetchone()


def get_variant_image(database_url, variant_id):
    """Return the picture of the product an option belongs to, or None."""
    with transaction(database_url) as cursor:
        cursor.execute(
            """SELECT p.image_data, p.image_content_type
               FROM product_variants AS v
               JOIN products AS p ON p.id = v.product_id
               WHERE v.id = %s AND p.is_active = 1 AND p.image_data IS NOT NULL""",
            (variant_id,),
        )
        return cursor.fetchone()


def decrement_stock(database_url, variant_id, quantity):
    """Reduce stock only when enough units remain.

    One UPDATE both checks and subtracts, so two buyers cannot both take the
    last unit: the second UPDATE finds stock < quantity and changes no row.
    """
    with transaction(database_url) as cursor:
        cursor.execute(
            """UPDATE product_variants SET stock = stock - %s
               WHERE id = %s AND stock >= %s""",
            (quantity, variant_id, quantity),
        )
        return cursor.rowcount == 1


def restore_stock(database_url, variant_id, quantity):
    """Add units back after a checkout is cancelled or payment fails."""
    with transaction(database_url) as cursor:
        cursor.execute(
            "UPDATE product_variants SET stock = stock + %s WHERE id = %s",
            (quantity, variant_id),
        )
