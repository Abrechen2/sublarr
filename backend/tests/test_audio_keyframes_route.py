"""Tests for keyframes + scene-detect service + their routes.

Plan B8 Task 2 — keyframes (ffprobe) and scene boundaries (PySceneDetect)
feed the WaveformEditor's snap targets and scene markers.
"""

from __future__ import annotations

from unittest.mock import patch

# ─── list_keyframes (ffprobe-based) ────────────────────────────────────────


FAKE_FFPROBE_KEYFRAMES_OUTPUT = (
    "0.000000,K_\n"
    "0.083333,__\n"
    "1.250000,K_\n"
    "2.500000,__\n"
    "3.750000,K_\n"
    ",\n"  # malformed line, must be skipped
    "5.000000,K_\n"
)


class TestListKeyframes:
    def test_extracts_only_keyframe_timestamps(self):
        from services.audio_visualizer import list_keyframes

        with patch(
            "services.audio_visualizer._run_ffprobe_keyframes",
            return_value=FAKE_FFPROBE_KEYFRAMES_OUTPUT,
        ):
            kf = list_keyframes("/media/ep.mkv")

        assert kf == [0.0, 1.25, 3.75, 5.0]

    def test_handles_empty_ffprobe_output(self):
        from services.audio_visualizer import list_keyframes

        with patch("services.audio_visualizer._run_ffprobe_keyframes", return_value=""):
            assert list_keyframes("/media/ep.mkv") == []

    def test_propagates_ffprobe_error_as_runtime(self):
        from services.audio_visualizer import list_keyframes

        with patch(
            "services.audio_visualizer._run_ffprobe_keyframes",
            side_effect=RuntimeError("ffprobe missing"),
        ):
            try:
                list_keyframes("/media/ep.mkv")
            except RuntimeError as exc:
                assert "ffprobe" in str(exc)
            else:
                raise AssertionError("expected RuntimeError")


# ─── detect_scenes (PySceneDetect lazy) ────────────────────────────────────


class TestDetectScenes:
    def test_returns_empty_when_pyscenedetect_unavailable(self):
        """Lazy import: ImportError -> empty list, never raises."""
        from services import scene_detector

        # Force the lazy import to fail by patching the attempt
        with patch.object(scene_detector, "_import_scenedetect", side_effect=ImportError()):
            assert scene_detector.detect_scenes("/media/ep.mkv") == []

    def test_returns_seconds_list_when_available(self):
        from services import scene_detector

        # Mock the result of scenedetect.detect(); each scene is a tuple
        # (start_timecode, end_timecode) where each timecode has .get_seconds()
        class FakeTimecode:
            def __init__(self, seconds: float):
                self._s = seconds

            def get_seconds(self) -> float:
                return self._s

        fake_scenes = [
            (FakeTimecode(0.0), FakeTimecode(12.5)),
            (FakeTimecode(12.5), FakeTimecode(28.3)),
            (FakeTimecode(28.3), FakeTimecode(60.0)),
        ]

        class FakeContentDetector:
            def __init__(self, threshold: float = 27.0):
                self.threshold = threshold

        fake_detect = lambda *a, **kw: fake_scenes  # noqa: E731

        with patch.object(
            scene_detector,
            "_import_scenedetect",
            return_value=(fake_detect, FakeContentDetector),
        ):
            result = scene_detector.detect_scenes("/media/ep.mkv")

        # Boundaries of the *next* scenes — first one (0.0) is dropped because
        # it's the start of the file, not a meaningful cut.
        assert result == [12.5, 28.3]


# ─── Routes ────────────────────────────────────────────────────────────────


class TestKeyframesRoute:
    def test_requires_file_path(self, client):
        resp = client.get("/api/v1/audio/keyframes")
        assert resp.status_code == 400

    def test_rejects_path_traversal(self, client):
        resp = client.get("/api/v1/audio/keyframes?file_path=/etc/passwd")
        assert resp.status_code == 403

    def test_returns_keyframes_for_existing_file(self, client, tmp_path):
        video = tmp_path / "ep.mkv"
        video.write_bytes(b"\x00")
        with patch(
            "services.audio_visualizer._run_ffprobe_keyframes",
            return_value=FAKE_FFPROBE_KEYFRAMES_OUTPUT,
        ):
            resp = client.get(f"/api/v1/audio/keyframes?file_path={video}")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["keyframes"] == [0.0, 1.25, 3.75, 5.0]


class TestScenesRoute:
    def test_requires_file_path(self, client):
        resp = client.get("/api/v1/audio/scenes")
        assert resp.status_code == 400

    def test_returns_empty_when_pyscenedetect_unavailable(self, client, tmp_path):
        video = tmp_path / "ep.mkv"
        video.write_bytes(b"\x00")
        from services import scene_detector

        with patch.object(scene_detector, "_import_scenedetect", side_effect=ImportError()):
            resp = client.get(f"/api/v1/audio/scenes?file_path={video}")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body == {"scenes": [], "available": False}


class TestSpeechRoute:
    def test_requires_file_path(self, client):
        resp = client.get("/api/v1/audio/speech")
        assert resp.status_code == 400

    def test_rejects_path_traversal(self, client):
        resp = client.get("/api/v1/audio/speech?file_path=/etc/passwd")
        assert resp.status_code == 403

    def test_returns_empty_when_webrtcvad_unavailable(self, client, tmp_path):
        video = tmp_path / "ep.mkv"
        video.write_bytes(b"\x00")
        from services import speech_detector

        with patch.object(speech_detector, "_import_webrtcvad", side_effect=ImportError()):
            resp = client.get(f"/api/v1/audio/speech?file_path={video}")
        assert resp.status_code == 200
        assert resp.get_json() == {"segments": [], "available": False}

    def test_returns_segments_when_available(self, client, tmp_path):
        video = tmp_path / "ep.mkv"
        video.write_bytes(b"\x00")
        with patch(
            "routes.audio.detect_speech_segments",
            return_value=[{"start": 1.0, "end": 2.5}],
        ):
            resp = client.get(f"/api/v1/audio/speech?file_path={video}")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["segments"] == [{"start": 1.0, "end": 2.5}]
        assert body["available"] is True
