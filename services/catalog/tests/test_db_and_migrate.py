"""Connection settings, connection retries and the migration runner."""

import pymssql
import pytest

from catalog import db
from catalog.db import transaction
from catalog.migrate import MIGRATIONS_DIR, migrate, pending_migrations, split_batches


def test_connection_settings_parse_the_url():
    settings = db.connection_settings("mssql+pymssql://user:p%40ss@host:1444/shop_db")
    assert settings == {"server": "host", "port": "1444", "user": "user",
                        "password": "p@ss", "database": "shop_db"}
    assert db.connection_settings("mssql://u:p@h/d")["port"] == "1433"


def test_connection_settings_reject_other_schemes():
    with pytest.raises(ValueError):
        db.connection_settings("postgres://u:p@h/d")


def test_connect_retries_then_succeeds(monkeypatch):
    """A paused database fails a few times, then connects: no error reaches the caller."""
    calls, sleeps = [], []

    def fake_connect(**kwargs):
        calls.append(kwargs)
        if len(calls) < 3:
            raise pymssql.OperationalError("40613 database is not currently available")
        return "connection"

    monkeypatch.setattr(db.pymssql, "connect", fake_connect)
    monkeypatch.setattr(db.time, "sleep", sleeps.append)
    assert db.connect("mssql+pymssql://u:p@h/d") == "connection"
    assert len(calls) == 3
    assert sleeps == [1, 2]


def test_connect_gives_up_after_the_last_attempt(monkeypatch):
    def always_fail(**kwargs):
        raise pymssql.OperationalError("down")

    monkeypatch.setattr(db.pymssql, "connect", always_fail)
    monkeypatch.setattr(db.time, "sleep", lambda s: None)
    with pytest.raises(pymssql.OperationalError):
        db.connect("mssql+pymssql://u:p@h/d")


def test_connect_without_retry_tries_once(monkeypatch):
    calls = []

    def fail(**kwargs):
        calls.append(1)
        raise pymssql.OperationalError("down")

    monkeypatch.setattr(db.pymssql, "connect", fail)
    with pytest.raises(pymssql.OperationalError):
        db.connect("mssql+pymssql://u:p@h/d", retry=False)
    assert calls == [1]


def test_transaction_rolls_back_on_error(db_url_with_product):
    """If anything fails inside a transaction, none of its changes are saved."""
    url = db_url_with_product
    with pytest.raises(RuntimeError):
        with transaction(url) as cursor:
            cursor.execute("UPDATE products SET price_cents = 0")
            raise RuntimeError("boom")
    with transaction(url) as cursor:
        cursor.execute("SELECT price_cents FROM products")
        assert cursor.fetchone()["price_cents"] == 500


@pytest.fixture
def db_url_with_product(db):
    with transaction(db) as cursor:
        cursor.execute("INSERT INTO products (name, price_cents) VALUES ('Mug', 500)")
    return db


def test_split_batches_on_go_lines():
    sql = "CREATE TABLE a (x INT);\nGO\n  go  \nUPDATE a SET x = 1;\nGO"
    assert split_batches(sql) == ["CREATE TABLE a (x INT);", "UPDATE a SET x = 1;"]
    assert split_batches("SELECT 'GOOD'") == ["SELECT 'GOOD'"]


def test_pending_migrations_are_in_order_and_skip_applied(tmp_path):
    for name in ("002_b.sql", "001_a.sql", "010_c.sql", "notes.txt"):
        (tmp_path / name).write_text("SELECT 1")
    pending = pending_migrations({"001_a.sql"}, tmp_path)
    assert [p.name for p in pending] == ["002_b.sql", "010_c.sql"]


def test_second_run_applies_nothing(database_url):
    """The session fixture already applied every file; running again is a no-op."""
    connection = db.connect(database_url)
    try:
        assert migrate(connection) == []
        cursor = connection.cursor()
        cursor.execute("SELECT version FROM schema_migrations ORDER BY version")
        recorded = [row[0] for row in cursor.fetchall()]
    finally:
        connection.close()
    assert recorded == sorted(p.name for p in MIGRATIONS_DIR.glob("*.sql"))


def test_failed_migration_is_rolled_back_and_not_recorded(database_url, tmp_path):
    (tmp_path / "001_ok.sql").write_text("CREATE TABLE dbo.tmp_ok (x INT);")
    (tmp_path / "002_bad.sql").write_text("CREATE TABLE dbo.tmp_bad (x INT);\nGO\nTHIS IS NOT SQL;")
    connection = db.connect(database_url)
    try:
        with pytest.raises(pymssql.Error):
            migrate(connection, tmp_path)
        cursor = connection.cursor()
        cursor.execute("SELECT version FROM schema_migrations WHERE version IN ('001_ok.sql', '002_bad.sql')")
        assert [row[0] for row in cursor.fetchall()] == ["001_ok.sql"]
        cursor.execute("SELECT OBJECT_ID('dbo.tmp_bad')")
        assert cursor.fetchone()[0] is None
        cursor.execute("DROP TABLE dbo.tmp_ok; DELETE FROM schema_migrations WHERE version = '001_ok.sql'")
        connection.commit()
    finally:
        connection.close()


def test_migration_004_keeps_existing_products(tmp_path):
    """Build a database at migration 003, add products, then apply 004.

    004 changes a table that already holds data: every product must survive
    unchanged, with version 1 if it had a picture and 0 if not.
    """
    from tests.conftest import TEST_DATABASE_URL

    settings = db.connection_settings(TEST_DATABASE_URL)
    name = settings["database"].removesuffix("_test") + "_m004_test"
    admin = pymssql.connect(**{**settings, "database": "master"}, autocommit=True, login_timeout=30)
    admin.cursor().execute(f"IF DB_ID(N'{name}') IS NOT NULL DROP DATABASE [{name}]; CREATE DATABASE [{name}]")
    url = TEST_DATABASE_URL.rsplit("/", 1)[0] + f"/{name}"
    try:
        for path in sorted(MIGRATIONS_DIR.glob("00[1-3]_*.sql")):
            (tmp_path / path.name).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        connection = db.connect(url)
        try:
            migrate(connection, tmp_path)
        finally:
            connection.close()
        with transaction(url) as cursor:
            cursor.execute("""INSERT INTO products (name, price_cents, image_data, image_content_type)
                              VALUES ('With picture', 200, 0x89504E47, 'image/png'),
                                     ('No picture', 300, NULL, NULL)""")

        (tmp_path / "004_image_version.sql").write_text(
            (MIGRATIONS_DIR / "004_image_version.sql").read_text(encoding="utf-8"), encoding="utf-8")
        connection = db.connect(url)
        try:
            assert migrate(connection, tmp_path) == ["004_image_version.sql"]
        finally:
            connection.close()

        with transaction(url) as cursor:
            cursor.execute("SELECT name, price_cents, image_data, image_version FROM products ORDER BY name")
            rows = cursor.fetchall()
        assert rows == [
            {"name": "No picture", "price_cents": 300, "image_data": None, "image_version": 0},
            {"name": "With picture", "price_cents": 200, "image_data": b"\x89PNG", "image_version": 1},
        ]
    finally:
        admin.cursor().execute(
            f"ALTER DATABASE [{name}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE [{name}]")
        admin.close()
