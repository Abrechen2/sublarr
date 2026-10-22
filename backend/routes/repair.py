"""Repair API — restore subtitles the pre-1.6.6 pipeline damaged.

GET  /api/v1/repair/scan    — what is damaged, and where each original comes from
POST /api/v1/repair/run     — start a restore pass (dry_run writes nothing)
GET  /api/v1/repair/status  — progress of the running pass
GET  /api/v1/repair/wrong-episodes          — saved subtitles of another episode
POST /api/v1/repair/wrong-episodes/requeue  — block them for their video and search again
"""

import logging
import threading

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
    from services.repair.runner import order_local_first
    from services.repair.scanner import scan

    language = request.args.get("language") or None
    report = scan(language=language)

    # The same split the repair pass makes, so "backups only" never promises
    # work it will defer (an encoding candidate's .bak holds the damage too).
    local, remote = order_local_first(report.candidates)
    from_bak = len(local)
    needs_download: dict[str, int] = {}
    for candidate in remote:
        needs_download[candidate.provider] = needs_download.get(candidate.provider, 0) + 1

    return jsonify(
        {
            "damaged": report.repairable,
            "untouched": report.untouched,
            "missing_from_disk": report.missing_from_disk,
            "unresolvable": report.unresolvable,
            "quarantined": report.quarantined,
            "already_repaired": report.already_repaired,
            "partially_repaired": len(report.partially_repaired),
            "partially_repaired_files": report.partially_repaired[:50],
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
    local_only = bool(body.get("local_only", False))

    started = job.start(
        current_app._get_current_object(),
        language=language,
        dry_run=dry_run,
        limit=limit,
        local_only=local_only,
    )
    if not started:
        return jsonify({"error": "a repair pass is already running"}), 409

    return jsonify(
        {"status": "started", "dry_run": dry_run, "local_only": local_only, "language": language}
    ), 202


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


@bp.route("/wrong-episodes", methods=["GET"])
def wrong_episodes():
    """Saved automatic downloads whose winning release names another episode.

    Reads the database and the files' names only; downloads and changes nothing.
    ---
    get:
      summary: Find saved subtitles of another episode
      parameters:
        - in: query
          name: language
          schema: {type: string}
      responses:
        200:
          description: Findings
    """
    from services.wrong_episode_audit import scan_wrong_episodes

    findings = scan_wrong_episodes(language=request.args.get("language") or None)
    return jsonify({"count": len(findings), "findings": [f.as_dict() for f in findings]}), 200


_requeue_lock = threading.Lock()


@bp.route("/wrong-episodes/requeue", methods=["POST"])
def requeue_wrong_episodes():
    """Block each finding for its video, keep the file until replaced, search again.

    The findings are computed here, not taken from the request.
    ---
    post:
      summary: Requeue saved subtitles of another episode
      responses:
        202:
          description: Started
        409:
          description: Already running
    """
    body = request.get_json(silent=True) or {}
    language = body.get("language") or None
    if not _requeue_lock.acquire(blocking=False):
        return jsonify({"error": "a requeue is already running"}), 409
    app = current_app._get_current_object()

    def _run():
        try:
            with app.app_context():
                from services.wrong_episode_audit import requeue_findings, scan_wrong_episodes

                requeue_findings(scan_wrong_episodes(language=language))
        except Exception as exc:  # noqa: BLE001 — a background thread must log, not die silently
            logger.exception("wrong-episode requeue failed: %s", exc)
        finally:
            _requeue_lock.release()

    threading.Thread(target=_run, name="wrong-episode-requeue", daemon=True).start()
    return jsonify({"status": "started", "language": language}), 202
