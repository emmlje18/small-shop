"""Orders service. Skeleton: only /health until the orders code moves here."""

import os

from flask import Flask, jsonify


def create_app():
    """Create the orders Flask app."""
    app = Flask(__name__)

    @app.get("/health")
    def health():
        """Report that the process is up and which commit it runs."""
        return jsonify(status="ok", version=os.environ.get("GIT_SHA", "dev"))

    return app
