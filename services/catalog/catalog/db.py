"""SQL Server connection for the catalog service, with retries for a paused database."""

import logging
import os
import time
from contextlib import contextmanager
from urllib.parse import unquote, urlparse

import pymssql

log = logging.getLogger(__name__)

# Azure SQL serverless pauses after an hour idle and takes up to about a minute
# to resume; connections fail meanwhile (error 40613). These waits add up to
# about 75 seconds before the last attempt.
RETRY_DELAYS_S = (1, 2, 4, 8, 15, 15, 15, 15)


def connection_settings(database_url):
    """Turn mssql+pymssql://user:password@host:port/database into pymssql arguments."""
    url = urlparse(database_url)
    if url.scheme not in ("mssql", "mssql+pymssql"):
        raise ValueError("DATABASE_URL must start with mssql+pymssql://")
    return {
        "server": url.hostname,
        "port": str(url.port or 1433),
        "user": unquote(url.username or ""),
        "password": unquote(url.password or ""),
        "database": url.path.lstrip("/"),
    }


def connect(database_url=None):
    """Open a connection, retrying with growing waits while the database is unreachable."""
    settings = connection_settings(database_url or os.environ["DATABASE_URL"])
    attempts = len(RETRY_DELAYS_S) + 1
    for attempt in range(1, attempts + 1):
        try:
            return pymssql.connect(**settings, login_timeout=10, timeout=30)
        except pymssql.OperationalError as error:
            if attempt == attempts:
                raise
            delay = RETRY_DELAYS_S[attempt - 1]
            log.warning(
                "Database not reachable (attempt %d of %d): %s. Retrying in %ds.",
                attempt, attempts, error, delay,
            )
            time.sleep(delay)


@contextmanager
def transaction(database_url=None):
    """Give a cursor that returns rows as dicts; commit on success, roll back on error.

    Every repository function uses this, so each one is a single unit of work:
    either all of its SQL is saved or none of it is.
    """
    connection = connect(database_url)
    try:
        cursor = connection.cursor(as_dict=True)
        yield cursor
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
