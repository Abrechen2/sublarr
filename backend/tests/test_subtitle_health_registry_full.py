from services.subtitle_health.registry import CHECKERS


def test_all_nine_checkers_registered():
    names = {c.__module__.rsplit(".", 1)[-1] for c in CHECKERS}
    assert names == {
        "ass_escape_leak",
        "language_mislabel",
        "empty_or_tiny",
        "encoding_mojibake",
        "timing_sanity",
        "format_mismatch",
        "unicode_control_chars",
        "container_metadata_drift",
        "missing_language",
    }
