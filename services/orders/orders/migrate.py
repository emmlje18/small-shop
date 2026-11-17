"""Apply orders SQL migrations once each, in order, before the web server starts.

Run as `python -m orders.migrate`. The Dockerfile runs it before gunicorn, so
migrations run in one process even though gunicorn starts several workers.
"""

import logging
import re
import sys
from pathlib import Path

from orders.db import connect

log = logging.getLogger("orders.migrate")

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"

CREATE_HISTORY_TABLE = """
IF OBJECT_ID(N'dbo.schema_migrations', N'U') IS NULL
    CREATE TABLE dbo.schema_migrations (
        version NVARCHAR(255) NOT NULL CONSTRAINT pk_schema_migrations PRIMARY KEY,
        applied_at DATETIME2 NOT NULL
            CONSTRAINT df_schema_migrations_applied_at DEFAULT SYSUTCDATETIME()
    );
"""

# A line containing only GO ends a batch, as in sqlcmd and SSMS. SQL Server
# compiles a whole batch before running it, so a migration that adds a column
# and then updates it needs a GO between the two statements.
BATCH_SEPARATOR = re.compile(r"^\s*GO\s*$", re.IGNORECASE | re.MULTILINE)


def split_batches(sql):
    """Split a migration file into the batches SQL Server runs one at a time."""
    return [batch.strip() for batch in BATCH_SEPARATOR.split(sql) if batch.strip()]


def pending_migrations(applied_versions, directory=MIGRATIONS_DIR):
    """Return migration files not yet recorded, in filename order (001, 002, ...)."""
    return [
        path for path in sorted(Path(directory).glob("*.sql"))
        if path.name not in applied_versions
    ]


def migrate(connection, directory=MIGRATIONS_DIR):
    """Apply each pending migration and its history row in one transaction."""
    cursor = connection.cursor()
    cursor.execute(CREATE_HISTORY_TABLE)
    connection.commit()

    cursor.execute("SELECT version FROM dbo.schema_migrations")
    applied_versions = {row[0] for row in cursor.fetchall()}
    pending = pending_migrations(applied_versions, directory)

    if not pending:
        log.info("No pending migrations (%d already applied)", len(applied_versions))
        return []

    for path in pending:
        log.info("Applying migration %s", path.name)
        try:
            for batch in split_batches(path.read_text(encoding="utf-8")):
                cursor.execute(batch)
            cursor.execute(
                "INSERT INTO dbo.schema_migrations (version) VALUES (%s)", (path.name,)
            )
            connection.commit()
        except Exception:
            connection.rollback()
            log.exception("Migration %s failed and was rolled back", path.name)
            raise
        log.info("Applied migration %s", path.name)

    return [path.name for path in pending]


def main():
    """Connect using DATABASE_URL and apply pending migrations."""
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stdout,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    connection = connect()
    try:
        migrate(connection)
    finally:
        connection.close()


if __name__ == "__main__":
    main()
