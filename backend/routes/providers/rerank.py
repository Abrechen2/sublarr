"""Provider re-ranking routes: /rerank/preview, /rerank."""

import logging

from flask import jsonify, request

from routes.providers import bp

logger = logging.getLogger(__name__)


@bp.route("/rerank/preview", methods=["GET"])
def get_rerank_preview():
    """GET /api/v1/providers/rerank/preview — preview auto re-ranking without applying.

    Returns proposed modifier for each provider based on current download history.
    """
    from config import get_settings
    from providers.reranker import compute_reranking_preview

    settings = get_settings()
    min_dl = request.args.get("min_downloads", settings.provider_reranking_min_downloads, type=int)
    max_mod = request.args.get("max_modifier", settings.provider_reranking_max_modifier, type=int)

    preview = compute_reranking_preview(min_downloads=min_dl, max_modifier=max_mod)
    return jsonify(preview)


@bp.route("/rerank", methods=["POST"])
def trigger_rerank():
    """POST /api/v1/providers/rerank — manually trigger provider re-ranking.

    Body (optional JSON):
        force: bool  — bypass hourly throttle (default: true for manual trigger)
    """
    data = request.get_json(silent=True) or {}
    force = data.get("force", True)

    from providers.reranker import apply_auto_reranking

    result = apply_auto_reranking(force=force)
    return jsonify(result)
