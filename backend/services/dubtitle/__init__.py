"""Dubtitle detection & selection package (roadmap A4 / issue #146)."""

from services.dubtitle.cache import (
    detect_dubtitle_cached,
    get_cached_detection,
    store_detection,
)
from services.dubtitle.detector import (
    DubtitleCandidate,
    DubtitleDetectionResult,
    ValidationResult,
    detect_dubtitle,
    result_to_dict,
    validate_subtitle_against_audio,
)

__all__ = [
    "DubtitleCandidate",
    "DubtitleDetectionResult",
    "ValidationResult",
    "detect_dubtitle",
    "detect_dubtitle_cached",
    "get_cached_detection",
    "result_to_dict",
    "store_detection",
    "validate_subtitle_against_audio",
]
