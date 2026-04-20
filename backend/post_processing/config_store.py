"""Per-trigger op config (Plan B6).

Reads/writes ``config_entries`` rows keyed as ``post_processing.<trigger>``
with value = JSON list of op_ids. Never raises on read — missing or invalid
values return an empty list so the pipeline simply does nothing.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

_KEY_PREFIX = "post_processing."
_OP_KEY_PREFIX = "post_processing.op."
_VALID_TRIGGERS = ("after_download", "after_translate", "after_sync")


def _trigger_key(trigger: str) -> str:
    return f"{_KEY_PREFIX}{trigger}"


def _op_field_key(op_id: str, field: str) -> str:
    return f"{_OP_KEY_PREFIX}{op_id}.{field}"


def _op_field_prefix(op_id: str) -> str:
    return f"{_OP_KEY_PREFIX}{op_id}."


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
    from db.models.core import ConfigEntry
    from extensions import db

    key = _trigger_key(trigger)
    now = datetime.now(UTC)
    existing = ConfigEntry.query.filter_by(key=key).one_or_none()
    value = json.dumps(op_ids)
    if existing is None:
        db.session.add(ConfigEntry(key=key, value=value, updated_at=now))
    else:
        existing.value = value
        existing.updated_at = now
    db.session.commit()


def get_op_config(op_id: str) -> dict[str, str]:
    """Return all configured fields for ``op_id`` as ``{field: value}``.

    Reads every ``post_processing.op.<op_id>.<field>`` row. Missing rows map
    to missing dict keys (the pipeline injector then leaves the op's class
    default attribute untouched). Never raises — a DB error returns ``{}``.
    """
    try:
        from db.models.core import ConfigEntry

        prefix = _op_field_prefix(op_id)
        rows = ConfigEntry.query.filter(ConfigEntry.key.like(f"{prefix}%")).all()
        out: dict[str, str] = {}
        for row in rows:
            field = row.key[len(prefix) :]
            if not field:
                continue
            out[field] = row.value or ""
        return out
    except Exception as exc:
        logger.warning("get_op_config(%s) failed: %s", op_id, exc)
        return {}


def set_op_config(op_id: str, config: dict[str, str]) -> None:
    """Upsert all fields for ``op_id`` from ``config``.

    Each key/value pair is written to its own ``config_entries`` row. Fields
    not present in ``config`` are NOT deleted — call sites that want a full
    replace should wipe the rows first (current API does partial updates
    matching the submitted schema fields).
    """
    from db.models.core import ConfigEntry
    from extensions import db

    now = datetime.now(UTC)
    for field, value in config.items():
        key = _op_field_key(op_id, field)
        existing = ConfigEntry.query.filter_by(key=key).one_or_none()
        if existing is None:
            db.session.add(ConfigEntry(key=key, value=str(value), updated_at=now))
        else:
            existing.value = str(value)
            existing.updated_at = now
    db.session.commit()
