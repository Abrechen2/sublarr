"""App-level routes registered directly on the Flask instance.

Extracted from app.py. Hosts /api/v1/metrics and the SPA catch-all fallback.
Blueprint-based routes live under backend/routes/ and are registered via
routes.register_blueprints().
"""


def _register_app_routes(app):
    """Register app-level routes: /metrics and SPA fallback."""
    from flask import jsonify, send_from_directory

    @app.route("/api/v1/metrics", methods=["GET"])
    def prometheus_metrics():
        """Prometheus metrics endpoint (protected by auth hook)."""
        from flask import Response

        from config import get_settings
        from metrics import generate_metrics

        body, content_type = generate_metrics(get_settings().db_path)
        return Response(body, mimetype=content_type)

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def serve_spa(path):
        """Serve the React SPA frontend.

        Unknown `/api/...` paths must NOT fall through to index.html — a mistyped
        endpoint should return a JSON 404 so clients fail loudly instead of
        silently parsing an HTML/landing-page response.
        """
        import os

        if path.startswith("api/"):
            return (
                jsonify({"error": "Not found", "path": f"/{path}"}),
                404,
            )

        static_dir = app.static_folder or "static"

        if path and os.path.exists(os.path.join(static_dir, path)):
            return send_from_directory(static_dir, path)

        index_path = os.path.join(static_dir, "index.html")
        if os.path.exists(index_path):
            return send_from_directory(static_dir, "index.html")

        from version import __version__

        return jsonify(
            {
                "name": "Sublarr",
                "version": __version__,
                "api": "/api/v1/health",
                "message": "Frontend not built. Run 'npm run build' in frontend/ first.",
            }
        )
