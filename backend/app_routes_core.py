"""App-level routes registered directly on the Flask instance.

Extracted from app.py. Hosts /api/v1/metrics and the SPA catch-all fallback.
Blueprint-based routes live under backend/routes/ and are registered via
routes.register_blueprints().
"""


def _register_app_routes(app):
    """Register app-level routes: /metrics and SPA fallback."""
    from flask import jsonify, request, send_from_directory

    @app.route("/api/v1/metrics", methods=["GET"])
    def prometheus_metrics():
        """Prometheus metrics endpoint (protected by auth hook)."""
        from flask import Response

        from config import get_settings
        from metrics import generate_metrics

        body, content_type = generate_metrics(get_settings().db_path)
        return Response(body, mimetype=content_type)

    # Pre-compressed encodings the build emits (see frontend/scripts/compress-dist.mjs),
    # in preference order. Serving these with Content-Encoding avoids per-request
    # compression CPU — important on low-power self-hosts (NAS/Pi) where shipping
    # the raw multi-hundred-KB lazy route chunks made first page loads slow.
    _ENCODINGS = (("br", ".br"), ("gzip", ".gz"))
    # Vite writes content-hashed files under /assets/ → immutable, cache hard.
    _IMMUTABLE_PREFIX = "assets/"

    def _send_static(static_dir, rel_path):
        import mimetypes
        import os

        # Prefer a pre-compressed sibling the client accepts; fall back to raw.
        accept = request.headers.get("Accept-Encoding", "")
        chosen_encoding = None
        serve_rel = rel_path
        for enc_name, suffix in _ENCODINGS:
            if enc_name in accept and os.path.isfile(os.path.join(static_dir, rel_path + suffix)):
                chosen_encoding = enc_name
                serve_rel = rel_path + suffix
                break

        # Content-Type comes from the ORIGINAL name (foo.js), never the .br/.gz.
        content_type = mimetypes.guess_type(rel_path)[0] or "application/octet-stream"
        resp = send_from_directory(static_dir, serve_rel, mimetype=content_type)
        if chosen_encoding:
            resp.headers["Content-Encoding"] = chosen_encoding
            resp.headers["Vary"] = "Accept-Encoding"
        if rel_path.startswith(_IMMUTABLE_PREFIX):
            resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return resp

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

        if path and os.path.isfile(os.path.join(static_dir, path)):
            return _send_static(static_dir, path)

        index_path = os.path.join(static_dir, "index.html")
        if os.path.exists(index_path):
            from base_path import get_base_path, inject_base_into_index

            with open(index_path, encoding="utf-8") as fh:
                html = inject_base_into_index(fh.read(), get_base_path())
            resp = app.response_class(html, mimetype="text/html")
            # index.html must always revalidate so a new deploy's hashed asset
            # references are picked up instead of a stale cached shell.
            resp.headers["Cache-Control"] = "no-cache"
            return resp

        from version import __version__

        return jsonify(
            {
                "name": "Sublarr",
                "version": __version__,
                "api": "/api/v1/health",
                "message": "Frontend not built. Run 'npm run build' in frontend/ first.",
            }
        )
