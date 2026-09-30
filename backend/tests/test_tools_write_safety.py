"""The subtitle tools must not lose work they did not write.

External review of 1.15.0-rc.17 (2026-09-30), each finding checked against
the code before it was fixed here:

- ``/tools/diff/apply`` wrote whatever the browser sent. A stale editor tab
  silently overwrote a newer save; the editor's own save already refuses that
  with 409 on a changed ``last_modified``.
- It backed up to ``episode.ass.bak`` while every other tool and
  ``GET /tools/backup`` use ``episode.bak.ass`` — the diff backup was invisible
  to the restore path.
- ``/tools/convert`` overwrote an existing ``*.converted.<fmt>`` without asking.
- ``/tools/waveform-extract`` left its temp ``.opus`` behind on every ffmpeg
  failure or timeout.
- The ASS/SRT sanitizers returned the ORIGINAL bytes when parsing failed —
  a file the sanitizer could not read reached the library unsanitized.
"""

import os
import subprocess
from unittest.mock import MagicMock, patch

import pytest

ASS = """\
[Script Info]
ScriptType: v4.00+

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,2,2,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,{line}
"""

ORIGINAL = ASS.replace("{line}", "Hello world")
EDITED = ASS.replace("{line}", "Hallo Welt")
SAVED_ELSEWHERE = ASS.replace("{line}", "Saved in another tab")


@pytest.fixture
def client(temp_db, tmp_path):
    os.environ["SUBLARR_MEDIA_PATH"] = str(tmp_path)
    from config import reload_settings

    reload_settings()
    from app import create_app

    app = create_app(testing=True)
    with app.test_client() as c, app.app_context():
        yield c
    del os.environ["SUBLARR_MEDIA_PATH"]
    reload_settings()


def _episode(tmp_path, content=ORIGINAL):
    path = tmp_path / "episode.ass"
    path.write_text(content, encoding="utf-8")
    return path


def _apply(client, path, last_modified):
    body = {"file_path": str(path), "original": ORIGINAL, "modified": EDITED}
    if last_modified is not None:
        body["last_modified"] = last_modified
    return client.post("/api/v1/tools/diff/apply", json=body)


class TestDiffApplyRefusesAStaleTab:
    def test_a_file_changed_since_loading_is_refused_and_left_alone(self, client, tmp_path):
        path = _episode(tmp_path)
        loaded_at = os.path.getmtime(path)
        path.write_text(SAVED_ELSEWHERE, encoding="utf-8")
        os.utime(path, (loaded_at + 60, loaded_at + 60))

        resp = _apply(client, path, loaded_at)

        assert resp.status_code == 409
        assert path.read_text(encoding="utf-8") == SAVED_ELSEWHERE
        assert not (tmp_path / "episode.bak.ass").exists(), "no backup for a refused write"

    def test_last_modified_is_required(self, client, tmp_path):
        path = _episode(tmp_path)

        resp = _apply(client, path, None)

        assert resp.status_code == 400
        assert path.read_text(encoding="utf-8") == ORIGINAL

    def test_an_unchanged_file_is_applied(self, client, tmp_path):
        path = _episode(tmp_path)

        resp = _apply(client, path, os.path.getmtime(path))

        assert resp.status_code == 200, resp.get_json()
        assert "Hallo Welt" in path.read_text(encoding="utf-8-sig")


class TestDiffApplyBackupIsTheSharedOne:
    def test_the_backup_is_where_every_other_tool_puts_it(self, client, tmp_path):
        path = _episode(tmp_path)

        resp = _apply(client, path, os.path.getmtime(path))

        assert resp.status_code == 200, resp.get_json()
        assert resp.get_json()["backup"] == str(tmp_path / "episode.bak.ass")
        assert not (tmp_path / "episode.ass.bak").exists()

    def test_the_backup_is_reachable_through_the_backup_endpoint(self, client, tmp_path):
        path = _episode(tmp_path)
        _apply(client, path, os.path.getmtime(path))

        resp = client.get("/api/v1/tools/backup", query_string={"file_path": str(path)})

        assert resp.status_code == 200, resp.get_json()
        assert "Hello world" in resp.get_json()["content"]


