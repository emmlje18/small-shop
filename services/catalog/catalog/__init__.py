"""Catalog service: products, options and stock, as a JSON API."""

import logging
import os
import sys
import time

from flask import Flask, g, jsonify, request
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

from catalog.api import admin_api, internal_api, public_api
from catalog.db import transaction

request_log = logging.getLogger("catalog.request")


def create_app(config=None):
    """Create the catalog Flask app. Settings come from environment variables."""
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stdout,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    app = Flask(__name__)
    app.config.update(
        DATABASE_URL=os.environ.get("DATABASE_URL", ""),
        ADMIN_PASSWORD=os.environ.get("ADMIN_PASSWORD", ""),
        INTERNAL_TOKEN=os.environ.get("INTERNAL_TOKEN", ""),
        # Comma-separated browser origins allowed to call this API (the UI).
        CORS_ORIGINS=os.environ.get("CORS_ORIGINS", ""),
        GIT_SHA=os.environ.get("GIT_SHA", "dev"),
        MAX_CONTENT_LENGTH=5 * 1024 * 1024 + 64 * 1024,  # 5 MB image + form overhead
    )
    if config:
        app.config.update(config)

    # CORS: browsers only let a page on another site read our responses if we
    # name that site. Only the UI's origin is named. /internal is left out:
    # it is called server to server by orders, never from a browser.
    origins = [o.strip() for o in app.config["CORS_ORIGINS"].split(",") if o.strip()]
    CORS(
        app,
        resources={r"^/(?!internal/).*": {"origins": origins}},
        allow_headers=["Authorization", "Content-Type"],
        methods=["GET", "POST", "PUT", "DELETE"],
    )

    app.register_blueprint(public_api)
    app.register_blueprint(admin_api)
    app.register_blueprint(internal_api)

    @app.before_request
    def start_timer():
        g.started = time.perf_counter()

    @app.after_request
    def log_request(response):
        """One line per request on stdout: method, path, status, duration."""
        duration_ms = (time.perf_counter() - g.get("started", time.perf_counter())) * 1000
        request_log.info(
            "%s %s %s %.1fms", request.method, request.path, response.status_code, duration_ms
        )
        return response

    @app.get("/health")
    def health():
        """200 when this service can write and read its own database, else 503.

        Only this service's own state counts: the health of other services
        does not change the answer.
        """
        try:
            with transaction(app.config["DATABASE_URL"], retry=False) as cursor:
                cursor.execute(
                    """UPDATE health_check SET checked_at = SYSUTCDATETIME() WHERE id = 1;
                       IF @@ROWCOUNT = 0
                           INSERT INTO health_check (id, checked_at)
                           VALUES (1, SYSUTCDATETIME());"""
                )
                cursor.execute("SELECT checked_at FROM health_check WHERE id = 1")
                cursor.fetchone()
            db_status, code = "ok", 200
        except Exception:
            app.logger.exception("Health check could not use the database")
            db_status, code = "unavailable", 503
        status = "ok" if code == 200 else "error"
        return jsonify(status=status, db=db_status, version=app.config["GIT_SHA"]), code

    @app.errorhandler(HTTPException)
    def http_error(error):
        """Answer 404, 405, 413 and other HTTP errors as JSON instead of HTML."""
        return jsonify(error=error.description), error.code

    return app
