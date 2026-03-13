import json
from datetime import datetime
from unittest.mock import patch

from db.models.core import ChapterCache


class TestChapterCacheModel:
    def test_tablename(self):
        assert ChapterCache.__tablename__ == "chapter_cache"

    def test_has_required_columns(self):
        cols = {c.key for c in ChapterCache.__table__.columns}
        assert "file_path" in cols
        assert "mtime" in cols
        assert "chapters_json" in cols
        assert "cached_at" in cols


class TestNormalizeChapter:
    def test_full_fields(self):
        from chapters import _normalize_chapter

        raw = {
            "id": 0,
            "start_time": "0.000000",
            "end_time": "90.500000",
            "tags": {"title": "Opening"},
        }
        result = _normalize_chapter(raw)
        assert result == {
            "id": 0,
            "title": "Opening",
            "start_ms": 0,
            "end_ms": 90500,
        }

    def test_missing_title_uses_fallback(self):
        from chapters import _normalize_chapter

        raw = {"id": 2, "start_time": "300.000", "end_time": "600.000", "tags": {}}
        result = _normalize_chapter(raw)
        assert result["title"] == "Chapter 3"

    def test_no_tags_key(self):
        from chapters import _normalize_chapter

        raw = {"id": 0, "start_time": "0.0", "end_time": "30.0"}
        result = _normalize_chapter(raw)
        assert result["title"] == "Chapter 1"
        assert result["start_ms"] == 0
        assert result["end_ms"] == 30000


class TestProbeChapters:
    def test_parses_ffprobe_output(self):
        from chapters import _probe_chapters

        fake_output = '{"chapters": [{"id": 0, "start_time": "0.000", "end_time": "90.000", "tags": {"title": "OP"}}]}'
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = fake_output
            mock_run.return_value.returncode = 0
            result = _probe_chapters("/fake/video.mkv")
        assert len(result) == 1
        assert result[0]["title"] == "OP"
        assert result[0]["end_ms"] == 90000

    def test_returns_empty_list_when_no_chapters(self):
        from chapters import _probe_chapters

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = '{"chapters": []}'
            mock_run.return_value.returncode = 0
            result = _probe_chapters("/fake/video.mkv")
        assert result == []

    def test_returns_empty_on_ffprobe_failure(self):
        from chapters import _probe_chapters

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = ""
            mock_run.return_value.returncode = 1
            result = _probe_chapters("/fake/video.mkv")
        assert result == []


class TestGetChapters:
    def test_returns_cached_result(self, app_ctx, tmp_path):
        """get_chapters returns DB-cached chapters without calling ffprobe."""
        from chapters import get_chapters
        from extensions import db

        video = tmp_path / "ep.mkv"
        video.write_bytes(b"fake")
        chapters = [{"id": 0, "title": "OP", "start_ms": 0, "end_ms": 90000}]

        row = ChapterCache(
            file_path=str(video),
            mtime=video.stat().st_mtime,
            chapters_json=json.dumps(chapters),
            cached_at=datetime.utcnow().isoformat(),
        )
        db.session.add(row)
        db.session.commit()

        with patch("chapters._probe_chapters") as mock_probe:
            result = get_chapters(str(video))
        mock_probe.assert_not_called()
        assert result == chapters

    def test_probes_when_cache_miss(self, app_ctx, tmp_path):
        from chapters import get_chapters

        video = tmp_path / "ep2.mkv"
        video.write_bytes(b"fake")
        fake_chapters = [{"id": 0, "title": "A", "start_ms": 0, "end_ms": 5000}]

        with patch("chapters._probe_chapters", return_value=fake_chapters) as mock_probe:
            result = get_chapters(str(video))
        mock_probe.assert_called_once_with(str(video))
        assert result == fake_chapters

    def test_probes_when_mtime_changed(self, app_ctx, tmp_path):
        from chapters import get_chapters
        from extensions import db

        video = tmp_path / "ep3.mkv"
        video.write_bytes(b"fake")

        # Cache with stale mtime
        row = ChapterCache(
            file_path=str(video),
            mtime=0.0,  # wrong mtime
            chapters_json=json.dumps([]),
            cached_at=datetime.utcnow().isoformat(),
        )
        db.session.add(row)
        db.session.commit()

        fresh = [{"id": 0, "title": "Fresh", "start_ms": 0, "end_ms": 1000}]
        with patch("chapters._probe_chapters", return_value=fresh):
            result = get_chapters(str(video))
        assert result == fresh


class TestGetChaptersEndpoint:
    def test_get_chapters_returns_list(self, client, tmp_path, monkeypatch):
        video = tmp_path / "ep.mkv"
        video.write_bytes(b"fake")
        fake_chapters = [
            {"id": 0, "title": "Opening", "start_ms": 0, "end_ms": 90000},
            {"id": 1, "title": "Main", "start_ms": 90000, "end_ms": 1350000},
        ]
        monkeypatch.setattr("routes.tools.get_chapters", lambda p: fake_chapters)
        monkeypatch.setattr("routes.tools.is_safe_path", lambda p, b: True)

        r = client.get(f"/api/v1/tools/chapters?video_path={video}")
        assert r.status_code == 200
        data = r.get_json()
        assert "chapters" in data
        assert len(data["chapters"]) == 2
        assert data["chapters"][0]["title"] == "Opening"

    def test_get_chapters_missing_param(self, client):
        r = client.get("/api/v1/tools/chapters")
        assert r.status_code == 400

    def test_get_chapters_unsafe_path_rejected(self, client, monkeypatch):
        monkeypatch.setattr("routes.tools.is_safe_path", lambda p, b: False)
        r = client.get("/api/v1/tools/chapters?video_path=/etc/passwd")
        assert r.status_code == 403


class TestAdvancedSyncChapterRange:
    def test_offset_with_chapter_range_only_shifts_in_range(self, client, tmp_path, monkeypatch):
        sub = tmp_path / "ep.de.srt"
        sub.write_text(
            "1\n00:00:01,000 --> 00:00:02,000\nIn chapter\n\n"
            "2\n00:05:00,000 --> 00:05:01,000\nOutside chapter\n"
        )
        monkeypatch.setattr("routes.tools.is_safe_path", lambda p, b: True)

        r = client.post(
            "/api/v1/tools/advanced-sync",
            json={
                "file_path": str(sub),
                "operation": "offset",
                "offset_ms": 500,
                "chapter_range": {"start_ms": 0, "end_ms": 60000},
            },
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data["status"] == "synced"
        assert data["chapter_range"] == {"start_ms": 0, "end_ms": 60000}

        import pysubs2

        result = pysubs2.load(str(sub))
        assert result[0].start == 1500  # shifted: 1000 + 500
        assert result[1].start == 300000  # unchanged: 5*60*1000

    def test_offset_chapter_range_preview_returns_in_range_events(
        self, client, tmp_path, monkeypatch
    ):
        sub = tmp_path / "ep2.de.srt"
        sub.write_text(
            "1\n00:00:01,000 --> 00:00:02,000\nIn chapter\n\n"
            "2\n00:05:00,000 --> 00:05:01,000\nOutside\n"
        )
        monkeypatch.setattr("routes.tools.is_safe_path", lambda p, b: True)

        r = client.post(
            "/api/v1/tools/advanced-sync",
            json={
                "file_path": str(sub),
                "operation": "offset",
                "offset_ms": 200,
                "chapter_range": {"start_ms": 0, "end_ms": 60000},
                "preview": True,
            },
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data["status"] == "preview"
        texts = [e["text"] for e in data["events"]]
        assert any("In chapter" in t for t in texts)
        assert not any("Outside" in t for t in texts)
