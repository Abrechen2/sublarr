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

    # permanent_delete=True bypasses the trash-dir resolver, which on CI
    # may fall outside tmp_path. The new audit tests in
    # test_extract_cleanup_audit_2026_05_09.py cover the trash-by-default
    # path with a patched media_path; this test covers the hard-delete path.
    config = {"keep_languages": ["de"], "permanent_delete": True}
    result = execute_language_filter(str(tmp_path), config, dry_run=False)

    assert result["deleted"] == 2  # fr.ass + en.srt
    assert (tmp_path / "show.de.ass").exists()
    assert (tmp_path / "show.de.nfo").exists()
    assert not (tmp_path / "show.fr.ass").exists()
    assert not (tmp_path / "show.en.srt").exists()


def test_language_filter_keeps_language_variants(tmp_path):
    """keep_languages=['de'] must also keep .deu.ass and .ger.ass variants."""
    from services.cleanup_executors import execute_language_filter

    (tmp_path / "show.de.ass").write_text("german iso-1")
    (tmp_path / "show.deu.ass").write_text("german iso-2")
    (tmp_path / "show.ger.ass").write_text("german iso-legacy")
    (tmp_path / "show.german.ass").write_text("german full")
    (tmp_path / "show.fr.ass").write_text("french sub")

    config = {"keep_languages": ["de"], "permanent_delete": True}
    result = execute_language_filter(str(tmp_path), config, dry_run=False)

    assert result["deleted"] == 1  # only fr.ass
    assert (tmp_path / "show.de.ass").exists()
    assert (tmp_path / "show.deu.ass").exists()
    assert (tmp_path / "show.ger.ass").exists()
    assert (tmp_path / "show.german.ass").exists()
    assert not (tmp_path / "show.fr.ass").exists()


def test_language_filter_dry_run_deletes_nothing(tmp_path):
    """dry_run=True must not delete any files."""
    from services.cleanup_executors import execute_language_filter

    (tmp_path / "show.fr.ass").write_text("french sub")
    config = {"keep_languages": ["de"]}
    result = execute_language_filter(str(tmp_path), config, dry_run=True)

    assert result["would_delete"] >= 1
    assert (tmp_path / "show.fr.ass").exists()


def _foreign_probe(*_args, **_kwargs):
    """Fake ffprobe result: ger + eng kept, jpn + ita are foreign, und present."""
    return {
        "streams": [
            {"codec_type": "video", "index": 0},
            {"codec_type": "subtitle", "index": 1, "tags": {"language": "ger"}},
            {"codec_type": "subtitle", "index": 2, "tags": {"language": "eng"}},
            {"codec_type": "subtitle", "index": 3, "tags": {"language": "jpn"}},
            {"codec_type": "subtitle", "index": 4, "tags": {"language": "ita"}},
            {"codec_type": "subtitle", "index": 5, "tags": {"language": "und"}},
        ]
    }


def test_foreign_tracks_dry_run_reports_without_stripping(tmp_path):
    """dry_run reports foreign tracks (jpn+ita) and never calls the strip."""
    from services.cleanup_executors import execute_foreign_tracks

    (tmp_path / "show.mkv").write_bytes(b"video")
    strip = MagicMock()
    with (
        patch("remux.get_media_streams", _foreign_probe),
        patch("remux.remove_foreign_subtitle_streams", strip),
    ):
        result = execute_foreign_tracks(
            str(tmp_path), {"keep_languages": ["de", "en"], "keep_und": True}, dry_run=True
        )

    assert result["would_strip_files"] == 1
    assert result["would_strip_tracks"] == 2  # jpn + ita (und kept)
    assert result["examples"][0]["langs"] == ["ita", "jpn"]
    strip.assert_not_called()


def test_foreign_tracks_execute_strips_foreign(tmp_path):
    """execute calls remove_foreign_subtitle_streams with de+en variants kept."""
    from services.cleanup_executors import execute_foreign_tracks

    (tmp_path / "show.mkv").write_bytes(b"video")
    strip = MagicMock(return_value="/media/.sublarr/trash/2026/show.mkv.123.bak")
    with (
        patch("remux.get_media_streams", _foreign_probe),
        patch("remux.remove_foreign_subtitle_streams", strip),
    ):
        result = execute_foreign_tracks(
            str(tmp_path), {"keep_languages": ["de", "en"], "keep_und": True}, dry_run=False
        )

    assert result["stripped_files"] == 1
    assert result["tracks_removed"] == 2
    strip.assert_called_once()
    kept = strip.call_args.kwargs["target_languages"]
    assert {"ger", "deu", "eng"}.issubset(kept)  # expanded to raw ffprobe tags
    assert strip.call_args.kwargs["keep_und"] is True


def test_foreign_tracks_refreshes_media_servers_after_strip(tmp_path):
    """A successful strip triggers a media-server refresh for the video."""
    from services.cleanup_executors import execute_foreign_tracks

    (tmp_path / "show.mkv").write_bytes(b"video")
    notify = MagicMock()
    with (
        patch("remux.get_media_streams", _foreign_probe),
        patch("remux.remove_foreign_subtitle_streams", MagicMock(return_value="bak")),
        patch("services.media_server_notify.notify_media_servers", notify),
    ):
        execute_foreign_tracks(
            str(tmp_path), {"keep_languages": ["de", "en"], "keep_und": True}, dry_run=False
        )

    notify.assert_called_once_with(str(tmp_path / "show.mkv"))


