"""Translation memory cache endpoints — /translation-memory/*."""

import logging

from flask import jsonify

from routes.translate import bp

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Translation Memory Cache Endpoints
# ---------------------------------------------------------------------------


@bp.route("/translation-memory/stats", methods=["GET"])
def translation_memory_stats():
    """Return statistics for the translation memory cache.
    ---
    get:
      tags:
        - Translate
      summary: Translation memory cache statistics
      description: Returns the number of entries stored in the persistent translation memory cache.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Cache statistics
          content:
            application/json:
              schema:
                type: object
                properties:
                  entries:
                    type: integer
                    description: Total cached translation entries
    """
    try:
        from db.translation import get_translation_cache_stats

        stats = get_translation_cache_stats()
        return jsonify(stats)
    except Exception as e:
        logger.error("Failed to get translation memory stats: %s", e)
        return jsonify({"error": str(e)}), 500


@bp.route("/translation-memory/cache", methods=["DELETE"])
def clear_translation_memory_cache():
    """Clear all entries from the translation memory cache.
    ---
    delete:
      tags:
        - Translate
      summary: Clear translation memory cache
      description: Deletes all cached translations from the persistent translation memory. This does not affect the glossary or any subtitle files.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Cache cleared
          content:
            application/json:
              schema:
                type: object
                properties:
                  cleared:
                    type: boolean
                  deleted:
                    type: integer
                    description: Number of rows deleted
    """
    try:
        from db.translation import clear_translation_cache

        deleted = clear_translation_cache()
        logger.info("Translation memory cache cleared: %d entries deleted", deleted)
        return jsonify({"cleared": True, "deleted": deleted})
    except Exception as e:
        logger.error("Failed to clear translation memory cache: %s", e)
        return jsonify({"error": str(e)}), 500
