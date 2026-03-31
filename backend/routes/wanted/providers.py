"""Wanted provider routes — scanner status, search-providers, download-specific, cleanup, batch-translate."""

import logging
import os

from flask import jsonify, request

from events import emit_event
from routes.wanted import bp

logger = logging.getLogger(__name__)


# Language code aliases used for sidecar matching
_LANG_ALIASES: dict[str, list[str]] = {
    "de": ["de", "deu", "ger"],
    "en": ["en", "eng"],
    "fr": ["fr", "fra", "fre"],
    "es": ["es", "spa"],
    "ja": ["ja", "jpn"],
    "zh": ["zh", "zho", "chi"],
    "ko": ["ko", "kor"],
    "pt": ["pt", "por"],
    "it": ["it", "ita"],
    "ru": ["ru", "rus"],
    "nl": ["nl", "nld", "dut"],
    "pl": ["pl", "pol"],
}


def _sidecar_lang_codes(lang: str) -> set[str]:
    """Return all recognised filename codes for *lang* (e.g. 'de' → {'de','deu','ger'})."""
    aliases = _LANG_ALIASES.get(lang.lower(), [lang.lower()])
    return {c.lower() for c in aliases}


@bp.route("/wanted/scanner/status", methods=["GET"])
def scanner_status():
    """Live status of the Wanted scanner (scanning + searching state, progress, timestamps)."""
    from services.wanted_scanner import get_scanner  # noqa: I001

    scanner = get_scanner()
    return jsonify(
        {
            "is_scanning": scanner.is_scanning,
            "is_searching": scanner.is_searching,
            "progress": scanner.scan_progress,
            "last_scan_at": scanner.last_scan_at,
            "last_search_at": scanner.last_search_at,
            "last_summary": scanner.last_summary,
        }
    )


@bp.route("/wanted/<int:item_id>/search-providers", methods=["GET"])
def search_providers_interactive(item_id):
    """Return all provider results for interactive subtitle selection.
    ---
    get:
      tags:
        - Wanted
      summary: Interactive provider search
      description: Searches all providers and returns every result for the user to pick from manually.
      security:
        - apiKeyAuth: []
      parameters:
        - in: path
          name: item_id
          required: true
          schema:
            type: integer
          description: Wanted item ID
      responses:
        200:
          description: All provider results
          content:
            application/json:
              schema:
                type: object
                properties:
                  results:
                    type: array
                    items:
                      type: object
                  total:
                    type: integer
                  item:
                    type: object
        404:
          description: Item not found
    """
    from db.wanted import get_wanted_item
    from wanted_search import search_providers_for_item

    item = get_wanted_item(item_id)
    if not item:
        return jsonify({"error": "Item not found"}), 404

    result = search_providers_for_item(item_id)
    return jsonify(result)


@bp.route("/wanted/<int:item_id>/download-specific", methods=["POST"])
def download_specific(item_id):
    """Download a specific subtitle result chosen by the user.
    ---
    post:
      tags:
        - Wanted
      summary: Download specific subtitle
      description: Downloads a specific provider result and optionally translates it.
      security:
        - apiKeyAuth: []
      parameters:
        - in: path
          name: item_id
          required: true
          schema:
            type: integer
          description: Wanted item ID
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [provider_name, subtitle_id, language]
              properties:
                provider_name:
                  type: string
                subtitle_id:
                  type: string
                language:
                  type: string
                translate:
                  type: boolean
                  default: false
      responses:
        200:
          description: Subtitle downloaded (and optionally translated)
          content:
            application/json:
              schema:
                type: object
                properties:
                  success:
                    type: boolean
                  path:
                    type: string
                  format:
                    type: string
                  translated:
                    type: boolean
        400:
          description: Validation error or download/translation failed
        404:
          description: Item not found
    """
    from db.wanted import get_wanted_item
    from wanted_search import download_specific_for_item

    item = get_wanted_item(item_id)
    if not item:
        return jsonify({"error": "Item not found"}), 404

    data = request.get_json() or {}
    provider_name = (data.get("provider_name") or "").strip()
    subtitle_id = (data.get("subtitle_id") or "").strip()
    language = (data.get("language") or "").strip()
    translate = bool(data.get("translate", False))

    if not provider_name or not subtitle_id or not language:
        return jsonify({"error": "provider_name, subtitle_id, and language are required"}), 400

    result = download_specific_for_item(item_id, provider_name, subtitle_id, language, translate)

    if not result.get("success"):
        return jsonify(result), 400

    emit_event(
        "wanted_item_processed",
        {
            "wanted_id": item_id,
            "status": "found",
            "output_path": result.get("path"),
            "provider": provider_name,
        },
    )
    return jsonify(result)


