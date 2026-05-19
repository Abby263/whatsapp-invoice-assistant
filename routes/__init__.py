"""Blueprint registration for the hosted Flask application."""

from __future__ import annotations

from flask import Flask

from . import auth, debug, web, webhook, workspace


def register_blueprints(app: Flask) -> None:
    app.register_blueprint(web.bp)
    app.register_blueprint(webhook.bp)
    app.register_blueprint(auth.bp)
    app.register_blueprint(workspace.bp)
    app.register_blueprint(debug.bp)
