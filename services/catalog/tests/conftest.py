"""Shared fixtures: a throwaway SQL Server database built by the real migrations.

TEST_DATABASE_URL must point at a database whose name ends in "_test"; it is
dropped and recreated at the start of every test run, so it can never be the
service's real database. Locally `docker compose run --rm catalog-tests` sets
it; in CI a SQL Server service container provides it.
"""

import os

import pymssql
import pytest

from catalog import create_app
from catalog.db import connection_settings, transaction
from catalog.migrate import migrate

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "mssql+pymssql://sa:LocalDev_Sa_Pass1@localhost:14330/catalog_test",
)


@pytest.fixture(scope="session")
def database_url():
    """Create an empty test database once per run and apply every migration."""
    settings = connection_settings(TEST_DATABASE_URL)
    name = settings["database"]
    if not name.endswith("_test"):
        raise RuntimeError(f"Refusing to recreate {name!r}: test databases must end in _test")

    # CREATE/DROP DATABASE cannot run inside a transaction, hence autocommit.
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
    """Give each test empty tables, so tests cannot affect one another."""
    with transaction(database_url) as cursor:
        cursor.execute("DELETE FROM product_variants; DELETE FROM products; DELETE FROM health_check;")
    return database_url


@pytest.fixture
def app(db):
    """The catalog Flask app wired to the test database with known secrets."""
    return create_app({
        "DATABASE_URL": db,
        "ADMIN_PASSWORD": "test-admin",
        "INTERNAL_TOKEN": "test-internal",
        "CORS_ORIGINS": "http://ui.test",
        "TESTING": True,
    })


@pytest.fixture
def client(app):
    """Sends HTTP requests to the app without starting a server."""
    return app.test_client()


ADMIN = {"Authorization": "Bearer test-admin"}
INTERNAL = {"X-Internal-Token": "test-internal"}
