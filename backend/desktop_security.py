"""Restrict the desktop HTTP service to its own host and browser origin."""
from urllib.parse import urlsplit
from flask import abort, request


def protect_desktop_server(app, url):
    host = urlsplit(url).netloc
    app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024

    @app.before_request
    def check_local_request():
        if request.host != host:
            abort(403)
        origin = request.headers.get("Origin")
        if origin is not None and origin != url:
            abort(403)
        if request.headers.get("Sec-Fetch-Site") == "cross-site":
            abort(403)

    @app.after_request
    def protect_local_response(response):
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response
