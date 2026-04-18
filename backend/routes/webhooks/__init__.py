"""Webhook routes package — /webhook/sonarr, /webhook/radarr, /webhook/jellyfin.

Split from the old ``routes/webhooks.py`` flat file (B1Wh). The three
provider-specific handlers live in sibling modules (``sonarr``,
``radarr``, ``jellyfin``) and register onto the shared ``bp``
Blueprint at import time.

The module-level helpers ``_spawn_pipeline`` + ``_webhook_auto_pipeline``
stay here — they're called by every handler and also used by tests as
patch targets (``patch("routes.webhooks._webhook_auto_pipeline")``).
Re-exports of ``emit_event`` and ``socketio`` keep the other two
documented patch paths alive.
"""

import hmac  # noqa: F401 — used by handler sub-modules via the routes.webhooks.hmac lookup
import logging
import threading
import time  # noqa: F401 — ditto

from flask import (  # noqa: F401 — re-exported so handlers import from routes.webhooks
    Blueprint,
    current_app,
    jsonify,
    request,
)

from events import emit_event  # noqa: F401 — tests patch routes.webhooks.emit_event
from extensions import socketio  # noqa: F401 — tests patch routes.webhooks.socketio

bp = Blueprint("webhooks", __name__, url_prefix="/api/v1")
logger = logging.getLogger(__name__)


def _spawn_pipeline(
    file_path: str, title: str, series_id: int = None, movie_id: int = None
) -> None:
    """Start the auto-pipeline on a daemon thread with a Flask app context.

    The pipeline touches the DB (get_wanted_items_by_path, process_wanted_item)
    which requires a Flask-SQLAlchemy app context. A raw threading.Thread has
    none, so we capture the live app object from the request handler and push
    an explicit context inside the worker thread. Without this every DB call
    in the pipeline raises `Working outside of application context` and the
    whole auto-download flow silently fails.
    """
    app = current_app._get_current_object()

    def _run():
        with app.app_context():
            _webhook_auto_pipeline(file_path, title, series_id, movie_id)

    threading.Thread(target=_run, daemon=True).start()


def _webhook_auto_pipeline(file_path: str, title: str, series_id: int = None, movie_id: int = None):
    """Full webhook automation pipeline: delay -> scan -> search -> translate.

    Each step is individually configurable. Emits WebSocket events at each stage.
    """
    from config import get_settings
    from db.jobs import create_job

    # Import _run_job from translate module for direct translation fallback
    from routes.translate import _run_job
    from services.wanted_scanner import get_scanner

    s = get_settings()
    delay = s.webhook_delay_minutes * 60

    emit_event(
        "webhook_received",
        {
            "file_path": file_path,
            "title": title,
            "delay_minutes": s.webhook_delay_minutes,
        },
    )

    # Step 1: Configurable delay (blocking sleep is safe here — this runs in a
    # dedicated background thread, HTTP response was already returned to the caller).
    # Long-term path: replace with RQ job so delay survives server restarts and
    # is visible in the job queue UI. See app.job_queue for the existing RQ setup.
    if delay > 0:
        logger.info("Webhook pipeline: waiting %d minutes...", s.webhook_delay_minutes)
        time.sleep(delay)

    result_info = {"file_path": file_path, "title": title, "steps": []}

    # Step 2: Auto-scan
    if s.webhook_auto_scan and series_id:
        try:
            scanner = get_scanner()
            scan_result = scanner.scan_series(series_id)
            result_info["steps"].append({"scan": scan_result})
            logger.info("Webhook pipeline: scan complete for series %d", series_id)
        except Exception as e:
            logger.warning("Webhook pipeline: scan failed: %s", e)
            result_info["steps"].append({"scan": {"error": str(e)}})
    elif s.webhook_auto_scan and movie_id:
        try:
            scanner = get_scanner()
            scan_result = scanner.scan_movie(movie_id)
            result_info["steps"].append({"scan": scan_result})
            logger.info("Webhook pipeline: scan complete for movie %d", movie_id)
        except Exception as e:
            logger.warning("Webhook pipeline: scan failed: %s", e)
            result_info["steps"].append({"scan": {"error": str(e)}})

    # Step 3: Auto-search + download via wanted system.
    # Runs process_wanted_item for EVERY wanted item tied to this file path —
    # one per target language (e.g. separate "de" and "en" entries for the same
    # episode). process_wanted_item internally respects settings.wanted_auto_translate:
    # when translation is disabled it still downloads target-language ASS/SRT
    # directly from providers (Steps 1+3 of process.py) and simply skips the
    # source-language + translate fallback (Steps 2/4/5).
    if s.webhook_auto_search:
        try:
            from db.wanted import get_wanted_items_by_path

            wanted_items = get_wanted_items_by_path(file_path)

            if not wanted_items:
                result_info["steps"].append({"search": "no wanted item found"})
            else:
                from wanted_search import process_wanted_item

                for item in wanted_items:
                    lang = item.get("target_language", "?")
                    try:
                        process_result = process_wanted_item(item["id"])
                        result_info["steps"].append({f"process_{lang}": process_result})
                        logger.info(
                            "Webhook pipeline: process_%s result: %s",
                            lang,
                            process_result.get("status"),
                        )
                    except Exception as inner:
                        logger.warning("Webhook pipeline: process_%s failed: %s", lang, inner)
                        result_info["steps"].append({f"process_{lang}": {"error": str(inner)}})
        except Exception as e:
            logger.warning("Webhook pipeline: search/process failed: %s", e)
            result_info["steps"].append({"search": {"error": str(e)}})

    # Step 4: Fallback -- direct translate if auto_search disabled
    if not s.webhook_auto_search:
        job = create_job(file_path)
        _run_job(job)
        result_info["steps"].append({"translate": "direct"})

    socketio.emit("webhook_completed", result_info)
    logger.info("Webhook pipeline completed for: %s", file_path)

    # Send notification
    try:
        from notifier import send_notification

        send_notification(
            title=f"Sublarr: {title}",
            body=f"Subtitle pipeline completed for {title}",
            event_type="download",
        )
    except Exception as exc:
        logger.warning("Notification send failed in webhook handler: %s", exc)


# Import sub-modules LAST so their @bp.route decorators fire after bp + the
# helpers are defined. Each module imports `bp` from us and registers routes.
from routes.webhooks import jellyfin as _jellyfin  # noqa: F401, E402
from routes.webhooks import radarr as _radarr  # noqa: F401, E402
from routes.webhooks import sonarr as _sonarr  # noqa: F401, E402
