"""Shared test data for catalog and order business-logic tests."""

from copy import deepcopy

import pytest

from app.db import initialize_database


class FakeCatalog:
    """Small in-memory catalog that implements the three order seam methods."""

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
def database_path(tmp_path):
    """Create the application schema in a separate SQLite file per test."""
    path = tmp_path / "shop.db"
    initialize_database(path)
    return path


@pytest.fixture
def catalog_data():
    """Provide two catalog snapshots that an order service can safely copy."""
    return {
        1: {
            "variant_id": 1,
            "product_name": "Keychain",
            "option_label": "Blue",
            "unit_price_cents": 500,
            "stock": 3,
        },
        2: {
            "variant_id": 2,
            "product_name": "Keychain",
            "option_label": "Red",
            "unit_price_cents": 700,
            "stock": 2,
        },
    }


@pytest.fixture
def fake_catalog(catalog_data):
    """Provide the fake catalog used by cart and checkout tests."""
    return FakeCatalog(catalog_data)
