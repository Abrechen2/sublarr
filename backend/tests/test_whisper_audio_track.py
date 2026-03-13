"""Tests for audio_track_index propagation through WhisperQueue and transcribe route."""

import time
from unittest.mock import MagicMock, patch

import pytest


class TestWhisperJobDataclass:
    def test_has_audio_track_index_field(self):
        from whisper.queue import WhisperJob

        job = WhisperJob(job_id="abc", file_path="/fake.mkv")
        assert hasattr(job, "audio_track_index")
        assert job.audio_track_index is None

    def test_accepts_explicit_index(self):
        from whisper.queue import WhisperJob

        job = WhisperJob(job_id="abc", file_path="/fake.mkv", audio_track_index=2)
        assert job.audio_track_index == 2


class TestWhisperQueueAudioTrack:
    def test_explicit_index_bypasses_language_selection(self):
        """When audio_track_index is set, get_audio_track_by_index is called, not select_audio_track."""
        from whisper.queue import WhisperQueue

        fake_track = {
            "stream_index": 2,
            "language": "eng",
            "codec": "aac",
            "channels": 2,
            "title": "",
        }
        fake_result = MagicMock(
            success=True,
            srt_content="1\n00:00:01,000 --> 00:00:02,000\nHello",
            backend_name="faster_whisper",
            detected_language="en",
            language_probability=0.99,
            segment_count=1,
            duration_seconds=2.0,
        )
        manager = MagicMock()
        manager.transcribe.return_value = fake_result

        queue = WhisperQueue(max_concurrent=1)
        by_index = []
        by_lang = []

        def mock_by_index(fp, idx):
            by_index.append(idx)
            return fake_track

        def mock_by_lang(fp, preferred_language):
            by_lang.append(preferred_language)
            return fake_track

        with (
            patch("whisper.queue.get_audio_track_by_index", mock_by_index),
            patch("whisper.queue.select_audio_track", mock_by_lang),
            patch("whisper.queue.extract_audio_to_wav"),
            patch("whisper.queue.create_whisper_job"),
            patch("whisper.queue.update_whisper_job"),
            patch("tempfile.mkstemp", return_value=(0, "/tmp/fake.wav")),
            patch("os.close"),
            patch("os.path.exists", return_value=True),
            patch("os.remove"),
        ):
            queue.submit(
                job_id="t1",
                file_path="/fake.mkv",
                language="ja",
                source_language="ja",
                audio_track_index=2,
                whisper_manager=manager,
            )
            time.sleep(0.5)

        assert by_index == [2], "get_audio_track_by_index must be called with explicit index"
        assert by_lang == [], "select_audio_track must NOT be called when explicit index is set"

    def test_none_index_uses_language_selection(self):
        """When audio_track_index is None, select_audio_track is called normally."""
        from whisper.queue import WhisperQueue

        fake_track = {
            "stream_index": 0,
            "language": "jpn",
            "codec": "aac",
            "channels": 2,
            "title": "",
        }
        fake_result = MagicMock(
            success=True,
            srt_content="1\n00:00:01,000 --> 00:00:02,000\nHello",
            backend_name="faster_whisper",
            detected_language="ja",
            language_probability=0.99,
            segment_count=1,
            duration_seconds=2.0,
        )
        manager = MagicMock()
        manager.transcribe.return_value = fake_result

        queue = WhisperQueue(max_concurrent=1)
        by_index = []
        by_lang = []

        def mock_by_index(fp, idx):
            by_index.append(idx)
            return fake_track

        def mock_by_lang(fp, preferred_language):
            by_lang.append(preferred_language)
            return fake_track

        with (
            patch("whisper.queue.get_audio_track_by_index", mock_by_index),
            patch("whisper.queue.select_audio_track", mock_by_lang),
            patch("whisper.queue.extract_audio_to_wav"),
            patch("whisper.queue.create_whisper_job"),
            patch("whisper.queue.update_whisper_job"),
            patch("tempfile.mkstemp", return_value=(0, "/tmp/fake.wav")),
            patch("os.close"),
            patch("os.path.exists", return_value=True),
            patch("os.remove"),
        ):
            queue.submit(
                job_id="t2",
                file_path="/fake.mkv",
                language="ja",
                source_language="ja",
                audio_track_index=None,
                whisper_manager=manager,
            )
            time.sleep(0.5)

        assert by_lang == ["ja"], "select_audio_track must be called when index is None"
        assert by_index == [], "get_audio_track_by_index must NOT be called when index is None"


class TestWhisperTranscribeRoute:
    @pytest.fixture
    def client(self, temp_db):
        from app import create_app

        app = create_app(testing=True)
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c

    def test_accepts_audio_track_index(self, client, monkeypatch):
        captured = {}

        class FakeQueue:
            def submit(self, **kwargs):
                captured.update(kwargs)
                return "j1"

        monkeypatch.setattr("routes.whisper._queue", FakeQueue())
        monkeypatch.setattr("routes.whisper.is_safe_path", lambda *a: True)
        monkeypatch.setattr("routes.whisper.os.path.exists", lambda p: True)
        r = client.post(
            "/api/v1/whisper/transcribe",
            json={"file_path": "/media/ep1.mkv", "audio_track_index": 2},
            content_type="application/json",
        )
        assert r.status_code == 202
        assert captured.get("audio_track_index") == 2

    def test_missing_index_defaults_to_none(self, client, monkeypatch):
        captured = {}

        class FakeQueue:
            def submit(self, **kwargs):
                captured.update(kwargs)
                return "j2"

        monkeypatch.setattr("routes.whisper._queue", FakeQueue())
        monkeypatch.setattr("routes.whisper.is_safe_path", lambda *a: True)
        monkeypatch.setattr("routes.whisper.os.path.exists", lambda p: True)
        r = client.post(
            "/api/v1/whisper/transcribe",
            json={"file_path": "/media/ep1.mkv"},
            content_type="application/json",
        )
        assert r.status_code == 202
        assert captured.get("audio_track_index") is None

    def test_rejects_negative_index(self, client, monkeypatch):
        monkeypatch.setattr("routes.whisper.is_safe_path", lambda *a: True)
        monkeypatch.setattr("routes.whisper.os.path.exists", lambda p: True)
        r = client.post(
            "/api/v1/whisper/transcribe",
            json={"file_path": "/media/ep1.mkv", "audio_track_index": -1},
            content_type="application/json",
        )
        assert r.status_code == 400

    def test_rejects_string_index(self, client, monkeypatch):
        monkeypatch.setattr("routes.whisper.is_safe_path", lambda *a: True)
        monkeypatch.setattr("routes.whisper.os.path.exists", lambda p: True)
        r = client.post(
            "/api/v1/whisper/transcribe",
            json={"file_path": "/media/ep1.mkv", "audio_track_index": "first"},
            content_type="application/json",
        )
        assert r.status_code == 400
