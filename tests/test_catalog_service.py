"""Tests for catalog validation and atomic stock operations."""

import pytest

from app.catalog.service import CatalogService


def test_product_price_must_be_nonnegative(database_path):
    """Products reject a negative integer-cents price before SQLite is used."""
    service = CatalogService(database_path)

    with pytest.raises(ValueError, match="Price"):
        service.add_product("Keychain", "A small keychain", -1)


def test_variant_stock_must_be_nonnegative(database_path):
    """Variants reject negative stock before SQLite is used."""
    service = CatalogService(database_path)
    product_id = service.add_product("Keychain", "A small keychain", 500)

    with pytest.raises(ValueError, match="Stock"):
        service.add_variant(product_id, "Blue", -1)


def test_decrement_stock_refuses_more_than_available(database_path):
    """The conditional update prevents the stored stock from becoming negative."""
    service = CatalogService(database_path)
    product_id = service.add_product("Keychain", "A small keychain", 500)
    variant_id = service.add_variant(product_id, "Blue", 1)

    assert service.decrement_stock(variant_id, 2) is False
    assert service.get_variant_snapshot(variant_id)["stock"] == 1


def test_decrement_and_restore_stock(database_path):
    """A successful reservation can be returned to the catalog later."""
    service = CatalogService(database_path)
    product_id = service.add_product("Keychain", "A small keychain", 500)
    variant_id = service.add_variant(product_id, "Blue", 2)

    assert service.decrement_stock(variant_id, 2) is True
    service.restore_stock(variant_id, 2)

    assert service.get_variant_snapshot(variant_id)["stock"] == 2
