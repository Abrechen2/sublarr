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
    from wanted_scanner import get_scanner  # noqa: I001

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
    from db.wanted import get_wanted_item, get_wanted_items
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
        items = [get_wanted_item(iid) for iid in item_ids]
        items = [it for it in items if it]
    else:
        result = get_wanted_items(status="extracted", per_page=10000)
        items = result.get("data", [])

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
                if not is_safe_path(media_path, sidecar):
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
    """Queue re-translation for a single wanted item.

    Looks up the wanted item by ID, verifies the media file exists, deletes any
    existing translated subtitle sidecar files, and starts a background
    translation job.

    Returns the job_id string on success, or None if the item / file was not found.
    """
    import threading

    from config import get_settings
    from db.jobs import create_job
    from db.wanted import get_wanted_item
    from events import emit_event
    from security_utils import is_safe_path

    item = get_wanted_item(item_id)
    if not item:
        return None

    file_path = item.get("file_path") or item.get("path")
    if not file_path or not os.path.exists(file_path):
        return None

    settings = get_settings()
    if not is_safe_path(file_path, settings.media_path):
        logger.warning("_retranslate_item: path traversal rejected for item %s", item_id)
        return None

    # Remove existing translated sidecar files so re-translation starts clean
    base = os.path.splitext(file_path)[0]
    for fmt in ("ass", "srt"):
        for pattern in settings.get_target_patterns(fmt):
            target = base + pattern
            if os.path.exists(target):
                try:
                    os.remove(target)
                    logger.info("batch-translate: removed existing sidecar %s", target)
                except OSError as exc:
                    logger.warning("batch-translate: could not remove %s: %s", target, exc)

    new_job = create_job(file_path, force=True)

    from flask import current_app as _current_app

    _app = _current_app._get_current_object()

    def _run():
        from routes.translate import _run_job

        with _app.app_context():
            _run_job(new_job)
            emit_event(
                "translation_complete",
                {
                    "file_path": file_path,
                    "job_id": new_job["id"],
                },
            )

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    return new_job["id"]


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
