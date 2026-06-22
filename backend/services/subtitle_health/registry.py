"""Registry of active checkers."""

from services.subtitle_health.checkers import (
    ass_escape_leak,
    container_metadata_drift,
    empty_or_tiny,
    encoding_mojibake,
    format_mismatch,
    language_mislabel,
    missing_language,
    timing_sanity,
    unicode_control_chars,
)

CHECKERS = [
    ass_escape_leak.detect,
    language_mislabel.detect,
    empty_or_tiny.detect,
    encoding_mojibake.detect,
    timing_sanity.detect,
    format_mismatch.detect,
    unicode_control_chars.detect,
    container_metadata_drift.detect,
    missing_language.detect,
]
