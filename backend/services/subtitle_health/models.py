"""Dataclasses describing subtitle-health findings."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class IssueType(StrEnum):
    ASS_ESCAPE_LEAK = "ass_escape_leak"
    LANGUAGE_MISLABEL = "language_mislabel"
    # Emitted by Plan 2 checkers (scaffolding):
    EMPTY_OR_TINY = "empty_or_tiny"
    ENCODING_MOJIBAKE = "encoding_mojibake"
    TIMING_SANITY = "timing_sanity"
    MISSING_LANGUAGE = "missing_language"
    FORMAT_MISMATCH = "format_mismatch"
    UNICODE_CONTROL_CHARS = "unicode_control_chars"
    CONTAINER_METADATA_DRIFT = "container_metadata_drift"


class Severity(StrEnum):
    CONFIRMED = "confirmed"
    SUSPICIOUS = "suspicious"
    INFO = "info"


class TargetKind(StrEnum):
    SIDECAR = "sidecar"
    EMBEDDED = "embedded"


@dataclass
class Issue:
    type: IssueType
    severity: Severity
    episode_id: int | None
    target_kind: TargetKind
    target_path: str
    stream_index: int | None
    lang: str
    count: int
    snippets: list[str]
    raw_hash: str
    fixable: bool
    suggested_fix: str | None
    # Persisted finding id, backfilled by persist_scan_result so the API
    # response carries the id the fix endpoint needs. None for a fresh,
    # not-yet-persisted issue.
    id: int | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type.value,
            "severity": self.severity.value,
            "episode_id": self.episode_id,
            "target_kind": self.target_kind.value,
            "target_path": self.target_path,
            "stream_index": self.stream_index,
            "lang": self.lang,
            "count": self.count,
            "snippets": list(self.snippets[:3]),
            "raw_hash": self.raw_hash,
            "fixable": self.fixable,
            "suggested_fix": self.suggested_fix,
        }


@dataclass
class ScanResult:
    episode_id: int | None
    video_path: str
    issues: list[Issue] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "episode_id": self.episode_id,
            "video_path": self.video_path,
            "healthy": len(self.issues) == 0,
            "issue_count": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
        }
