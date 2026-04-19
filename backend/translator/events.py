"""Translation-event writer — populates translation_events table.

Uses the same fresh-session pattern as scheduler_job_runs to ensure a
corrupted tick session cannot destroy the event record it's writing.

Event-write failures are ALWAYS logged + swallowed — translation work
must never fail due to metrics-write failure.
"""

from __future__ import annotations

import logging
from datetime import datetime

from db.models.translation import TranslationEvent
from extensions import db

logger = logging.getLogger(__name__)

_MAX_ERROR_MSG_BYTES = 4096


def write_translation_event(
    *,
    backend: str,
    source_lang: str,
    target_lang: str,
    lines_count: int,
    chars_in: int,
    started_at: datetime,
    status: str,
    finished_at: datetime | None = None,
    chars_out: int | None = None,
    tokens_in: int | None = None,
    tokens_out: int | None = None,
    cost_micro_usd: int = 0,
    cache_hit: bool = False,
    error_type: str | None = None,
    error_msg: str | None = None,
    job_id: str | None = None,
) -> None:
    """Persist one translation event.

    Silently logs + swallows DB failures; translation work must never
    be blocked by event-write failures.
    """
    latency_ms = None
    if finished_at is not None:
        latency_ms = int((finished_at - started_at).total_seconds() * 1000)

    if error_msg and len(error_msg) > _MAX_ERROR_MSG_BYTES:
        error_msg = error_msg[: _MAX_ERROR_MSG_BYTES - 3] + "..."

    row = TranslationEvent(
        backend=backend,
        source_lang=source_lang,
        target_lang=target_lang,
        lines_count=lines_count,
        chars_in=chars_in,
        chars_out=chars_out,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_estimate_micro_usd=cost_micro_usd,
        cache_hit=cache_hit,
        latency_ms=latency_ms,
        status=status,
        error_type=error_type,
        error_msg=error_msg,
        job_id=job_id,
        started_at=started_at,
        finished_at=finished_at,
    )
    try:
        _commit(row)
    except Exception:
        logger.error("translation event write failed", exc_info=True)
        try:
            db.session.rollback()
        except Exception:
            logger.error("rollback failed", exc_info=True)


def _commit(row: TranslationEvent) -> None:
    """Separate helper so tests can patch it."""
    db.session.add(row)
    db.session.commit()