@bp.route("/wanted/cleanup", methods=["POST"])
def cleanup_sidecars():
    """Delete non-target-language subtitle sidecars next to extracted media files.
    ---
    post:
      tags:
        - Wanted
      summary: Cleanup non-target sidecar subtitles
      description: >
        For each wanted item (optionally filtered by item_ids) finds all .ass/.srt
        sidecar files next to the media file and deletes those that do not match the
        target language.  Use dry_run=true to preview without deleting.
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                item_ids:
                  type: array
                  items:
                    type: integer
                  description: Restrict to these wanted item IDs (omit for all extracted items)
                dry_run:
                  type: boolean
                  description: If true, report what would be deleted without actually deleting
      responses:
        200:
          description: Cleanup result
          content:
            application/json:
              schema:
                type: object
                properties:
                  deleted:
                    type: array
                    items:
                      type: string
                  kept:
                    type: array
                    items:
                      type: string
                  errors:
                    type: array
                    items:
                      type: string
                  dry_run:
                    type: boolean
    """
    import glob as _glob

    from config import get_settings
    from db.wanted import get_wanted_items, get_wanted_items_by_ids
    from security_utils import is_safe_path

    data = request.get_json(force=True, silent=True) or {}
    dry_run = bool(data.get("dry_run", False))
    item_ids: list[int] | None = data.get("item_ids")

    settings = get_settings()
    media_path = getattr(settings, "media_path", None) or "/"

    deleted: list[str] = []
    kept: list[str] = []
    errors: list[str] = []

    # Resolve items to process
    if item_ids:
        items = list(get_wanted_items_by_ids(item_ids).values())
    else:
        _PAGE = 200
        _page = 1
        items = []
        while True:
            result = get_wanted_items(status="extracted", page=_page, per_page=_PAGE)
            batch = result.get("data", [])
            items.extend(batch)
            if len(batch) < _PAGE:
                break
            _page += 1

    for item in items:
        file_path = item.get("file_path", "")
        if not file_path or not os.path.exists(file_path):
            continue

        target_lang = item.get("target_language", "")
        keep_codes = _sidecar_lang_codes(target_lang) if target_lang else set()

        # Determine base name (strip video extension)
        base = os.path.splitext(file_path)[0]

        for fmt in ("ass", "srt"):
            pattern = f"{base}.*.{fmt}"
            for sidecar in _glob.glob(pattern):
                # Security: ensure sidecar is within allowed media path
                if not is_safe_path(sidecar, media_path):
                    errors.append(f"Skipped (path traversal): {sidecar}")
                    continue

                # Extract language code from sidecar filename: base.<lang>.<fmt>
                remainder = sidecar[len(base) + 1 : -len(fmt) - 1]  # e.g. "de" or "deu"
                lang_part = remainder.split(".")[0].lower()

                if lang_part in keep_codes:
                    kept.append(sidecar)
                else:
                    if not dry_run:
                        try:
                            os.remove(sidecar)
                            deleted.append(sidecar)
                        except OSError as exc:
                            errors.append(f"{sidecar}: {exc}")
                    else:
                        deleted.append(sidecar)  # report as "would delete"

    return jsonify({"deleted": deleted, "kept": kept, "errors": errors, "dry_run": dry_run})


# ---------------------------------------------------------------------------
# Batch re-translation
# ---------------------------------------------------------------------------


def _retranslate_item(item_id: int):
    """Queue re-translation for a single wanted item. Delegates to retranslation service."""
    from services.retranslation import retranslate_item

    return retranslate_item(item_id)


@bp.route("/wanted/batch-translate", methods=["POST"])
def batch_translate():
    """Queue multiple wanted items for re-translation.
    ---
    post:
      tags:
        - Wanted
      summary: Batch re-translate wanted items
      description: >
        Accepts a list of wanted item IDs and queues each one for re-translation.
        Items whose media file cannot be found are silently skipped.
      security:
        - apiKeyAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [item_ids]
              properties:
                item_ids:
                  type: array
                  items:
                    type: integer
                  description: List of wanted item IDs to re-translate
      responses:
        202:
          description: Jobs queued
          content:
            application/json:
              schema:
                type: object
                properties:
                  queued:
                    type: integer
                  job_ids:
                    type: array
                    items:
                      type: string
        400:
          description: item_ids missing or empty
    """
    data = request.get_json(force=True, silent=True) or {}
    item_ids = data.get("item_ids")
    if not item_ids:
        return jsonify({"error": "item_ids required and must be non-empty"}), 400
    if not isinstance(item_ids, list):
        return jsonify({"error": "item_ids must be a list"}), 400

    job_ids = []
    for item_id in item_ids:
        job_id = _retranslate_item(item_id)
        if job_id:
            job_ids.append(job_id)

    return jsonify({"queued": len(job_ids), "job_ids": job_ids}), 202
