"""Dubtitle detection & selection package (roadmap A4 / issue #146)."""

from services.dubtitle.detector import (
    DubtitleCandidate,
    DubtitleDetectionResult,
    ValidationResult,
    detect_dubtitle,
    validate_subtitle_against_audio,
)

__all__ = [
    "DubtitleCandidate",
    "DubtitleDetectionResult",
    "ValidationResult",
    "detect_dubtitle",
    "validate_subtitle_against_audio",
]
