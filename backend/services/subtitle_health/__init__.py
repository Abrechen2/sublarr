"""Subtitle Health — detect-and-repair framework for subtitle content defects.

See docs/superpowers/specs/2026-06-21-subtitle-health-design.md.
"""

from services.subtitle_health.models import (
    Issue,
    IssueType,
    ScanResult,
    Severity,
    TargetKind,
)
from services.subtitle_health.scan import scan_episode

__all__ = ["Issue", "IssueType", "ScanResult", "Severity", "TargetKind", "scan_episode"]
