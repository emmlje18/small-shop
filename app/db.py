"""SQLite connection and schema setup."""

import sqlite3
from pathlib import Path


def connect(database_path):
    """Open a SQLite connection with this app's foreign keys enabled."""
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database(database_path):
    """Create the tables if they are missing, so startup is repeatable."""
    Path(database_path).parent.mkdir(parents=True, exist_ok=True)
    with connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                price_cents INTEGER NOT NULL CHECK (price_cents >= 0),
                image_path TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS product_variants (
                id INTEGER PRIMARY KEY,
                product_id INTEGER NOT NULL REFERENCES products(id),
                option_label TEXT NOT NULL,
                stock INTEGER NOT NULL CHECK (stock >= 0)
            );

            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY,
                customer_name TEXT NOT NULL,
                customer_email TEXT NOT NULL,
                status TEXT NOT NULL CHECK (
                    status IN ('pending', 'paid', 'shipped', 'cancelled')
                ),
                total_cents INTEGER NOT NULL CHECK (total_cents >= 0),
                payment_ref TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS order_items (
                id INTEGER PRIMARY KEY,
                order_id INTEGER NOT NULL REFERENCES orders(id),
                variant_id INTEGER NOT NULL,
                product_name TEXT NOT NULL,
                option_label TEXT NOT NULL,
                unit_price_cents INTEGER NOT NULL CHECK (unit_price_cents >= 0),
                quantity INTEGER NOT NULL CHECK (quantity > 0)
            );
            """
        )
