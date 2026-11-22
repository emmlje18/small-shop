"""Shared fixtures: a throwaway orders database, a fake catalog, and a stub catalog server.

TEST_DATABASE_URL must name a database ending in "_test"; it is dropped and
recreated at the start of every run, so it can never be the real database.
"""

import os
import threading
import time
from copy import deepcopy

import pymssql
import pytest
from flask import Flask, jsonify, request
from werkzeug.serving import make_server

from orders import create_app
from orders.db import connection_settings, transaction
from orders.migrate import migrate

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "mssql+pymssql://sa:LocalDev_Sa_Pass1@localhost:14330/orders_test",
)
STUB_TOKEN = "stub-internal-token"


@pytest.fixture(scope="session")
def database_url():
    """Create an empty test database once per run and apply every migration."""
    settings = connection_settings(TEST_DATABASE_URL)
    name = settings["database"]
    if not name.endswith("_test"):
        raise RuntimeError(f"Refusing to recreate {name!r}: test databases must end in _test")
    admin = pymssql.connect(**{**settings, "database": "master"}, autocommit=True, login_timeout=30)
    cursor = admin.cursor()
    cursor.execute(
        f"""IF DB_ID(N'{name}') IS NOT NULL
            BEGIN
                ALTER DATABASE [{name}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
                DROP DATABASE [{name}];
            END"""
    )
    cursor.execute(f"CREATE DATABASE [{name}]")
    admin.close()
    connection = pymssql.connect(**settings)
    try:
        migrate(connection)
    finally:
        connection.close()
    return TEST_DATABASE_URL


@pytest.fixture
def db(database_url):
    """Empty tables before each test."""
    with transaction(database_url) as cursor:
        cursor.execute("DELETE FROM order_items; DELETE FROM orders; DELETE FROM health_check;")
    return database_url


SNAPSHOTS = {
    1: {"variant_id": 1, "product_name": "Keychain", "option_label": "Blue", "unit_price_cents": 500, "stock": 3},
    2: {"variant_id": 2, "product_name": "Keychain", "option_label": "Red", "unit_price_cents": 700, "stock": 2},
}


class FakeCatalog:
    """In-memory stand-in with the three seam methods (as in Assignment 1)."""

    def __init__(self, snapshots):
        self.snapshots = deepcopy(snapshots)

    def get_variant_snapshot(self, variant_id):
        snapshot = self.snapshots.get(variant_id)
        return deepcopy(snapshot) if snapshot is not None else None

    def decrement_stock(self, variant_id, quantity):
        snapshot = self.snapshots.get(variant_id)
        if snapshot is None or snapshot["stock"] < quantity:
            return False
        snapshot["stock"] -= quantity
        return True

    def restore_stock(self, variant_id, quantity):
        self.snapshots[variant_id]["stock"] += quantity


@pytest.fixture
def fake_catalog():
    return FakeCatalog(SNAPSHOTS)


def build_stub_catalog(state):
    """A tiny Flask app that behaves like the catalog's /internal endpoints.

    It follows services/catalog/openapi.yaml: same paths, token header, body
    and status codes (200, 400, 401, 404, 409). state["delay_s"] makes it slow.
    """
    stub = Flask("stub_catalog")

    def guarded(handler):
        def wrapper(variant_id):
            time.sleep(state.get("delay_s", 0))
            state["calls"].append((request.method, request.path))
            if request.headers.get("X-Internal-Token") != STUB_TOKEN:
                return jsonify(error="Internal token required."), 401
            return handler(variant_id)
        wrapper.__name__ = handler.__name__
        return wrapper

    def quantity():
        value = (request.get_json(silent=True) or {}).get("quantity")
        return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None

    @stub.get("/internal/variants/<int:variant_id>")
    @guarded
    def snapshot(variant_id):
        if variant_id not in state["stock"]:
            return jsonify(error="Variant not found."), 404
        return jsonify({**SNAPSHOTS[variant_id], "stock": state["stock"][variant_id]})

    @stub.post("/internal/variants/<int:variant_id>/decrement")
    @guarded
    def decrement(variant_id):
        qty = quantity()
        if qty is None:
            return jsonify(error="Quantity must be a positive whole number."), 400
        if state["stock"].get(variant_id, 0) < qty:
            return jsonify(error="Not enough stock."), 409
        state["stock"][variant_id] -= qty
        return jsonify(variant_id=variant_id, decremented=qty)

    @stub.post("/internal/variants/<int:variant_id>/restore")
    @guarded
    def restore(variant_id):
        qty = quantity()
        if qty is None:
            return jsonify(error="Quantity must be a positive whole number."), 400
        state["stock"][variant_id] = state["stock"].get(variant_id, 0) + qty
        return jsonify(variant_id=variant_id, restored=qty)

    return stub


@pytest.fixture
def stub_catalog():
    """Run the stub catalog on a free local port in a background thread."""
    state = {"stock": {1: 3, 2: 2}, "calls": [], "delay_s": 0}
    server = make_server("127.0.0.1", 0, build_stub_catalog(state), threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    state["url"] = f"http://127.0.0.1:{server.server_port}"
    yield state
    server.shutdown()


def make_client(db_url, catalog_url, timeout_s=2.0):
    return create_app({
        "DATABASE_URL": db_url,
        "CATALOG_URL": catalog_url,
        "CATALOG_TIMEOUT_S": timeout_s,
        "INTERNAL_TOKEN": STUB_TOKEN,
        "CORS_ORIGINS": "http://ui.test",
        "TESTING": True,
    }).test_client()


@pytest.fixture
def client(db, stub_catalog):
    """Orders app wired to the test database and the stub catalog over HTTP."""
    return make_client(db, stub_catalog["url"])
