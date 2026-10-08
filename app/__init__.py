"""Application setup for the small shop."""

from flask import Flask, jsonify

from app.config import get_config
from app.db import initialize_database
from app.catalog.routes_admin import admin_blueprint
from app.catalog.routes_public import catalog_blueprint


def create_app():
    """Create the Flask app and prepare its local database."""
    app = Flask(
        __name__,
        template_folder="../templates",
        static_folder="../static",
    )
    app.config.update(get_config())

    if app.config["ADMIN_PASSWORD"] == "admin":
        app.logger.warning("Using the default admin password; set ADMIN_PASSWORD.")

    app.config["DATA_DIR"].mkdir(parents=True, exist_ok=True)
    app.config["UPLOAD_DIR"].mkdir(parents=True, exist_ok=True)
    initialize_database(app.config["DATABASE_PATH"])
    app.register_blueprint(admin_blueprint)
    app.register_blueprint(catalog_blueprint)

    @app.get("/health")
    def health():
        """Report that the web process is responding."""
        return jsonify(status="ok")

    return app
