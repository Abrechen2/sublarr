"""Tests for subtitle export endpoints.

Covers two new endpoints (not yet implemented — all tests expected to FAIL):
  GET /api/v1/subtitles/download?path=<abs_path>
  GET /api/v1/series/<id>/subtitles/export

Run with:
  cd backend && python -m pytest tests/test_subtitle_export.py -v
"""

import io
import os
import sys
import zipfile
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ─── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def media_dir(tmp_path, monkeypatch):
    """Temp media dir set as SUBLARR_MEDIA_PATH for the duration of the test."""
    monkeypatch.setenv("SUBLARR_MEDIA_PATH", str(tmp_path))
    from config import reload_settings

    reload_settings()
    yield tmp_path
    reload_settings()


@pytest.fixture
def sub_client(temp_db, media_dir):
    """Test client + one .de.ass file inside media_dir."""
    from app import create_app

    season_dir = media_dir / "ShowName" / "Season 01"
    season_dir.mkdir(parents=True)
    sub_file = season_dir / "ShowName.S01E01.de.ass"
    sub_file.write_text("[Script Info]\nTitle: Test\n", encoding="utf-8")
    app = create_app(testing=True)
    with app.test_client() as c:
        yield c, sub_file, media_dir


# ─── TestSingleFileDownload ────────────────────────────────────────────────────


class TestSingleFileDownload:
    """Tests for GET /api/v1/subtitles/download?path="""

    def test_download_valid_subtitle(self, sub_client):
        """Valid .de.ass inside media_dir → 200 with file content."""
        client, sub_file, media_dir = sub_client
        resp = client.get(f"/api/v1/subtitles/download?path={sub_file}")
        assert resp.status_code == 200
        assert b"Script Info" in resp.data
        assert "attachment" in resp.headers.get("Content-Disposition", "")

    def test_download_missing_path_param(self, sub_client):
        """GET without path param → 400."""
        client, _sub_file, _media_dir = sub_client
        resp = client.get("/api/v1/subtitles/download")
        assert resp.status_code == 400

    def test_download_path_traversal(self, sub_client):
        """Requesting /etc/passwd → 403 (path traversal blocked)."""
        client, _sub_file, _media_dir = sub_client
        resp = client.get("/api/v1/subtitles/download?path=/etc/passwd")
        assert resp.status_code == 403

    def test_download_bad_extension(self, sub_client, media_dir):
        """Requesting a .py file → 403 (not a subtitle extension)."""
        client, _sub_file, _media_dir = sub_client
        bad_file = media_dir / "script.py"
        bad_file.write_text("print('hello')", encoding="utf-8")
        resp = client.get(f"/api/v1/subtitles/download?path={bad_file}")
        assert resp.status_code == 403

    def test_download_missing_file(self, sub_client, media_dir):
        """Requesting a file that does not exist → 404."""
        client, _sub_file, _media_dir = sub_client
        missing = media_dir / "nonexistent.de.srt"
        resp = client.get(f"/api/v1/subtitles/download?path={missing}")
        assert resp.status_code == 404

    @pytest.mark.parametrize("ext", [".ass", ".srt", ".vtt", ".ssa", ".sub"])
    def test_download_allowed_extensions(self, sub_client, media_dir, ext):
        """All allowed subtitle extensions are served as file attachments."""
        client, _sub_file, _media_dir = sub_client
        allowed_file = media_dir / f"ShowName.S01E01.de{ext}"
        allowed_file.write_text("[Script Info]\nTitle: Test\n", encoding="utf-8")
        resp = client.get(f"/api/v1/subtitles/download?path={allowed_file}")
        assert resp.status_code == 200
        assert "attachment" in resp.headers.get("Content-Disposition", "")


# ─── TestSeriesZipExport ───────────────────────────────────────────────────────


class TestSeriesZipExport:
    """Tests for GET /api/v1/series/<id>/subtitles/export"""

    def test_export_series_zip_basic(self, sub_client):
        """Basic export → 200, application/zip, attachment header, ZIP contains .de.ass."""
        client, _sub_file, media_dir = sub_client
        series_path = str(media_dir / "ShowName")

        with patch("routes.subtitles._get_series_path", return_value=series_path):
            resp = client.get("/api/v1/series/1/subtitles/export")

        assert resp.status_code == 200
        assert "application/zip" in resp.content_type
        assert "attachment" in resp.headers.get("Content-Disposition", "")

        with zipfile.ZipFile(io.BytesIO(resp.data)) as zf:
            names = zf.namelist()
        assert any("de.ass" in name for name in names)

    def test_export_series_zip_lang_filter(self, sub_client, media_dir):
        """?lang=de filters to only German subs; English subs excluded."""
        client, _sub_file, _media_dir = sub_client

        # Add an English subtitle alongside the existing German one
        en_file = media_dir / "ShowName" / "Season 01" / "ShowName.S01E01.en.srt"
        en_file.write_text("1\n00:00:01,000 --> 00:00:03,000\nHello\n", encoding="utf-8")

        series_path = str(media_dir / "ShowName")

        with patch("routes.subtitles._get_series_path", return_value=series_path):
            resp = client.get("/api/v1/series/1/subtitles/export?lang=de")

        assert resp.status_code == 200

        with zipfile.ZipFile(io.BytesIO(resp.data)) as zf:
            names = zf.namelist()

        assert all("de" in name for name in names), f"Expected only 'de' files, got: {names}"
        assert not any("en" in name for name in names), f"Unexpected 'en' file in: {names}"

    def test_export_series_zip_not_found(self, sub_client):
        """_get_series_path returns None → 404."""
        client, _sub_file, _media_dir = sub_client

        with patch("routes.subtitles._get_series_path", return_value=None):
            resp = client.get("/api/v1/series/99/subtitles/export")

        assert resp.status_code == 404

    def test_export_series_zip_path_safety(self, sub_client):
        """_get_series_path returns /etc → 403 (outside media_dir)."""
        client, _sub_file, _media_dir = sub_client

        with patch("routes.subtitles._get_series_path", return_value="/etc"):
            resp = client.get("/api/v1/series/1/subtitles/export")

        assert resp.status_code == 403

    def test_export_series_zip_size_limit(self, sub_client, media_dir, monkeypatch):
        """Single subtitle exceeding 50 MB → 413 Payload Too Large."""
        client, _sub_file, _media_dir = sub_client

        season_dir = media_dir / "ShowName" / "Season 01"
        big_file = season_dir / "big.de.ass"
        big_file.write_bytes(b"X" * (51 * 1024 * 1024))

        series_path = str(media_dir / "ShowName")

        def fake_scan(series_path_arg):
            return [{"path": str(big_file), "language": "de", "format": "ass"}]

        monkeypatch.setattr("routes.subtitles._scan_series_subtitles", fake_scan)

        with patch("routes.subtitles._get_series_path", return_value=series_path):
            resp = client.get("/api/v1/series/1/subtitles/export")

        assert resp.status_code == 413
