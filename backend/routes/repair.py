"""Repair API — restore subtitles the pre-1.6.6 pipeline damaged.

GET  /api/v1/repair/scan    — what is damaged, and where each original comes from
POST /api/v1/repair/run     — start a restore pass (dry_run writes nothing)
GET  /api/v1/repair/status  — progress of the running pass
"""

import logging

from flask import Blueprint, current_app, jsonify, request

logger = logging.getLogger(__name__)

bp = Blueprint("repair", __name__, url_prefix="/api/v1/repair")


@bp.route("/scan", methods=["GET"])
def scan_damaged():
    """Report damaged sidecars and how each one's original can be recovered.

    Downloads nothing: the .bak check is a local hash comparison, and the damage
    check compares the file on disk against the hash recorded at download time.
    ---
    get:
      summary: Scan for subtitles damaged by the pre-1.6.6 processing pipeline
      parameters:
        - in: query
          name: language
          schema: {type: string}
          description: Restrict the scan to one language (e.g. "de").
      responses:
        200:
          description: Scan report
    """
    from services.repair.runner import _hash_bytes
    from services.repair.scanner import scan
    from subtitle_filename import find_existing_bak

    language = request.args.get("language") or None
    report = scan(language=language)

    from_bak = 0
    needs_download: dict[str, int] = {}
    for candidate in report.candidates:
        bak = find_existing_bak(candidate.file_path)
        pristine = False
        if bak:
            try:
                with open(bak, "rb") as fh:
                    pristine = _hash_bytes(fh.read()) == candidate.original_hash
            except OSError:
                pristine = False
        if pristine:
            from_bak += 1
        else:
            needs_download[candidate.provider] = needs_download.get(candidate.provider, 0) + 1

    return jsonify(
        {
            "damaged": report.repairable,
            "untouched": report.untouched,
            "missing_from_disk": report.missing_from_disk,
            "unresolvable": report.unresolvable,
            "already_repaired": report.already_repaired,
            "recoverable_from_backup": from_bak,
            "needs_download": sum(needs_download.values()),
            "needs_download_by_provider": needs_download,
        }
    ), 200


@bp.route("/run", methods=["POST"])
def run_repair_job():
    """Start a repair pass in the background.

    ---
    post:
      summary: Restore damaged subtitles
      responses:
        202:
          description: Started
        409:
          description: A repair pass is already running
    """
    from services.repair import job

    body = request.get_json(silent=True) or {}
    language = body.get("language") or None
    dry_run = bool(body.get("dry_run", False))
    limit = body.get("limit")
    limit = int(limit) if limit else None

    started = job.start(
        current_app._get_current_object(), language=language, dry_run=dry_run, limit=limit
    )
    if not started:
        return jsonify({"error": "a repair pass is already running"}), 409

    return jsonify({"status": "started", "dry_run": dry_run, "language": language}), 202


@bp.route("/status", methods=["GET"])
def repair_status():
    """Progress of the running (or last) repair pass.

    ---
    get:
      summary: Repair progress
      responses:
        200:
          description: Current state
    """
    from services.repair import job

    return jsonify(job.get_state()), 200
