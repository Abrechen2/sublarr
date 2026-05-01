"""Tests for services.subtitle_backups + the matching API routes."""

import os
from pathlib import Path

import pytest

from services.subtitle_backups import (
    cleanup_subtitle_baks,
    derive_active_sub_path,
    derive_video_path,
    is_orphan,
    iter_subtitle_baks,
    list_subtitle_baks,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _touch(directory: Path, name: str, content: str = "x") -> Path:
    p = directory / name
    p.write_text(content, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Path derivation
# ---------------------------------------------------------------------------


class TestDeriveActiveSubPath:
    def test_simple_bak_strips_only_bak(self, tmp_path):
        bak = tmp_path / "ep.en.bak.srt"
        active = derive_active_sub_path(str(bak))
        assert active == str(tmp_path / "ep.en.srt")

    def test_hi_bak_preserves_hi(self, tmp_path):
        """A bak of the HI variant must restore back to the HI sidecar,
        not silently change which file gets the modifier."""
        bak = tmp_path / "ep.en.hi.bak.srt"
        active = derive_active_sub_path(str(bak))
        assert active == str(tmp_path / "ep.en.hi.srt")

    def test_non_bak_returns_none(self, tmp_path):
        plain = tmp_path / "ep.en.srt"
        assert derive_active_sub_path(str(plain)) is None


class TestDeriveVideoPath:
    def test_finds_existing_mkv(self, tmp_path):
        _touch(tmp_path, "ep.mkv")
        bak = tmp_path / "ep.en.bak.srt"
        assert derive_video_path(str(bak)) == str(tmp_path / "ep.mkv")

    def test_returns_none_when_no_video(self, tmp_path):
        bak = tmp_path / "ep.en.bak.srt"
        assert derive_video_path(str(bak)) is None

    def test_picks_mp4_when_mkv_absent(self, tmp_path):
        _touch(tmp_path, "ep.mp4")
        bak = tmp_path / "ep.en.bak.srt"
        assert derive_video_path(str(bak)) == str(tmp_path / "ep.mp4")


# ---------------------------------------------------------------------------
# Orphan detection
# ---------------------------------------------------------------------------


class TestIsOrphan:
    def test_not_orphan_when_active_sub_exists(self, tmp_path):
        _touch(tmp_path, "ep.en.srt")  # active sub still around
        bak = _touch(tmp_path, "ep.en.bak.srt")
        assert is_orphan(str(bak)) is False

    def test_not_orphan_when_video_exists(self, tmp_path):
        _touch(tmp_path, "ep.mkv")  # video still around, sub deleted manually
        bak = _touch(tmp_path, "ep.en.bak.srt")
        assert is_orphan(str(bak)) is False

    def test_orphan_when_neither_active_sub_nor_video(self, tmp_path):
        # User deleted both video AND active sub; bak is left dangling
        bak = _touch(tmp_path, "ep.en.bak.srt")
        assert is_orphan(str(bak)) is True


# ---------------------------------------------------------------------------
# iter_subtitle_baks
# ---------------------------------------------------------------------------


class TestIterSubtitleBaks:
    def test_yields_only_bak_files(self, tmp_path):
        _touch(tmp_path, "ep.en.srt")  # active
        bak = _touch(tmp_path, "ep.en.bak.srt")
        _touch(tmp_path, "ep.mkv")
        _touch(tmp_path, "ep.de.hi.srt")  # modifier sub, not a bak

        result = list(iter_subtitle_baks([str(tmp_path)]))
        assert result == [str(bak)]

    def test_skips_hidden_dirs(self, tmp_path):
        """Trash dirs (.sublarr, .sublarr_trash) start with `.` and must
        be pruned during the walk, otherwise the cleanup pipeline would
        nuke files the remux module is keeping deliberately."""
        hidden = tmp_path / ".sublarr"
        hidden.mkdir()
        _touch(hidden, "x.en.bak.srt")  # should NOT appear

        visible = tmp_path / "Show"
        visible.mkdir()
        bak = _touch(visible, "ep.en.bak.srt")

        result = list(iter_subtitle_baks([str(tmp_path)]))
        assert result == [str(bak)]

    def test_handles_missing_root(self, tmp_path):
        ghost = str(tmp_path / "does-not-exist")
        assert list(iter_subtitle_baks([ghost])) == []


# ---------------------------------------------------------------------------
# list_subtitle_baks
# ---------------------------------------------------------------------------


class TestListSubtitleBaks:
    def test_includes_orphan_flag(self, tmp_path):
        bak = _touch(tmp_path, "ep.en.bak.srt")
        result = list_subtitle_baks([str(tmp_path)])
        assert len(result) == 1
        entry = result[0]
        assert entry["path"] == str(bak)
        assert entry["language"] == "en"
        assert entry["is_orphan"] is True
        assert entry["restore_path"] == str(tmp_path / "ep.en.srt")
        assert entry["video_path"] is None
        assert entry["expires_at"] is None  # retention=0 disables expiry

    def test_with_retention_populates_expires_at(self, tmp_path):
        _touch(tmp_path, "ep.en.bak.srt")
        result = list_subtitle_baks([str(tmp_path)], retention_days=30)
        assert result[0]["expires_at"] is not None
        assert "T" in result[0]["expires_at"]  # ISO format

    def test_series_path_filter(self, tmp_path):
        s1 = tmp_path / "Show A"
        s2 = tmp_path / "Show B"
        s1.mkdir()
        s2.mkdir()
        _touch(s1, "a.en.bak.srt")
        _touch(s2, "b.en.bak.srt")

        result = list_subtitle_baks([str(tmp_path)], series_path_filter=str(s1))
        assert len(result) == 1
        assert result[0]["path"].startswith(str(s1))

    def test_modifiers_field_exposes_full_stack(self, tmp_path):
        _touch(tmp_path, "ep.en.hi.bak.srt")
        result = list_subtitle_baks([str(tmp_path)])
        assert "bak" in result[0]["modifiers"]
        assert "hi" in result[0]["modifiers"]


# ---------------------------------------------------------------------------
# cleanup_subtitle_baks
# ---------------------------------------------------------------------------


class TestCleanupSubtitleBaks:
    def test_no_criteria_returns_note(self, tmp_path):
        result = cleanup_subtitle_baks([str(tmp_path)], older_than_days=0, orphans_only=False)
        assert result["deleted"] == []
        assert "note" in result

    def test_older_than_deletes_old_baks(self, tmp_path):
        # Create an old bak (modify mtime to 60 days ago) + active sub so
        # it is NOT an orphan — exercises the pure age path.
        _touch(tmp_path, "ep.en.srt")
        old_bak = _touch(tmp_path, "ep.en.bak.srt")
        old_time = os.path.getmtime(old_bak) - 60 * 86400
        os.utime(old_bak, (old_time, old_time))

        result = cleanup_subtitle_baks([str(tmp_path)], older_than_days=30)
        assert str(old_bak) in result["deleted"]
        assert not old_bak.exists()
        assert result["orphans_purged"] == 0

    def test_recent_baks_skipped_under_ttl(self, tmp_path):
        _touch(tmp_path, "ep.en.srt")
        recent = _touch(tmp_path, "ep.en.bak.srt")
        result = cleanup_subtitle_baks([str(tmp_path)], older_than_days=30)
        assert recent.exists()
        assert result["skipped"] == 1
        assert result["deleted"] == []

    def test_orphans_purged_immediately_regardless_of_age(self, tmp_path):
        """Orphan baks are deleted regardless of TTL because they no
        longer protect anything (Gemini-Pro 2026-05-01 design note)."""
        orphan = _touch(tmp_path, "ep.en.bak.srt")  # no video, no active sub
        # Recent mtime — would normally skip under 30d retention
        result = cleanup_subtitle_baks([str(tmp_path)], older_than_days=30)
        assert str(orphan) in result["deleted"]
        assert result["orphans_purged"] == 1

    def test_orphans_only_skips_aged_non_orphans(self, tmp_path):
        # Old bak with intact active sub (not orphan) — must survive
        _touch(tmp_path, "old.en.srt")
        old_with_active = _touch(tmp_path, "old.en.bak.srt")
        old_time = os.path.getmtime(old_with_active) - 365 * 86400
        os.utime(old_with_active, (old_time, old_time))

        # Orphan bak — should be deleted even in orphans_only mode
        orphan = _touch(tmp_path, "ghost.en.bak.srt")

        result = cleanup_subtitle_baks([str(tmp_path)], older_than_days=30, orphans_only=True)
        assert str(orphan) in result["deleted"]
        assert old_with_active.exists()
        assert result["orphans_purged"] == 1

    def test_dry_run_reports_without_deleting(self, tmp_path):
        bak = _touch(tmp_path, "ep.en.bak.srt")  # orphan
        result = cleanup_subtitle_baks([str(tmp_path)], older_than_days=30, dry_run=True)
        assert str(bak) in result["deleted"]
        assert bak.exists()  # still on disk
        assert result["dry_run"] is True


# ---------------------------------------------------------------------------
# HTTP endpoints (smoke tests via Flask test client)
# ---------------------------------------------------------------------------


@pytest.fixture
def client_with_media(temp_db, tmp_path):
    """Stand up the Flask app with media_path pointed at a temp dir.

    The ``temp_db`` fixture (from conftest.py) sets ``SUBLARR_API_KEY=""``
    which disables auth for the test client. We then patch the
    settings accessor used by the route handler to point ``media_path``
    at our fixture's temp directory so the bak walker actually finds
    our test files.
    """
    from unittest.mock import MagicMock, patch

    from app import create_app

    fake_settings = MagicMock()
    fake_settings.media_path = str(tmp_path)
    fake_settings.extra_media_paths = ""
    fake_settings.subtitle_bak_retention_days = 30

    app = create_app(testing=True)
    app.config["TESTING"] = True

    with (
        patch("routes.subtitle_processor.get_settings", return_value=fake_settings),
        app.test_client() as c,
    ):
        yield c, tmp_path


class TestSubtitleBackupsRoutes:
    def test_list_endpoint_returns_baks(self, client_with_media):
        client, tmp_path = client_with_media
        _touch(tmp_path, "ep.en.bak.srt")  # orphan

        resp = client.get("/api/v1/library/subtitle-backups")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["count"] == 1
        assert data["orphan_count"] == 1
        assert data["retention_days"] == 30
        assert data["backups"][0]["language"] == "en"
        assert data["backups"][0]["is_orphan"] is True

    def test_cleanup_dry_run(self, client_with_media):
        client, tmp_path = client_with_media
        _touch(tmp_path, "ep.en.bak.srt")  # orphan

        resp = client.post(
            "/api/v1/library/subtitle-backups/cleanup",
            json={"orphans_only": True, "dry_run": True},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["orphans_purged"] == 1
        assert data["dry_run"] is True
        assert (tmp_path / "ep.en.bak.srt").exists()

    def test_cleanup_actually_deletes(self, client_with_media):
        client, tmp_path = client_with_media
        bak = _touch(tmp_path, "ep.en.bak.srt")  # orphan

        resp = client.post(
            "/api/v1/library/subtitle-backups/cleanup",
            json={"orphans_only": True},
        )
        assert resp.status_code == 200
        assert not bak.exists()

    def test_list_with_invalid_series_path_returns_403(self, client_with_media):
        client, _tmp = client_with_media
        resp = client.get("/api/v1/library/subtitle-backups?series_path=/etc")
        assert resp.status_code == 403
