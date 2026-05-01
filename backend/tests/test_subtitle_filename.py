"""Tests for backend.subtitle_filename — the suffix-stripper parser."""

import pytest

from subtitle_filename import (
    MODIFIERS,
    SUBTITLE_EXTS,
    is_backup_subtitle,
    is_subtitle_sidecar,
    parse_subtitle_filename,
)


class TestParseHappyPath:
    def test_simple_lang_only(self):
        r = parse_subtitle_filename("/m/Show.S01E01.de.srt")
        assert r is not None
        assert r.base == "Show.S01E01"
        assert r.language == "de"
        assert r.modifiers == ()
        assert r.extension == "srt"
        assert r.is_backup is False
        assert r.primary_modifier is None

    def test_3_letter_iso_639_2(self):
        r = parse_subtitle_filename("/m/Show.eng.srt")
        assert r is not None
        assert r.language == "eng"

    def test_ass_extension(self):
        r = parse_subtitle_filename("/m/Show.de.ass")
        assert r is not None
        assert r.extension == "ass"

    @pytest.mark.parametrize("ext", sorted(SUBTITLE_EXTS))
    def test_all_supported_exts(self, ext):
        r = parse_subtitle_filename(f"/m/x.de.{ext}")
        assert r is not None
        assert r.extension == ext


class TestParseBackup:
    def test_simple_bak(self):
        r = parse_subtitle_filename("/m/Show.en.bak.srt")
        assert r is not None
        assert r.language == "en"
        assert r.modifiers == ("bak",)
        assert r.is_backup is True
        assert r.primary_modifier is None

    def test_bak_uppercase_in_filename(self):
        r = parse_subtitle_filename("/m/Show.en.BAK.SRT")
        assert r is not None
        assert r.language == "en"
        assert r.modifiers == ("bak",)
        assert r.extension == "srt"


class TestParseModifiers:
    @pytest.mark.parametrize("modifier", sorted(MODIFIERS - {"bak"}))
    def test_each_modifier_recognised(self, modifier):
        r = parse_subtitle_filename(f"/m/Show.en.{modifier}.srt")
        assert r is not None
        assert r.language == "en"
        assert r.modifiers == (modifier,)
        assert r.is_backup is False
        assert r.primary_modifier == modifier

    def test_stacked_modifiers_hi_bak(self):
        """HI-variant that was modified — has both .hi and .bak."""
        r = parse_subtitle_filename("/m/Show.en.hi.bak.srt")
        assert r is not None
        assert r.language == "en"
        # Stripper pops right-to-left: bak first, then hi
        assert r.modifiers == ("bak", "hi")
        assert r.is_backup is True
        assert r.primary_modifier == "hi"

    def test_stacked_modifiers_other_order(self):
        r = parse_subtitle_filename("/m/Show.en.bak.hi.srt")
        assert r is not None
        assert r.modifiers == ("hi", "bak")

    def test_three_modifiers(self):
        r = parse_subtitle_filename("/m/Show.en.forced.hi.bak.srt")
        assert r is not None
        assert r.modifiers == ("bak", "hi", "forced")


class TestParseRejects:
    def test_no_extension_match(self):
        assert parse_subtitle_filename("/m/Show.de.mkv") is None

    def test_no_language(self):
        assert parse_subtitle_filename("/m/Show.srt") is None

    def test_bare_lang_no_base(self):
        assert parse_subtitle_filename("/m/de.srt") is None

    def test_invalid_language_4_letter(self):
        assert parse_subtitle_filename("/m/Show.engs.srt") is None

    def test_invalid_language_with_digits(self):
        assert parse_subtitle_filename("/m/Show.en1.srt") is None

    def test_uppercase_language_normalised(self):
        # Languages compared case-insensitively
        r = parse_subtitle_filename("/m/Show.EN.srt")
        assert r is not None
        assert r.language == "en"

    def test_dot_in_basename_doesnt_break(self):
        """Filenames with embedded dots ("Mr. Saturday") parse correctly."""
        r = parse_subtitle_filename("/m/Mr. Saturday Night S01E01.de.srt")
        assert r is not None
        assert r.base == "Mr. Saturday Night S01E01"
        assert r.language == "de"

    def test_modifier_only_no_language_rejected(self):
        # "Show.bak.srt" — no language slot, "bak" alone is not a lang
        assert parse_subtitle_filename("/m/Show.bak.srt") is None


class TestConvenienceWrappers:
    def test_is_subtitle_sidecar_true(self):
        assert is_subtitle_sidecar("/m/Show.de.srt") is True

    def test_is_subtitle_sidecar_false_for_video(self):
        assert is_subtitle_sidecar("/m/Show.mkv") is False

    def test_is_backup_subtitle_true(self):
        assert is_backup_subtitle("/m/Show.en.bak.srt") is True

    def test_is_backup_subtitle_false_for_active(self):
        assert is_backup_subtitle("/m/Show.en.srt") is False

    def test_is_backup_subtitle_false_for_non_sidecar(self):
        assert is_backup_subtitle("/m/Show.mkv") is False
