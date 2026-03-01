"""Languages route — /api/v1/languages."""

from flask import Blueprint, jsonify

from cache_response import cached_get

bp = Blueprint("languages", __name__, url_prefix="/api/v1")


@bp.route("/languages", methods=["GET"])
@cached_get(ttl_seconds=3600)
def get_languages():
    """Return the list of supported languages for the UI language picker.
    ---
    get:
      tags:
        - Config
      summary: Supported languages
      description: Returns all languages supported by Sublarr, ordered alphabetically by name.
      responses:
        200:
          description: List of language objects
          content:
            application/json:
              schema:
                type: array
                items:
                  type: object
                  properties:
                    code:
                      type: string
                      description: ISO 639-1 language code (e.g. "de")
                    name:
                      type: string
                      description: English language name (e.g. "German")
    """
    from config import SUPPORTED_LANGUAGES

    return jsonify(SUPPORTED_LANGUAGES)
