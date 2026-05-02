"""Tests for backend.subtitle_filename — the suffix-stripper parser."""

import os

import pytest

from subtitle_filename import (
    BAK_HIDDEN_DIR,
    BAK_SUBDIR,
    MODIFIERS,
    SUBTITLE_EXTS,
    active_path_for_bak,
    bak_dir_for,
    bak_path_for,
    find_existing_bak,
    is_backup_subtitle,
    is_subtitle_sidecar,
    legacy_bak_path_for,
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


class TestBakPathHelpers:
    """Helpers that translate between active sub paths and their backup
    locations. Backups live in ``<dir>/.sublarr/backups/`` since
    2026-05-02 — anything writing to or reading from a backup must go
    through these helpers, never inline ``f"{base}.bak{ext}"`` strings."""

    def test_bak_dir_for_uses_hidden_subdir(self):
        result = bak_dir_for("/m/Show/ep.en.srt")
        assert result == os.path.join("/m/Show", BAK_HIDDEN_DIR, BAK_SUBDIR)

    def test_bak_path_for_simple(self):
        result = bak_path_for("/m/Show/ep.en.srt")
        assert result == os.path.join("/m/Show", BAK_HIDDEN_DIR, BAK_SUBDIR, "ep.en.bak.srt")

    def test_bak_path_for_preserves_modifier_chain(self, tmp_path):
        """An HI sub's backup keeps the HI modifier in the basename so
        the restore path round-trips back to the HI sidecar."""
        active = str(tmp_path / "Show" / "ep.en.hi.srt")
        bak = bak_path_for(active)
        assert bak.endswith("ep.en.hi.bak.srt")
        # And reverse must round-trip
        assert active_path_for_bak(bak) == active

    def test_legacy_bak_path_for_returns_sibling(self, tmp_path):
        """The legacy helper produces the pre-2026-05-02 sibling path
        so readers can fall back when the canonical location is empty."""
        active = str(tmp_path / "ep.en.srt")
        expected = str(tmp_path / "ep.en.bak.srt")
        assert legacy_bak_path_for(active) == expected

    def test_active_path_for_bak_canonical_layout(self, tmp_path):
        series = tmp_path / "Show"
        bak = series / BAK_HIDDEN_DIR / BAK_SUBDIR / "ep.en.bak.srt"
        assert active_path_for_bak(str(bak)) == str(series / "ep.en.srt")

    def test_active_path_for_bak_legacy_layout(self, tmp_path):
        """Pre-migration sibling-located bak still resolves correctly —
        critical for the transition window during which both layouts
        coexist on disk."""
        series = tmp_path / "Show"
        bak = series / "ep.en.bak.srt"
        assert active_path_for_bak(str(bak)) == str(series / "ep.en.srt")

    def test_active_path_for_bak_returns_none_for_active(self):
        assert active_path_for_bak("/m/Show/ep.en.srt") is None

    def test_find_existing_bak_prefers_canonical(self, tmp_path):
        """When both layouts have a bak on disk, find_existing_bak
        returns the canonical hidden one — that's the location the
        new write path uses, so it must win."""
        active = tmp_path / "ep.en.srt"
        active.write_text("active")
        legacy = tmp_path / "ep.en.bak.srt"
        legacy.write_text("legacy")
        canonical_dir = tmp_path / BAK_HIDDEN_DIR / BAK_SUBDIR
        canonical_dir.mkdir(parents=True)
        canonical = canonical_dir / "ep.en.bak.srt"
        canonical.write_text("canonical")
        assert find_existing_bak(str(active)) == str(canonical)

    def test_find_existing_bak_falls_back_to_legacy(self, tmp_path):
        active = tmp_path / "ep.en.srt"
        active.write_text("active")
        legacy = tmp_path / "ep.en.bak.srt"
        legacy.write_text("legacy")
        assert find_existing_bak(str(active)) == str(legacy)

    def test_find_existing_bak_returns_none_when_absent(self, tmp_path):
        active = tmp_path / "ep.en.srt"
        active.write_text("active")
        assert find_existing_bak(str(active)) is None
