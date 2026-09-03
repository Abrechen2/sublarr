"""Hostile paths must be refused, not crash the request.

Found on 2026-09-03 by probing the deployed 1.14.0-rc.5 from the server side.
The access check itself was sound — every path outside the library answered
403 — but two inputs reached code that was not expecting them and surfaced as
HTTP 500:

  file_path=/media           → ffmpeg "Is a directory" → RuntimeError
  file_path=/media%00/../..  → os.path.realpath → ValueError: embedded null

Neither is a way in. Both are an unhandled exception where a 4xx belongs, and
a guard that raises instead of returning False is a guard whose callers all
have to remember to catch it — so the null byte is fixed in `is_safe_path`
itself rather than at one call site.
"""

import os

from security_utils import is_safe_path


class TestIsSafePathSurvivesHostileInput:
    """POSIX-only in effect: Windows' realpath does not raise on a NUL, so
    these pass on a dev box either way. They fail without the fix on Linux —
    verified in the running container before the fix went in — which is the
    platform every install runs on and the one CI uses."""

    def test_embedded_null_returns_false_instead_of_raising(self, tmp_path):
        base = str(tmp_path)

        assert is_safe_path(f"{base}/x\x00/../../etc/passwd", base) is False

    def test_null_in_the_base_is_refused_too(self, tmp_path):
        assert is_safe_path(str(tmp_path / "f.srt"), f"{tmp_path}\x00") is False

    def test_a_legitimate_path_still_passes(self, tmp_path):
        inner = tmp_path / "serie"
        inner.mkdir()
        target = inner / "f.srt"
        target.write_text("x", encoding="utf-8")

        assert is_safe_path(str(target), str(tmp_path)) is True

    def test_an_escape_is_still_refused(self, tmp_path):
        assert is_safe_path(f"{tmp_path}/../../etc/passwd", str(tmp_path)) is False


class TestSubtitleEndpointRejectsNonFiles:
    """A directory is not a subtitle; the answer is 4xx, not a stack trace."""

    def _bypass_access_check(self, monkeypatch):
        """Let the request past the 403 so the case after it can be reached.

        The access check is not what is under test here — it already answers
        403 correctly for everything outside the library. What is under test
        is what happens to a path that IS allowed and still is not a file.
        """
        import routes.video as video_routes

        monkeypatch.setattr(video_routes, "is_safe_path", lambda *a, **k: True)
        return video_routes

    def test_a_directory_is_refused_and_never_reaches_the_converter(
        self, client, tmp_path, monkeypatch
    ):
        video_routes = self._bypass_access_check(monkeypatch)

        reached = []
        monkeypatch.setattr(
            video_routes,
            "convert_subtitle_to_webvtt",
            lambda *a, **k: reached.append(a) or "/tmp/never.vtt",
        )

        directory = tmp_path / "eine_serie"
        directory.mkdir()

        response = client.get(f"/api/v1/video/subtitles?file_path={directory}")

        assert response.status_code == 400, response.get_data(as_text=True)
        assert reached == [], "the converter was handed a directory"

    def test_a_real_file_still_gets_through_to_the_converter(self, client, tmp_path, monkeypatch):
        video_routes = self._bypass_access_check(monkeypatch)

        reached = []

        def _fake_convert(path, *a, **k):
            reached.append(path)
            out = tmp_path / "out.vtt"
            out.write_text("WEBVTT\n", encoding="utf-8")
            return str(out)

        monkeypatch.setattr(video_routes, "convert_subtitle_to_webvtt", _fake_convert)

        subtitle = tmp_path / "f.srt"
        subtitle.write_text("1\n00:00:01,000 --> 00:00:02,000\nx\n", encoding="utf-8")

        response = client.get(f"/api/v1/video/subtitles?file_path={subtitle}")

        assert response.status_code == 200, response.get_data(as_text=True)
        assert reached == [str(subtitle)]

    def test_a_null_byte_answers_4xx_rather_than_crashing(self, client):
        response = client.get("/api/v1/video/subtitles?file_path=/media\x00/../etc/passwd")

        assert response.status_code < 500, response.get_data(as_text=True)
