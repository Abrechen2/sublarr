"""Tests for scripts.migrate_subtitle_baks — legacy bak migration."""

from __future__ import annotations

from pathlib import Path

from scripts.migrate_subtitle_baks import migrate
from subtitle_filename import BAK_HIDDEN_DIR, BAK_SUBDIR


def _touch(p: Path, content: str = "x") -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


class TestMigrate:
    def test_moves_legacy_bak_to_canonical_subdir(self, tmp_path):
        series = tmp_path / "Show"
        series.mkdir()
        legacy = _touch(series / "ep.en.bak.srt", "backup-content")
        _touch(series / "ep.en.srt", "active")  # active sub still around

        result = migrate([str(tmp_path)])

        canonical = series / BAK_HIDDEN_DIR / BAK_SUBDIR / "ep.en.bak.srt"
        assert canonical.exists()
        assert canonical.read_text() == "backup-content"
        assert not legacy.exists()
        assert len(result.moved) == 1
        assert result.errors == []

    def test_idempotent_second_run_is_noop(self, tmp_path):
        series = tmp_path / "Show"
        series.mkdir()
        _touch(series / "ep.en.bak.srt")
        _touch(series / "ep.en.srt")

        first = migrate([str(tmp_path)])
        assert len(first.moved) == 1

        # Second pass: no legacy files left, no work to do
        second = migrate([str(tmp_path)])
        assert second.moved == []
        assert second.total_seen == 0  # nothing to walk except canonical (which we skip)

    def test_dry_run_does_not_move(self, tmp_path):
        series = tmp_path / "Show"
        series.mkdir()
        legacy = _touch(series / "ep.en.bak.srt")

        result = migrate([str(tmp_path)], dry_run=True)

        assert legacy.exists()
        canonical = series / BAK_HIDDEN_DIR / BAK_SUBDIR / "ep.en.bak.srt"
        assert not canonical.exists()
        assert len(result.moved) == 1  # reported as "would move"

    def test_skips_when_canonical_already_exists(self, tmp_path):
        """If a canonical bak already exists, never overwrite — that
        would silently destroy the user's freshest backup. Leave the
        legacy file in place and report the conflict."""
        series = tmp_path / "Show"
        series.mkdir()
        legacy = _touch(series / "ep.en.bak.srt", "old-legacy")
        canonical = series / BAK_HIDDEN_DIR / BAK_SUBDIR / "ep.en.bak.srt"
        canonical.parent.mkdir(parents=True)
        canonical.write_text("newer-canonical")

        result = migrate([str(tmp_path)])

        assert result.skipped_dest_exists == 1
        assert legacy.exists()  # legacy untouched
        assert canonical.read_text() == "newer-canonical"  # canonical untouched

    def test_handles_modifier_stack(self, tmp_path):
        """A legacy ``.en.hi.bak.srt`` (HI variant backup) must move to
        the canonical ``.sublarr/backups/<base>.en.hi.bak.srt`` — the
        modifier stack is preserved in the basename so restore still
        round-trips correctly."""
        series = tmp_path / "Show"
        series.mkdir()
        legacy = _touch(series / "ep.en.hi.bak.srt")

        migrate([str(tmp_path)])

        canonical = series / BAK_HIDDEN_DIR / BAK_SUBDIR / "ep.en.hi.bak.srt"
        assert canonical.exists()
        assert not legacy.exists()

    def test_skips_files_already_in_canonical_layout(self, tmp_path):
        """The walker must not yield files that already live inside
        ``.sublarr/backups/`` — they're the destination, not migration
        candidates."""
        series = tmp_path / "Show"
        series.mkdir()
        canonical_dir = series / BAK_HIDDEN_DIR / BAK_SUBDIR
        canonical_dir.mkdir(parents=True)
        _touch(canonical_dir / "already.en.bak.srt")

        result = migrate([str(tmp_path)])

        assert result.moved == []
        assert result.errors == []

    def test_ignores_unrelated_bak_files(self, tmp_path):
        """The remux pipeline writes ``<file>.mkv.<ts>.bak`` — these
        are NOT subtitle backups and must be left alone. Only files
        matching the ``.bak.<sub_ext>`` shape are migration candidates."""
        series = tmp_path / "Show"
        series.mkdir()
        _touch(series / "movie.mkv.123.bak", "container-backup")
        # No subtitle bak — migration is a no-op
        result = migrate([str(tmp_path)])
        assert result.moved == []
        assert (series / "movie.mkv.123.bak").exists()

    def test_handles_missing_media_root(self, tmp_path):
        ghost = str(tmp_path / "does-not-exist")
        result = migrate([ghost])
        assert result.moved == []
        assert result.errors == []

    def test_skips_files_inside_existing_hidden_dirs(self, tmp_path):
        """Files inside .sublarr/trash/ (or any other hidden dir) must
        be ignored — they're owned by the remux pipeline, not us."""
        series = tmp_path / "Show"
        series.mkdir()
        trash = series / BAK_HIDDEN_DIR / "trash"
        trash.mkdir(parents=True)
        stray = _touch(trash / "x.en.bak.srt")

        result = migrate([str(tmp_path)])

        assert result.moved == []
        assert stray.exists()  # not touched
