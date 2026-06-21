# Stub — completed in a later task. Holds the dataclasses checkers consume.
from __future__ import annotations

from dataclasses import dataclass, field

from services.subtitle_health.models import TargetKind


@dataclass
class Target:
    kind: TargetKind
    path: str
    stream_index: int | None
    lang: str
    codec: str
    raw: bytes


@dataclass
class ScanContext:
    episode_id: int | None
    video_path: str
    targets: list[Target] = field(default_factory=list)
