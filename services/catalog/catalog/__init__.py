"""Catalog service: products, options and stock, as a JSON API."""

import os

from flask import Flask, jsonify
from werkzeug.exceptions import HTTPException

from catalog.api import admin_api, internal_api, public_api


def create_app(config=None):
    """Create the catalog Flask app. Settings come from environment variables."""
    app = Flask(__name__)
    app.config.update(
        DATABASE_URL=os.environ.get("DATABASE_URL", ""),
        ADMIN_PASSWORD=os.environ.get("ADMIN_PASSWORD", ""),
        INTERNAL_TOKEN=os.environ.get("INTERNAL_TOKEN", ""),
        GIT_SHA=os.environ.get("GIT_SHA", "dev"),
    )
    if config:
        app.config.update(config)

    app.register_blueprint(public_api)
    app.register_blueprint(admin_api)
    app.register_blueprint(internal_api)

    @app.get("/health")
    def health():
        """Report that the process is up and which commit it runs."""
        return jsonify(status="ok", version=app.config["GIT_SHA"])

    @app.errorhandler(HTTPException)
    def http_error(error):
        """Answer 404, 405 and other HTTP errors as JSON instead of HTML."""
        return jsonify(error=error.description), error.code

    return app
