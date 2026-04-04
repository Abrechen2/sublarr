"""Tests for cleanup_executors — language_filter, format_upgrade, orphan_files, orphan_db."""

import os
from unittest.mock import MagicMock, patch

import pytest


def test_language_filter_deletes_non_kept_languages(tmp_path):
    """Files not in keep_languages should be deleted; NFO files are never touched."""
    from services.cleanup_executors import execute_language_filter

    (tmp_path / "show.de.ass").write_text("german sub")
    (tmp_path / "show.en.srt").write_text("english sub")
    (tmp_path / "show.fr.ass").write_text("french sub")
    (tmp_path / "show.de.nfo").write_text("nfo file")  # never deleted

    config = {"keep_languages": ["de"]}
    result = execute_language_filter(str(tmp_path), config, dry_run=False)

    assert result["deleted"] == 2  # fr.ass + en.srt
    assert (tmp_path / "show.de.ass").exists()
    assert (tmp_path / "show.de.nfo").exists()
    assert not (tmp_path / "show.fr.ass").exists()
    assert not (tmp_path / "show.en.srt").exists()


def test_language_filter_dry_run_deletes_nothing(tmp_path):
    """dry_run=True must not delete any files."""
    from services.cleanup_executors import execute_language_filter

    (tmp_path / "show.fr.ass").write_text("french sub")
    config = {"keep_languages": ["de"]}
    result = execute_language_filter(str(tmp_path), config, dry_run=True)

    assert result["would_delete"] >= 1
    assert (tmp_path / "show.fr.ass").exists()


def test_format_upgrade_removes_srt_when_ass_exists(tmp_path):
    """SRT should be deleted when ASS exists for same base+language."""
    from services.cleanup_executors import execute_format_upgrade

    (tmp_path / "show.de.ass").write_text("german ass")
    (tmp_path / "show.de.srt").write_text("german srt")
    (tmp_path / "show.en.srt").write_text("english srt only")  # no ASS counterpart

    config = {"keep_format": "ass"}
    result = execute_format_upgrade(str(tmp_path), config, dry_run=False)

    assert result["deleted"] == 1  # only de.srt
    assert (tmp_path / "show.de.ass").exists()
    assert not (tmp_path / "show.de.srt").exists()
    assert (tmp_path / "show.en.srt").exists()  # kept, no ASS counterpart


def test_orphan_files_deletes_subs_without_video(tmp_path):
    """Subtitle without a video file in same dir should be detected as orphan."""
    from services.cleanup_executors import execute_orphan_files

    subdir = tmp_path / "nosub"
    subdir.mkdir()
    (subdir / "orphan.de.ass").write_text("sub without video")

    paired_dir = tmp_path / "paired"
    paired_dir.mkdir()
    (paired_dir / "movie.mkv").write_text("video")
    (paired_dir / "movie.de.ass").write_text("paired sub")

    result = execute_orphan_files(str(tmp_path), {}, dry_run=False)

    assert result["deleted"] == 1
    assert not (subdir / "orphan.de.ass").exists()
    assert (paired_dir / "movie.de.ass").exists()


def test_orphan_db_removes_stale_db_entries(tmp_path):
    """DB rows pointing to non-existent files should be removed."""
    from services.cleanup_executors import execute_orphan_db

    existing = str(tmp_path / "exists.de.ass")
    missing = str(tmp_path / "missing.de.ass")
    open(existing, "w").close()  # create the existing file

    mock_repo = MagicMock()
    mock_repo.get_all_subtitle_paths.return_value = [existing, missing]

    with patch("services.cleanup_executors.SubtitleRepository", return_value=mock_repo):
        result = execute_orphan_db({}, dry_run=False)

    assert result["deleted"] == 1
    mock_repo.delete_by_path.assert_called_once_with(missing)
