"""Application setup for the small shop."""

from flask import Flask, jsonify

from app.config import get_config
from app.db import initialize_database


def create_app():
    """Create the Flask app and prepare its local database."""
    app = Flask(__name__)
    app.config.update(get_config())

    if app.config["ADMIN_PASSWORD"] == "admin":
        app.logger.warning("Using the default admin password; set ADMIN_PASSWORD.")

    app.config["DATA_DIR"].mkdir(parents=True, exist_ok=True)
    app.config["UPLOAD_DIR"].mkdir(parents=True, exist_ok=True)
    initialize_database(app.config["DATABASE_PATH"])

    @app.get("/health")
    def health():
        """Report that the web process is responding."""
        return jsonify(status="ok")

    return app
