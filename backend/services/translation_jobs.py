"""Translation job execution + in-memory translation stats.

Moved from ``routes/translate/_helpers.py`` (``_run_job`` / ``_update_stats``)
and ``routes/batch_state.py`` (``stats_lock`` / ``_memory_stats``) on
2026-07-02 so that services (e.g. ``services.retranslation``) no longer
import from the routes layer. ``routes/translate/_helpers.py`` and
``routes/batch_state.py`` keep thin delegating shims / re-exports for the
old names — several tests patch those paths.
"""

from __future__ import annotations

import logging
import threading
import time

from extensions import socketio

logger = logging.getLogger(__name__)

# --- In-memory translation stats (shared with routes/system/statistics.py) ---

stats_lock = threading.Lock()
_memory_stats = {
    "started_at": time.time(),
    "upgrades": {"srt_to_ass_translated": 0, "srt_upgrade_skipped": 0},
    "quality_warnings": 0,
}


def update_stats(result):
    """Update stats from a translation result (thread-safe)."""
    from db.jobs import record_stat

    with stats_lock:
        if result["success"]:
            s = result.get("stats", {})
            if s.get("skipped"):
                record_stat(success=True, skipped=True)
                reason = s.get("reason", "")
                if "no ASS upgrade" in reason:
                    _memory_stats["upgrades"]["srt_upgrade_skipped"] += 1
            else:
                fmt = s.get("format", "")
                source = s.get("source", "")
                record_stat(success=True, skipped=False, fmt=fmt, source=source)
                if s.get("upgrade_from_srt"):
                    _memory_stats["upgrades"]["srt_to_ass_translated"] += 1
                if s.get("quality_warnings"):
                    _memory_stats["quality_warnings"] += len(s["quality_warnings"])
        else:
            record_stat(success=False)


def run_job(job_data):
    """Execute a translation job in a background thread."""
    from db.jobs import get_job, record_stat, update_job
    from translator import translate_file

    job_id = job_data["id"]

    # Cancellation guard: the job may have been soft-cancelled (DELETE
    # /translate/jobs/<id> or POST /translate/jobs/clear-queued) between
    # enqueue and thread start. Re-read the row and skip execution when it
    # is no longer queued — leave whatever status it has now untouched.
    try:
        current = get_job(job_id)
    except Exception:
        # DB hiccup on the pre-flight read must not eat the job — fall
        # through and let the normal execution path surface any real error.
        current = job_data
    if current is None or current.get("status") != "queued":
        logger.info(
            "Skipping translation job %s: status is %r, not 'queued' (cancelled or removed)",
            job_id,
            current.get("status") if current else None,
        )
        return

    try:
        update_job(job_id, "running")

        result = translate_file(
            job_data["file_path"],
            force=job_data.get("force", False),
            arr_context=job_data.get("arr_context"),
        )

        status = "completed" if result["success"] else "failed"
        update_job(job_id, status, result=result, error=result.get("error"))
        update_stats(result)

        # Emit WebSocket event
        socketio.emit(
            "job_update",
            {
                "id": job_id,
                "status": status,
                "result": result,
            },
        )

    except Exception as e:
        logger.exception("Job %s failed", job_id)
        update_job(job_id, "failed", error=str(e))
        record_stat(success=False)
