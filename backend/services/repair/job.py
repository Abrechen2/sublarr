"""The repair job: one long-running restore pass, observable while it runs.

Repairing thousands of sidecars takes hours (the provider allowance is a daily
budget), so the work runs in the background and the UI polls this state. Only one
pass may run at a time — two passes would race on the same files and burn quota
twice for nothing.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

_lock = threading.Lock()


@dataclass
class RepairState:
    running: bool = False
    dry_run: bool = False
    language: str | None = None
    total: int = 0
    done: int = 0
    repaired: int = 0
    from_bak: int = 0
    from_provider: int = 0
    skipped_hand_edited: int = 0
    skipped_provider_changed: int = 0
    failed: int = 0
    quota_exhausted: bool = False
    started_at: str | None = None
    finished_at: str | None = None
    last_file: str = ""
    error: str = ""
    recent: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


_state = RepairState()


def get_state() -> dict:
    return _state.as_dict()


def is_running() -> bool:
    return _state.running


def start(app, *, language: str | None = None, dry_run: bool = False, limit: int | None = None):
    """Kick off a repair pass. Returns False if one is already running."""
    global _state

    with _lock:
        if _state.running:
            return False
        _state = RepairState(
            running=True,
            dry_run=dry_run,
            language=language,
            started_at=datetime.now(UTC).isoformat(),
        )

    def _run():
        with app.app_context():
            try:
                _execute(language=language, dry_run=dry_run, limit=limit)
            except Exception as exc:  # noqa: BLE001 — a crash must not leave it "running"
                logger.exception("repair job failed: %s", exc)
                _state.error = str(exc)
            finally:
                _state.running = False
                _state.finished_at = datetime.now(UTC).isoformat()

    threading.Thread(target=_run, name="subtitle-repair", daemon=True).start()
    return True


def _execute(*, language: str | None, dry_run: bool, limit: int | None) -> None:
    from services.repair.runner import QuotaExhaustedError, repair_one
    from services.repair.scanner import scan

    report = scan(language=language, limit=limit)
    _state.total = report.repairable
    logger.info("repair: %d sidecars to restore (dry_run=%s)", report.repairable, dry_run)

    for candidate in report.candidates:
        _state.last_file = candidate.file_path
        try:
            outcome = repair_one(candidate, dry_run=dry_run)
        except QuotaExhaustedError as exc:
            _state.quota_exhausted = True
            logger.warning("repair: provider quota exhausted — stopping: %s", exc)
            break

        if outcome.status == "repaired":
            _state.repaired += 1
            if "from bak" in outcome.detail:
                _state.from_bak += 1
            elif "from provider" in outcome.detail:
                _state.from_provider += 1
        elif outcome.status == "hand_edited":
            _state.skipped_hand_edited += 1
        elif outcome.status == "provider_changed":
            _state.skipped_provider_changed += 1
        elif outcome.status != "repaired":
            _state.failed += 1

        _state.done += 1
        _state.recent.insert(0, {"file": candidate.file_path, "status": outcome.status})
        del _state.recent[20:]

    logger.info(
        "repair: finished — %d restored (%d from backups, %d re-downloaded), "
        "%d hand-edited, %d failed",
        _state.repaired,
        _state.from_bak,
        _state.from_provider,
        _state.skipped_hand_edited,
        _state.failed,
    )
