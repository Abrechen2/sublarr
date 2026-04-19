"""Base class + result dataclass for sync engines (Plan B7)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import ClassVar


@dataclass
class SyncResult:
    """Outcome of one sync engine attempt."""

    engine: str
    ok: bool
    offset_ms: int
    duration_ms: int
    output_path: str = ""
    reason: str = ""
    extra: dict = field(default_factory=dict)


class EngineUnavailableError(Exception):
    """Raised when the engine's CLI/module isn't installed."""


class SanityRejectError(Exception):
    """Raised when an engine returns an offset beyond the sanity threshold."""


class BaseSyncEngine(ABC):
    """Base class for a subtitle sync engine."""

    name: ClassVar[str] = ""
    timeout_s: ClassVar[int] = 600

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if the engine can run (CLI installed, deps present)."""

    @abstractmethod
    def sync(self, subtitle_path: str, video_path: str) -> SyncResult:
        """Run the sync. Returns a SyncResult (ok=False on caught errors).

        May raise on truly unexpected failures — the orchestrator catches those.
        """
