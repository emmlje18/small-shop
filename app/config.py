"""Read runtime settings from environment variables."""

import os
from pathlib import Path


def get_config():
    """Return the small set of settings used by the app."""
    data_dir = Path(os.environ.get("DATA_DIR", "./data")).resolve()
    return {
        "SECRET_KEY": os.environ.get("SECRET_KEY", "local-development-key"),
        "ADMIN_PASSWORD": os.environ.get("ADMIN_PASSWORD", "admin"),
        "DATA_DIR": data_dir,
        "UPLOAD_DIR": data_dir / "uploads",
        "DATABASE_PATH": data_dir / "shop.db",
        "MAX_CONTENT_LENGTH": 2 * 1024 * 1024,
    }
