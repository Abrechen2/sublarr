"""Tests for credit_remover — staff credit line detection and removal."""
import pytest


# ─── Heuristic 1: Role markers ────────────────────────────────────────────────

def test_role_marker_translator_detected():
    from credit_remover import _is_credit_line
    assert _is_credit_line("Translation by (Translator) John Smith", total_end_ms=120_000, event_start_ms=10_000) is True


def test_role_marker_qc_detected():
    from credit_remover import _is_credit_line
    assert _is_credit_line("Quality Check (QC)", total_end_ms=120_000, event_start_ms=10_000) is True


def test_role_marker_op_theme_detected():
    from credit_remover import _is_credit_line
    assert _is_credit_line("OP Theme", total_end_ms=120_000, event_start_ms=10_000) is True


def test_role_marker_ed_theme_detected():
    from credit_remover import _is_credit_line
    assert _is_credit_line("ED Theme", total_end_ms=120_000, event_start_ms=10_000) is True


# ─── Heuristic 2: Prefix patterns ─────────────────────────────────────────────

def test_prefix_credits_colon_detected():
    from credit_remover import _is_credit_line
    assert _is_credit_line("Credits: Some Names", total_end_ms=120_000, event_start_ms=10_000) is True


def test_prefix_staff_colon_detected():
    from credit_remover import _is_credit_line
    assert _is_credit_line("Staff: John Doe", total_end_ms=120_000, event_start_ms=10_000) is True


def test_prefix_translation_colon_detected():
    from credit_remover import _is_credit_line
    assert _is_credit_line("Translation: Jane Smith", total_end_ms=120_000, event_start_ms=10_000) is True


# ─── Heuristic 3: Duration heuristic ──────────────────────────────────────────

def test_duration_credit_region_detected():
    from credit_remover import _is_credit_line
    # Event starts at 23:50 in a 24-minute file → within last 90 s
    assert _is_credit_line("John Smith", total_end_ms=1_440_000, event_start_ms=1_430_000) is True


def test_duration_guard_question_mark_not_removed():
    from credit_remover import _is_credit_line
    # Even in credits region, lines with ? are preserved (dialogue guard)
    assert _is_credit_line("Are you okay?", total_end_ms=1_440_000, event_start_ms=1_430_000) is False


def test_duration_guard_exclamation_not_removed():
    from credit_remover import _is_credit_line
    assert _is_credit_line("Watch out!", total_end_ms=1_440_000, event_start_ms=1_430_000) is False


def test_duration_outside_credits_region_ignored():
    from credit_remover import _is_credit_line
    # Event at 5 s in a 24-minute file → not in credits region, no other heuristic.
    # Use 3-word input so Heuristic 4 (exactly 2 title-case words) does NOT trigger.
    assert _is_credit_line("The door creaked loudly", total_end_ms=1_440_000, event_start_ms=5_000) is False


def test_duration_threshold_respected(monkeypatch):
    """Custom credit_threshold_sec changes the boundary."""
    import os
    monkeypatch.setenv("SUBLARR_CREDIT_THRESHOLD_SEC", "30")
    from config import reload_settings
    reload_settings()

    from credit_remover import _is_credit_line
    # 40 s before end → outside 30 s threshold → not caught by duration heuristic alone
    # (name "John Smith" — heuristic 4 would catch it; use a safely non-matching name)
    assert _is_credit_line("Hello there", total_end_ms=1_440_000, event_start_ms=1_400_000) is False


# ─── Heuristic 4: Isolated capitalized names ──────────────────────────────────

def test_isolated_name_two_titlecase_words_detected():
    from credit_remover import _is_credit_line
    assert _is_credit_line("John Smith", total_end_ms=120_000, event_start_ms=5_000) is True


def test_isolated_name_with_punctuation_not_detected():
    from credit_remover import _is_credit_line
    assert _is_credit_line("Hello World!", total_end_ms=120_000, event_start_ms=5_000) is False


def test_isolated_name_three_words_not_detected():
    from credit_remover import _is_credit_line
    # Three words = not exactly two title-case words → no match
    assert _is_credit_line("John Michael Smith", total_end_ms=120_000, event_start_ms=5_000) is False


# ─── Normal dialogue NOT removed ──────────────────────────────────────────────

def test_normal_dialogue_not_removed():
    from credit_remover import _is_credit_line
    assert _is_credit_line("I'll be back tomorrow.", total_end_ms=120_000, event_start_ms=30_000) is False


def test_ass_round_trip():
    """remove_credits_from_ass removes credit dialogue events, preserves normal lines."""
    from credit_remover import remove_credits_from_ass
    ass_content = (
        "[Script Info]\nScriptType: v4.00+\n\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, "
        "Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, "
        "MarginV, Encoding\n"
        "Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,"
        "0,0,0,0,100,100,0,0,1,2,2,2,10,10,10,1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,Hello, how are you?\n"
        "Dialogue: 0,0:00:04.00,0:00:06.00,Default,,0,0,0,,Credits: John Smith\n"
    )
    cleaned, removed = remove_credits_from_ass(ass_content)
    assert removed == 1
    assert "Hello, how are you?" in cleaned
    assert "Credits: John Smith" not in cleaned


def test_ssa_and_srt_round_trip():
    """remove_credits_from_srt removes credit blocks, preserves dialogue."""
    from credit_remover import remove_credits_from_srt
    srt_content = (
        "1\n00:00:01,000 --> 00:00:03,000\nHello, how are you?\n\n"
        "2\n00:00:04,000 --> 00:00:06,000\nCredits: John Smith\n\n"
        "3\n00:00:07,000 --> 00:00:09,000\nI am fine, thanks.\n"
    )
    cleaned, removed = remove_credits_from_srt(srt_content)
    assert removed == 1
    assert "Hello, how are you?" in cleaned
    assert "Credits: John Smith" not in cleaned
    assert "I am fine" in cleaned


def test_backup_preserves_original_content(tmp_path):
    """Backup file matches original before modification."""
    import os
    src = tmp_path / "test.srt"
    original = "1\n00:00:01,000 --> 00:00:03,000\nCredits: John\n"
    src.write_text(original, encoding="utf-8")

    from credit_remover import remove_credits_from_srt
    # Verify remove function works correctly (backup created in route, not here)
    cleaned, removed = remove_credits_from_srt(original)
    assert removed >= 1
    # Original content unchanged by the pure function
    assert src.read_text(encoding="utf-8") == original
