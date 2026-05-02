"""Tests for the optional `track_index` argument on /tools/waveform-extract.

Plan B8 Task 6 — when the user picks a non-default audio track in the
waveform editor's track-picker, the frontend re-extracts that track's
audio for the waveform. We exercise the route at the boundary level:

  1. Cache key includes track_index → different tracks produce
     independent cached audio files.
  2. ffmpeg is invoked with `-map 0:a:<idx>` selecting the requested
     audio stream (and only the audio stream).
  3. Negative or non-integer track_index values are rejected (400).
"""

from __future__ import annotations

import os
from unittest.mock import patch, MagicMock


def _make_video(tmp_path):
    """Create a placeholder video file under the media root."""
    video = tmp_path / "ep.mkv"
    video.write_bytes(b"\x00")
    return video


def _ok_subprocess() -> MagicMock:
    """A subprocess.run mock that always reports success and writes the temp file.

    The route also calls ffprobe (via `_get_waveform_duration`); for ffprobe
    invocations we return a parseable JSON stub instead of writing the output
    file so the duration helper has something to read.
    """

    def _fake_run(cmd, **kwargs):
        proc = MagicMock()
        proc.returncode = 0
        proc.stderr = b""
        if cmd and cmd[0] == "ffprobe":
            proc.stdout = b'{"format": {"duration": "12.5"}}'
        else:
            proc.stdout = b""
            # ffmpeg writes to the last positional arg in our command shape.
            out_path = cmd[-1]
            with open(out_path, "wb") as f:
                f.write(b"\x00")
        return proc

    return MagicMock(side_effect=_fake_run)


def _ffmpeg_calls(run_mock: MagicMock) -> list:
    """Return only the ffmpeg invocations from the captured call list."""
    return [c for c in run_mock.call_args_list if c.args and c.args[0] and c.args[0][0] == "ffmpeg"]


class TestWaveformExtractTrackIndex:
    def test_passes_audio_map_to_ffmpeg_when_track_index_set(self, client, tmp_path):
        video = _make_video(tmp_path)
        run_mock = _ok_subprocess()

        with patch("subprocess.run", run_mock):
            resp = client.post(
                "/api/v1/tools/waveform-extract",
                json={"video_path": str(video), "track_index": 2},
            )

        assert resp.status_code == 200, resp.get_json()
        ffmpeg = _ffmpeg_calls(run_mock)
        assert len(ffmpeg) == 1
        cmd = ffmpeg[0].args[0]
        # `-map 0:a:<idx>` selects the Nth audio stream by audio-index.
        assert "-map" in cmd
        map_idx = cmd.index("-map")
        assert cmd[map_idx + 1] == "0:a:2"

    def test_default_extract_has_no_explicit_map(self, client, tmp_path):
        """Without track_index, ffmpeg's automatic audio-stream pick stands."""
        video = _make_video(tmp_path)
        run_mock = _ok_subprocess()

        with patch("subprocess.run", run_mock):
            resp = client.post(
                "/api/v1/tools/waveform-extract",
                json={"video_path": str(video)},
            )

        assert resp.status_code == 200
        ffmpeg = _ffmpeg_calls(run_mock)
        assert len(ffmpeg) == 1
        cmd = ffmpeg[0].args[0]
        # No explicit `-map` => let ffmpeg pick the default audio track.
        assert "-map" not in cmd

    def test_different_track_indices_produce_independent_cache_entries(
        self, client, tmp_path
    ):
        video = _make_video(tmp_path)
        run_mock = _ok_subprocess()

        with patch("subprocess.run", run_mock):
            resp1 = client.post(
                "/api/v1/tools/waveform-extract",
                json={"video_path": str(video), "track_index": 0},
            )
            resp2 = client.post(
                "/api/v1/tools/waveform-extract",
                json={"video_path": str(video), "track_index": 1},
            )

        assert resp1.status_code == 200
        assert resp2.status_code == 200
        url1 = resp1.get_json()["audio_url"]
        url2 = resp2.get_json()["audio_url"]
        # Distinct cache keys must produce distinct audio files.
        assert url1 != url2
        # Both ffmpeg invocations actually ran (cache misses); ffprobe calls
        # for duration aren't counted here.
        assert len(_ffmpeg_calls(run_mock)) == 2

    def test_same_track_index_hits_cache_on_second_call(self, client, tmp_path):
        video = _make_video(tmp_path)
        run_mock = _ok_subprocess()

        with patch("subprocess.run", run_mock):
            client.post(
                "/api/v1/tools/waveform-extract",
                json={"video_path": str(video), "track_index": 1},
            )
            client.post(
                "/api/v1/tools/waveform-extract",
                json={"video_path": str(video), "track_index": 1},
            )

        # Second call must hit the cache (only one ffmpeg extraction ran).
        assert len(_ffmpeg_calls(run_mock)) == 1

    def test_rejects_non_integer_track_index(self, client, tmp_path):
        video = _make_video(tmp_path)

        resp = client.post(
            "/api/v1/tools/waveform-extract",
            json={"video_path": str(video), "track_index": "abc"},
        )

        assert resp.status_code == 400
        assert "track_index" in resp.get_json()["error"]

    def test_rejects_negative_track_index(self, client, tmp_path):
        video = _make_video(tmp_path)

        resp = client.post(
            "/api/v1/tools/waveform-extract",
            json={"video_path": str(video), "track_index": -1},
        )

        assert resp.status_code == 400
        assert "track_index" in resp.get_json()["error"]
