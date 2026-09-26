"""Diagnostic sections of the support bundle.

Each section answers one question a bug report otherwise needs a round trip
for: which schema the database is on, what the scheduler has been doing, which
providers are really live, how deep the queues are, where the foreign-track
sweep stands, and which tool versions the container ships.

Every section is failure-tolerant on its own: an exception is logged and turns
into ``{"unavailable": "<reason>"}`` for that section only, so one broken table
never costs the user the whole export. Every value passes through ``redact()``
before it leaves this module.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
from collections.abc import Callable
from datetime import UTC, datetime

from routes.system.support_logs import _anonymize, current_hostname
from secret_redaction import redact, scrub_tree

logger = logging.getLogger(__name__)

RECENT_RUNS_PER_JOB = 20
# Long error texts in run history are truncated; the log file has the rest.
_ERROR_MSG_MAX = 300
_TOOL_TIMEOUT_S = 5
# (binary, version flag) — ffmpeg-family tools use a single dash.
_TOOLS = (("ffmpeg", "-version"), ("ffprobe", "-version"), ("mkvmerge", "--version"))
_TRACK_POLICY_FIELDS = (
    "cleanup_track_variant_mode",
    "cleanup_keep_forced",
    "cleanup_keep_sdh",
    "cleanup_sidecar_policy",
    "foreign_track_sweep_enabled",
    "cleanup_foreign_tracks_default",
)


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def _scrub_section(value):
    """Anonymize every string leaf — secrets, paths, IPs, e-mails, hostname.

    The same helper the log files go through: run-history error texts carry
    media paths and addresses just like log lines do.
    """
    hostname = current_hostname()
    return scrub_tree(value, lambda text: _anonymize(text, hostname=hostname))


def run_section(name: str, build: Callable[[], dict]) -> dict:
    """Build one section; a failure becomes ``{"unavailable": reason}``."""
    try:
        return _scrub_section(build())
    except Exception as exc:  # noqa: BLE001 — one section must not abort the export
        logger.warning("support bundle: section %s unavailable: %s", name, exc, exc_info=True)
        return {"unavailable": redact(f"{type(exc).__name__}: {exc}")}


# ─── database ─────────────────────────────────────────────────────────────────


def _alembic_state(engine) -> dict:
    import sqlalchemy as sa
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config()
    cfg.set_main_option(
        "script_location",
        os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "db", "migrations"
        ),
    )
    heads = sorted(ScriptDirectory.from_config(cfg).get_heads())
    if not sa.inspect(engine).has_table("alembic_version"):
        return {"tracked": False, "mode": "create_all", "heads": heads, "current": []}
    with engine.connect() as conn:
        current = sorted(
            r[0] for r in conn.execute(sa.text("SELECT version_num FROM alembic_version"))
        )
    return {
        "tracked": True,
        "mode": "alembic",
        "heads": heads,
        "current": current,
        "up_to_date": current == heads,
    }


def _untracked_repairs(engine) -> dict:
    import sqlalchemy as sa

    from db.untracked_data_repairs import MARKER_TABLE, REPAIRS

    registered = [revision for revision, _ in REPAIRS]
    if not sa.inspect(engine).has_table(MARKER_TABLE):
        return {"registered": registered, "applied": [], "pending": registered}
    with engine.connect() as conn:
        rows = conn.execute(
            sa.text(f"SELECT revision, applied_at, affected FROM {MARKER_TABLE}")
        ).all()
    applied = [{"revision": r[0], "applied_at": r[1], "affected": r[2]} for r in rows]
    done = {a["revision"] for a in applied}
    return {
        "registered": registered,
        "applied": applied,
        "pending": [r for r in registered if r not in done],
    }


def database_section() -> dict:
    from db.storage_probe import last_probe_result
    from extensions import db

    engine = db.engine
    dialect = engine.dialect.name
    backend = {"postgresql": "postgres", "sqlite": "sqlite"}.get(dialect, dialect)
    return {
        "backend": backend,
        "alembic": _alembic_state(engine),
        "untracked_data_repairs": _untracked_repairs(engine),
        "storage_probe": last_probe_result(),
    }


# ─── scheduler ────────────────────────────────────────────────────────────────


def _registered_jobs() -> dict:
    from flask import current_app

    from routes.system.scheduler_serializers import serialize_trigger

    scheduler = current_app.extensions.get("scheduler")
    if scheduler is None or getattr(scheduler, "_scheduler", None) is None:
        return {"running": False, "jobs": [], "paused": []}
    jobs = []
    for job_id in sorted(getattr(scheduler, "_registered_ids", ())):
        aps_job = scheduler._scheduler.get_job(job_id)
        jobs.append(
            {
                "id": job_id,
                "paused": aps_job is not None and aps_job.next_run_time is None,
                "trigger": serialize_trigger(aps_job.trigger) if aps_job else None,
                "next_run_time": _iso(aps_job.next_run_time) if aps_job else None,
            }
        )
    return {
        "running": bool(getattr(scheduler, "running", False)),
        "jobs": jobs,
        "paused": [j["id"] for j in jobs if j["paused"]],
    }


def _recent_runs() -> dict:
    import sqlalchemy as sa

    from db.models.scheduler import JobRun
    from extensions import db

    job_ids = [r[0] for r in db.session.execute(sa.select(JobRun.job_id).distinct()).all()]
    runs: dict[str, list[dict]] = {}
    for job_id in sorted(job_ids):
        rows = (
            db.session.execute(
                sa.select(JobRun)
                .where(JobRun.job_id == job_id)
                .order_by(JobRun.started_at.desc())
                .limit(RECENT_RUNS_PER_JOB)
            )
            .scalars()
            .all()
        )
        runs[job_id] = [
            {
                "started_at": _iso(r.started_at),
                "duration_ms": r.duration_ms,
                "status": r.status,
                "triggered_by": r.triggered_by,
                "error_type": r.error_type,
                # Anonymize the whole text, then cut — cutting first can split
                # a DSN mid-password so the surviving half matches no pattern.
                "error_msg": _anonymize(r.error_msg)[:_ERROR_MSG_MAX] if r.error_msg else None,
            }
            for r in rows
        ]
    return runs


def scheduler_section() -> dict:
    from config import get_settings

    settings = get_settings()
    interval_zero = sorted(
        name
        for name, value in settings.model_dump().items()
        if "interval" in name and isinstance(value, (int, float)) and value == 0
    )
    return {
        **_registered_jobs(),
        "interval_zero_settings": interval_zero,
        "recent_runs": _recent_runs(),
    }


# ─── providers ────────────────────────────────────────────────────────────────


def provider_rows() -> list[dict]:
    """One row per registered provider: configured, live, and breaker state.

    ``active`` means the provider is initialised in the running manager — not
    merely allowed by ``providers_enabled``. An empty ``providers_enabled``
    means "all allowed", and reading that as "all active" listed every
    unconfigured provider as live.
    """
    from config import get_settings
    from providers import _PROVIDER_CLASSES, get_provider_manager

    manager = get_provider_manager()
    live = getattr(manager, "_providers", {}) or {}
    breakers = getattr(manager, "_circuit_breakers", {}) or {}
    enabled_raw = getattr(get_settings(), "providers_enabled", "") or ""
    allowed = {p.strip().lower() for p in enabled_raw.split(",") if p.strip()}

    rows = []
    for name in sorted(_PROVIDER_CLASSES):
        breaker = breakers.get(name)
        status = breaker.get_status() if breaker is not None else None
        rows.append(
            {
                "name": name,
                "enabled": not allowed or name.lower() in allowed,
                "active": name in live,
                "circuit_state": status["state"] if status else None,
                "failure_count": status["failure_count"] if status else None,
            }
        )
    return rows


def providers_section() -> dict:
    return {"providers": provider_rows()}


# ─── queues ───────────────────────────────────────────────────────────────────


def queues_section() -> dict:
    import sqlalchemy as sa
    from flask import current_app

    from db.models.core import Job, SubtitleAutomationQueueEntry
    from extensions import db

    automation = [
        {"task_type": task_type, "state": state, "count": count}
        for task_type, state, count in db.session.execute(
            sa.select(
                SubtitleAutomationQueueEntry.task_type,
                SubtitleAutomationQueueEntry.state,
                sa.func.count(),
            ).group_by(SubtitleAutomationQueueEntry.task_type, SubtitleAutomationQueueEntry.state)
        ).all()
    ]
    jobs_by_status = {
        status: count
        for status, count in db.session.execute(
            sa.select(Job.status, sa.func.count()).group_by(Job.status)
        ).all()
    }
    queue = getattr(current_app, "job_queue", None)
    job_queue = None
    if queue is not None:
        job_queue = {
            "backend": queue.get_backend_info(),
            "queued": queue.get_queue_length(),
            "active": len(queue.get_active_jobs()),
        }
    return {
        "subtitle_automation_queue": automation,
        "translation_jobs_by_status": jobs_by_status,
        "job_queue": job_queue,
    }


# ─── foreign tracks ───────────────────────────────────────────────────────────


def foreign_tracks_section() -> dict:
    from dataclasses import asdict

    import sqlalchemy as sa

    from config import get_settings
    from db.models.foreign_tracks import ForeignTrackScan
    from extensions import db
    from services.foreign_tracks.state import load_state

    state = asdict(load_state())
    state.pop("config_hash", None)
    counts = {
        s: c
        for s, c in db.session.execute(
            sa.select(ForeignTrackScan.state, sa.func.count()).group_by(ForeignTrackScan.state)
        ).all()
    }
    settings = get_settings()
    return {
        "sweep_state": state,
        "scan_counts_by_state": counts,
        "track_policy": {name: getattr(settings, name, None) for name in _TRACK_POLICY_FIELDS},
    }


# ─── environment ──────────────────────────────────────────────────────────────


def _tool_version(binary: str, flag: str) -> str | None:
    path = shutil.which(binary)
    if path is None:
        return None
    result = subprocess.run(
        [path, flag], capture_output=True, text=True, timeout=_TOOL_TIMEOUT_S, check=False
    )
    first = (result.stdout or result.stderr).strip().splitlines()
    return first[0] if first else f"unknown (exit {result.returncode})"


def environment_section() -> dict:
    from app_logging import _fingerprint_payload, _in_container
    from config import get_settings

    tools: dict[str, str | None] = {}
    for binary, flag in _TOOLS:
        try:
            tools[binary] = _tool_version(binary, flag)
        except (OSError, subprocess.SubprocessError) as exc:
            logger.warning("support bundle: %s version check failed: %s", binary, exc)
            tools[binary] = f"unavailable: {type(exc).__name__}"
    now = datetime.now().astimezone()
    return {
        "fingerprint": _fingerprint_payload(get_settings()),
        "container": _in_container(),
        "timezone": {
            "tz_env": os.environ.get("TZ"),
            "local_name": time.tzname[0],
            "utc_offset": now.strftime("%z"),
            "now_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        "tools": tools,
    }


SECTIONS: dict[str, Callable[[], dict]] = {
    "database": database_section,
    "scheduler": scheduler_section,
    "providers": providers_section,
    "queues": queues_section,
    "foreign_tracks": foreign_tracks_section,
    "environment": environment_section,
}


def collect_sections() -> dict[str, dict]:
    return {name: run_section(name, build) for name, build in SECTIONS.items()}
