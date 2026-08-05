"""Sweep-level state for the batched foreign-track sweep.

Lives in ``config_entries`` rather than its own table, mirroring
``services/repair/resume.py`` — the same shape of problem (a long run that
must survive restarts and pick itself back up).
"""

import hashlib
import json
import logging
import os
from dataclasses import asdict, dataclass

logger = logging.getLogger(__name__)

STATE_KEY = "foreign_track_sweep_state"

PHASE_ENUMERATE = "enumerate"
PHASE_PROBE = "probe"
PHASE_STRIP = "strip"
PHASE_IDLE = "idle"


@dataclass
class SweepState:
    """Where the sweep is, across ticks and restarts."""

    generation: int = 0
    phase: str = PHASE_IDLE
    enumeration_complete: bool = False
    config_hash: str = ""
    started_at: str | None = None
    completed_at: str | None = None
    paused_reason: str | None = None


def load_state() -> SweepState:
    """Read the stored state, or a fresh one when nothing is stored yet."""
    from db.repositories.config import ConfigRepository

    raw = ConfigRepository().get_config_entry(STATE_KEY)
    if not raw:
        return SweepState()
    try:
        return SweepState(**json.loads(raw))
    except (ValueError, TypeError) as exc:
        logger.warning("Unreadable %s (%s) — starting a fresh sweep state", STATE_KEY, exc)
        return SweepState()


def save_state(state: SweepState) -> None:
    from db.repositories.config import ConfigRepository

    ConfigRepository().save_config_entry(STATE_KEY, json.dumps(asdict(state)))


def _norm_path(value: str) -> str:
    # Deliberately NOT case-folded: Sublarr runs on Linux/Docker, where the
    # filesystem is case-sensitive, so "_Filme" and "_filme" are genuinely
    # different scopes and must hash differently. Language codes ARE
    # case-insensitive (see the keep_languages normalisation below), but
    # paths are not — folding case here would mask a real scope change.
    return os.path.normpath(str(value)).replace("\\", "/").rstrip("/")


def config_hash(config: dict, media_root: str) -> str:
    """Hash every input that can change a file's verdict.

    Normalised so a cosmetic edit — reordering the keep-list, a trailing
    slash, or a language-code case difference — does not throw away 19,000
    cached verdicts. Path case is NOT cosmetic: the deployment filesystem
    (Linux/Docker) is case-sensitive, so a path differing only by case is a
    genuine scope change and deliberately does change the hash.
    """
    payload = {
        "keep_languages": sorted({str(x).lower() for x in (config.get("keep_languages") or [])}),
        "keep_und": bool(config.get("keep_und")),
        "include_paths": sorted({_norm_path(p) for p in (config.get("include_paths") or []) if p}),
        "exclude_paths": sorted({_norm_path(p) for p in (config.get("exclude_paths") or []) if p}),
        "media_root": _norm_path(media_root),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:32]
