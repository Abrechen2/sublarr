"""Spell checking routes — /spell/check, /spell/dictionaries."""

import os
import logging

from flask import Blueprint, request, jsonify

from config import get_settings
from services.spell_checker import (
    check_subtitle_file,
    get_available_dictionaries,
    SpellChecker,
)

bp = Blueprint("spell", __name__, url_prefix="/api/v1")
logger = logging.getLogger(__name__)


@bp.route("/spell/check", methods=["POST"])
def check_spelling():
    """Check spelling in a subtitle file or text content.
    ---
    post:
      tags:
        - Spell
      summary: Check spelling
      description: Checks spelling in a subtitle file or provided text content.
      security:
        - apiKeyAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                file_path:
                  type: string
                content:
                  type: string
                language:
                  type: string
                  default: en_US
                custom_words:
                  type: array
                  items:
                    type: string
      responses:
        200:
          description: Spell check results
          content:
            application/json:
              schema:
                type: object
                properties:
                  errors:
                    type: array
                    items:
                      type: object
                      properties:
                        word:
                          type: string
                        position:
                          type: integer
                        suggestions:
                          type: array
                          items:
                            type: string
                        line:
                          type: integer
                        text:
                          type: string
                  total_words:
                    type: integer
                  error_count:
                    type: integer
        400:
          description: Invalid request
        404:
          description: File not found
        500:
          description: Processing error
    """
    data = request.get_json(silent=True) or {}
    file_path = data.get("file_path")
    content = data.get("content")
    language = data.get("language", "en_US")
    custom_words = data.get("custom_words", [])

    if not file_path and not content:
        return jsonify({"error": "file_path or content is required"}), 400

    try:
        if file_path:
            # Path mapping
            settings = get_settings()
            mapped_path = file_path
            if hasattr(settings, "media_path_mapping") and settings.media_path_mapping:
                for mapping in settings.media_path_mapping:
                    if file_path.startswith(mapping.get("from", "")):
                        mapped_path = file_path.replace(
                            mapping["from"],
                            mapping.get("to", file_path),
                            1,
                        )
                        break

            if not os.path.exists(mapped_path):
                return jsonify({"error": "File not found"}), 404

            result = check_subtitle_file(mapped_path, language, custom_words)
        else:
            # Check content directly
            from services.spell_checker import SpellChecker, ENCHANT_AVAILABLE

            if not ENCHANT_AVAILABLE:
                return jsonify({
                    "errors": [],
                    "total_words": 0,
                    "error_count": 0,
                    "error": "Spell checking not available (pyenchant not installed)",
                }), 200

            checker = SpellChecker(language)
            if custom_words:
                checker.add_custom_words(custom_words)

            errors = checker.check_text(content)
            result = {
                "errors": errors,
                "total_words": len(checker._extract_words(content)),
                "error_count": len(errors),
            }

        return jsonify(result), 200
    except RuntimeError as e:
        logger.error("Spell checking failed: %s", e)
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        logger.exception("Unexpected error during spell checking")
        return jsonify({"error": "Internal server error"}), 500


@bp.route("/spell/dictionaries", methods=["GET"])
def list_dictionaries():
    """List available spell checking dictionaries.
    ---
    get:
      tags:
        - Spell
      summary: List dictionaries
      description: Returns list of available dictionary languages.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Available dictionaries
          content:
            application/json:
              schema:
                type: object
                properties:
                  dictionaries:
                    type: array
                    items:
                      type: string
    """
    try:
        dictionaries = get_available_dictionaries()
        return jsonify({"dictionaries": dictionaries}), 200
    except Exception as e:
        logger.exception("Failed to list dictionaries")
        return jsonify({"error": "Internal server error"}), 500
