"""Global search route -- GET /api/v1/search"""

from flask import Blueprint, request, jsonify
from db.search import search_all, rebuild_search_index

bp = Blueprint("search", __name__, url_prefix="/api/v1")


@bp.route("/search", methods=["GET"])
def global_search():
    """Full-text search across series, episodes, and subtitles.
    ---
    get:
      tags:
        - Search
      summary: Global search
      description: Searches across series, episodes, and subtitles using FTS5 trigram matching.
      parameters:
        - in: query
          name: q
          schema:
            type: string
          description: Search query (min 2 chars)
        - in: query
          name: limit
          schema:
            type: integer
            default: 20
          description: Max results per category (max 50)
      responses:
        200:
          description: Grouped search results
          content:
            application/json:
              schema:
                type: object
                properties:
                  query:
                    type: string
                  series:
                    type: array
                    items:
                      type: object
                  episodes:
                    type: array
                    items:
                      type: object
                  subtitles:
                    type: array
                    items:
                      type: object
    """
    q = request.args.get("q", "").strip()
    limit = min(int(request.args.get("limit", 20)), 50)
    if not q or len(q) < 2:
        return jsonify({"series": [], "episodes": [], "subtitles": [], "query": q})
    results = search_all(q, limit=limit)
    results["query"] = q
    return jsonify(results)


@bp.route("/search/rebuild-index", methods=["POST"])
def rebuild_index():
    """Rebuild FTS5 search index from current DB state.
    ---
    post:
      tags:
        - Search
      summary: Rebuild search index
      description: Rebuilds the FTS5 search index from current database contents.
      responses:
        200:
          description: Index rebuilt
          content:
            application/json:
              schema:
                type: object
                properties:
                  success:
                    type: boolean
                  message:
                    type: string
    """
    rebuild_search_index()
    return jsonify({"success": True, "message": "Search index rebuilt"})