def test_foreign_tracks_dry_run_does_not_refresh(tmp_path):
    """Dry-run must not trigger any media-server refresh."""
    from services.cleanup_executors import execute_foreign_tracks

    (tmp_path / "show.mkv").write_bytes(b"video")
    notify = MagicMock()
    with (
        patch("remux.get_media_streams", _foreign_probe),
        patch("services.media_server_notify.notify_media_servers", notify),
    ):
        execute_foreign_tracks(
            str(tmp_path), {"keep_languages": ["de", "en"], "keep_und": True}, dry_run=True
        )

    notify.assert_not_called()


def test_foreign_tracks_empty_keep_aborts(tmp_path):
    """An empty keep_languages must abort, never strip every track."""
    from services.cleanup_executors import execute_foreign_tracks

    (tmp_path / "show.mkv").write_bytes(b"video")
    result = execute_foreign_tracks(str(tmp_path), {"keep_languages": []}, dry_run=False)
    assert result.get("aborted") == "empty keep_languages"
    assert result["stripped_files"] == 0


def test_foreign_tracks_keep_und_false_strips_und(tmp_path):
    """keep_und=False adds the undetermined track to the strip set."""
    from services.cleanup_executors import execute_foreign_tracks

    (tmp_path / "show.mkv").write_bytes(b"video")
    with (
        patch("remux.get_media_streams", _foreign_probe),
        patch("remux.remove_foreign_subtitle_streams", MagicMock(return_value="bak")),
    ):
        result = execute_foreign_tracks(
            str(tmp_path), {"keep_languages": ["de", "en"], "keep_und": False}, dry_run=True
        )
    assert result["would_strip_tracks"] == 3  # jpn + ita + und


def test_format_upgrade_removes_srt_when_ass_exists(tmp_path):
    """SRT should be deleted when ASS exists for same base+language."""
    from services.cleanup_executors import execute_format_upgrade

    (tmp_path / "show.de.ass").write_text("german ass")
    (tmp_path / "show.de.srt").write_text("german srt")
    (tmp_path / "show.en.srt").write_text("english srt only")  # no ASS counterpart

    config = {"keep_format": "ass", "permanent_delete": True}
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

    result = execute_orphan_files(str(tmp_path), {"permanent_delete": True}, dry_run=False)

    assert result["deleted"] == 1
    assert not (subdir / "orphan.de.ass").exists()
    assert (paired_dir / "movie.de.ass").exists()


def test_orphan_db_removes_stale_db_entries(tmp_path):
    """DB rows pointing to non-existent files should be batch-removed.

    Audit C2-2: previously the executor called ``delete_by_path`` once
    per missing row (N+1). It now collects every missing path and
    issues a single ``delete_by_paths`` call.
    """
    from services.cleanup_executors import execute_orphan_db

    existing = str(tmp_path / "exists.de.ass")
    missing = str(tmp_path / "missing.de.ass")
    open(existing, "w").close()  # create the existing file

    mock_repo = MagicMock()
    mock_repo.get_all_subtitle_paths.return_value = [existing, missing]
    mock_repo.delete_by_paths.return_value = 1

    # Pin media_path to tmp_path so the new mount-reachability probe
    # passes during the unit test.
    fake_settings = MagicMock()
    fake_settings.media_path = str(tmp_path)

    with (
        patch("services.cleanup_executors.SubtitleRepository", return_value=mock_repo),
        patch("config.get_settings", return_value=fake_settings),
    ):
        result = execute_orphan_db({}, dry_run=False)

    assert result["deleted"] == 1
    mock_repo.delete_by_paths.assert_called_once_with([missing])


def test_subtitle_walk_skips_sublarr_trash(tmp_path):
    """Sidecar walks must NOT descend into the .sublarr trash subtree.

    Already-trashed foreign sidecars live under .sublarr/trash/<date>/ with
    no matching video. Before the exclusion, language_filter re-walked them
    every night and tried to re-trash them (prod: 5922 Permission-denied
    WARNINGs, and orphan_files counted 27k of them as orphans). The trash
    subtree must be pruned exactly like _video_files already does.
    """
    from services.cleanup_executors import execute_language_filter

    # A live foreign sidecar at the top level — must be removed (control).
    (tmp_path / "show.fr.ass").write_text("french sub")
    # Trashed foreign sidecars under .sublarr — must be left untouched.
    trash = tmp_path / ".sublarr" / "trash" / "2026-06-13"
    trash.mkdir(parents=True)
    (trash / "Old.ara.ass").write_text("trashed arabic")
    (trash / "Old.spa.srt").write_text("trashed spanish")

    config = {"keep_languages": ["de"], "permanent_delete": True}
    result = execute_language_filter(str(tmp_path), config, dry_run=False)

    assert result["deleted"] == 1  # only the live top-level fr.ass
    assert not (tmp_path / "show.fr.ass").exists()
    assert (trash / "Old.ara.ass").exists()
    assert (trash / "Old.spa.srt").exists()
