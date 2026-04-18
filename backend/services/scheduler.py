"""Sublarr scheduler service — APScheduler facade + JobSpec registry.

This file will grow across Phase 1 tasks; at this point it only
contains JobSpec + compute_default_misfire_grace_time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from apscheduler.triggers.base import BaseTrigger
from apscheduler.triggers.interval import IntervalTrigger


def compute_default_misfire_grace_time(trigger: BaseTrigger) -> int:
    """Return the default misfire grace (seconds) for a trigger.

    - IntervalTrigger: half of the interval in seconds.
    - CronTrigger (and anything else): 60 seconds.
    """
    if isinstance(trigger, IntervalTrigger):
        total = int(trigger.interval.total_seconds())
        return max(1, total // 2)
    return 60


@dataclass(frozen=True)
class JobSpec:
    """Declarative spec for a recurring scheduled job.

    Fields:
      id: stable identifier; used as the JobStore row key.
      func: tick function taking no args; must be idempotent.
      default_trigger: IntervalTrigger or CronTrigger used when no
        user override exists in the JobStore.
      timeout_s: enforced by _tick_wrapper via ThreadPoolExecutor.
      max_instances: APScheduler concurrency cap (defaults to 1).
      coalesce: collapse missed fires into one on resume.
      misfire_grace_time: None means computed at registration from
        compute_default_misfire_grace_time.
      owner_module: module path shown in the UI for grouping/debug.
      description: human-readable summary shown in the UI.
    """

    id: str
    func: Callable[[], None]
    default_trigger: BaseTrigger
    timeout_s: int = 300
    max_instances: int = 1
    coalesce: bool = True
    misfire_grace_time: int | None = None
    owner_module: str = ""
    description: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("JobSpec.id must be non-empty string")
        if not callable(self.func):
            raise TypeError("JobSpec.func must be callable")
        if not isinstance(self.timeout_s, int) or self.timeout_s <= 0:
            raise ValueError(f"JobSpec.timeout_s must be > 0 (got {self.timeout_s!r})")
        if not isinstance(self.default_trigger, BaseTrigger):
            raise TypeError("JobSpec.default_trigger must be a BaseTrigger subclass")