class TestConvertDoesNotOverwrite:
    def test_an_existing_conversion_is_refused_with_409(self, client, tmp_path):
        srt = tmp_path / "ep.de.srt"
        srt.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n\n", encoding="utf-8")
        target = tmp_path / "ep.de.converted.ass"
        target.write_text("hand-edited conversion", encoding="utf-8")

        resp = client.post(
            "/api/v1/tools/convert", json={"file_path": str(srt), "target_format": "ass"}
        )

        assert resp.status_code == 409
        assert "already exists" in resp.get_json()["error"]
        assert target.read_text(encoding="utf-8") == "hand-edited conversion"


class TestWaveformCleansUpAfterFailure:
    @pytest.fixture
    def temp_dir(self, tmp_path, monkeypatch):
        import tempfile

        scratch = tmp_path / "scratch"
        scratch.mkdir()
        monkeypatch.setattr(tempfile, "tempdir", str(scratch))
        return scratch

    def _extract(self, client, tmp_path, run):
        video = tmp_path / "ep.mkv"
        video.write_bytes(b"\x00")
        with patch("subprocess.run", run):
            return client.post("/api/v1/tools/waveform-extract", json={"video_path": str(video)})

    def test_a_failed_extraction_leaves_no_temp_file(self, client, tmp_path, temp_dir):
        failed = MagicMock(return_value=MagicMock(returncode=1, stderr=b"boom", stdout=b""))

        resp = self._extract(client, tmp_path, failed)

        assert resp.status_code == 500
        assert list(temp_dir.iterdir()) == []

    def test_a_timed_out_extraction_leaves_no_temp_file(self, client, tmp_path, temp_dir):
        timeout = MagicMock(side_effect=subprocess.TimeoutExpired(cmd="ffmpeg", timeout=120))

        resp = self._extract(client, tmp_path, timeout)

        assert resp.status_code == 500
        assert list(temp_dir.iterdir()) == []


class TestSanitizerFailsClosed:
    def _unparseable(self, monkeypatch):
        import pysubs2

        def boom(*_a, **_k):
            raise ValueError("unparseable")

        monkeypatch.setattr(pysubs2.SSAFile, "from_string", boom)

    def test_an_unparseable_ass_download_is_refused(self, monkeypatch):
        from subtitle_sanitizer import sanitize_subtitle

        self._unparseable(monkeypatch)

        with pytest.raises(ValueError):
            sanitize_subtitle(ORIGINAL.encode(), "ass")

    def test_the_download_path_rejects_it_instead_of_saving_it(self, monkeypatch):
        from subtitle_normalise import normalise_downloaded_content

        self._unparseable(monkeypatch)

        with pytest.raises(RuntimeError, match="security check"):
            normalise_downloaded_content(ORIGINAL.encode(), "ass")

    def test_an_unreadable_srt_is_refused(self, monkeypatch):
        import bs4

        from subtitle_sanitizer import sanitize_subtitle

        def boom(*_a, **_k):
            raise ValueError("unparseable")

        monkeypatch.setattr(bs4, "BeautifulSoup", boom)

        with pytest.raises(ValueError):
            sanitize_subtitle(b"1\n00:00:01,000 --> 00:00:02,000\nHi\n", "srt")

    def test_local_output_that_cannot_be_read_is_left_as_written(self, tmp_path, monkeypatch):
        """Translator output was serialised by pysubs2 a moment earlier; the
        helper reports the failure instead of raising into the flow."""
        from subtitle_sanitizer import sanitize_subtitle_file

        path = _episode(tmp_path)
        self._unparseable(monkeypatch)

        assert sanitize_subtitle_file(str(path)) is False
        assert path.read_text(encoding="utf-8") == ORIGINAL
