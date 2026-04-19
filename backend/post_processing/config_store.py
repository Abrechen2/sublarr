"""Per-trigger op config (Plan B6).

Reads/writes ``config_entries`` rows keyed as ``post_processing.<trigger>``
with value = JSON list of op_ids. Never raises on read — missing or invalid
values return an empty list so the pipeline simply does nothing.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_KEY_PREFIX = "post_processing."
_VALID_TRIGGERS = ("after_download", "after_translate", "after_sync")


def _trigger_key(trigger: str) -> str:
    return f"{_KEY_PREFIX}{trigger}"


def is_valid_trigger(trigger: str) -> bool:
    return trigger in _VALID_TRIGGERS


def get_trigger_ops(trigger: str) -> list[str]:
    """Return the ordered list of op_ids configured for ``trigger``.

    Returns an empty list if the setting is unset, empty, or malformed.
    Never raises — the pipeline treats an empty list as "do nothing".
    """
    try:
        from db.models.core import ConfigEntry

        entry = ConfigEntry.query.filter_by(key=_trigger_key(trigger)).one_or_none()
        if entry is None or not entry.value:
            return []
        parsed = json.loads(entry.value)
        if isinstance(parsed, list):
            return [str(x) for x in parsed]
        return []
    except Exception as exc:
        logger.warning("get_trigger_ops(%s) failed: %s", trigger, exc)
        return []


def set_trigger_ops(trigger: str, op_ids: list[str]) -> None:
    """Upsert the op list for ``trigger``. Raises on DB failure."""
    from extensions import db
    from db.models.core import ConfigEntry

    key = _trigger_key(trigger)
    now = datetime.now(timezone.utc)
    existing = ConfigEntry.query.filter_by(key=key).one_or_none()
    value = json.dumps(op_ids)
    if existing is None:
        db.session.add(ConfigEntry(key=key, value=value, updated_at=now))
    else:
        existing.value = value
        existing.updated_at = now
    db.session.commit()
