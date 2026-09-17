"""Regression: files written into the media library through a same-directory temp.

Four writers created their work file with a bare ``tempfile.mkstemp(dir=...)``
next to the episode and ``os.replace``d it into place:

* ``ass_probe.extract_subtitle_stream`` (every embedded-track extraction)
* the subtitle-repair pass after an embedded extraction
* ``POST /tools/diff/apply``
* the ``remux_track`` subtitle-health fixer (rewrites the video itself)

``mkstemp`` creates its file 0600, so the result landed ``-rw-------``. On a
library with POSIX ACLs that is worse than it looks: chmod 600 also sets the
ACL mask to ``---``, which cancels every named ACL entry. Prod had 1 417
sidecars the media server (Emby, a different uid) could not open.

The same writers used the default ``tmp`` prefix, so a process killed mid-write
(container stop, host shutdown) left ``tmpXXXXXXXX.srt`` in the library for
good — prod had seven, all zero bytes, all dated to an outage.
"""

from __future__ import annotations

import os
import stat
import sys
import time
from unittest.mock import MagicMock, patch

import pytest

posix_only = pytest.mark.skipif(
    sys.platform == "win32", reason="POSIX file-mode semantics do not apply on Windows"
)

SRT = b"1\n00:00:01,000 --> 00:00:02,000\nhello\n"


def _mode(path) -> int:
    return stat.S_IMODE(os.stat(path).st_mode)


def _age(path, seconds: float) -> None:
    past = time.time() - seconds
    os.utime(path, (past, past))


def _fake_ffmpeg(captured: dict):
    def fake_run(cmd, **kwargs):
        captured["tmp_out"] = cmd[-1]
        with open(cmd[-1], "wb") as fh:
            fh.write(SRT)
        return MagicMock(returncode=0, stderr="")

    return fake_run


class TestExtractSubtitleStream:
    @posix_only
    def test_extracted_sidecar_is_world_readable(self, tmp_path, app_ctx):
        from ass_probe import extract_subtitle_stream

        mkv = tmp_path / "show.mkv"
        mkv.write_bytes(b"\x1a\x45\xdf\xa3")
        out = tmp_path / "show.de.srt"
        old = os.umask(0o022)
        try:
            with patch("ass_probe.subprocess.run", side_effect=_fake_ffmpeg({})):
                extract_subtitle_stream(str(mkv), {"sub_index": 0, "format": "srt"}, str(out))
        finally:
            os.umask(old)
        assert _mode(out) == 0o644, f"expected 0644, got {oct(_mode(out))}"

    def test_temp_file_carries_the_sublarr_prefix(self, tmp_path, app_ctx):
        from ass_probe import extract_subtitle_stream

        mkv = tmp_path / "show.mkv"
        mkv.write_bytes(b"\x1a\x45\xdf\xa3")
        captured: dict = {}
        with patch("ass_probe.subprocess.run", side_effect=_fake_ffmpeg(captured)):
            extract_subtitle_stream(
                str(mkv), {"sub_index": 0, "format": "srt"}, str(tmp_path / "show.de.srt")
            )
        assert os.path.basename(captured["tmp_out"]).startswith(".sublarr-")

    def test_stale_orphaned_temps_are_swept_before_extracting(self, tmp_path, app_ctx):
        from ass_probe import extract_subtitle_stream

        mkv = tmp_path / "show.mkv"
        mkv.write_bytes(b"\x1a\x45\xdf\xa3")

        stale_ours = tmp_path / ".sublarr-k2j4h5g6.srt"
        stale_ours.write_bytes(b"partial")
        _age(stale_ours, 7 * 3600)
        stale_legacy = tmp_path / "tmp6fyuxlvz.srt"
        stale_legacy.write_bytes(b"")
        _age(stale_legacy, 7 * 3600)

        fresh_ours = tmp_path / ".sublarr-inflight.srt"  # another worker, right now
        fresh_ours.write_bytes(b"partial")
        legacy_with_content = tmp_path / "tmpabcdefgh.srt"  # not provably ours
        legacy_with_content.write_bytes(SRT)
        _age(legacy_with_content, 7 * 3600)
        user_file = tmp_path / "tmp.srt"
        user_file.write_bytes(b"")
        _age(user_file, 7 * 3600)

        with patch("ass_probe.subprocess.run", side_effect=_fake_ffmpeg({})):
            extract_subtitle_stream(
                str(mkv), {"sub_index": 0, "format": "srt"}, str(tmp_path / "show.de.srt")
            )

        assert not stale_ours.exists()
        assert not stale_legacy.exists()
        assert fresh_ours.exists()
        assert legacy_with_content.exists()
        assert user_file.exists()


class TestSweepOrphanedTemps:
    def test_never_touches_directories_or_video_temps_of_a_running_remux(self, tmp_path):
        from utils.atomic_write import sweep_orphaned_temps

        trash_dir = tmp_path / ".sublarr"
        trash_dir.mkdir()
        _age(trash_dir, 7 * 3600)
        running_remux = tmp_path / ".sublarr-remux-abc.mkv"
        running_remux.write_bytes(b"x")

        assert sweep_orphaned_temps(str(tmp_path)) == 0
        assert trash_dir.is_dir()
        assert running_remux.exists()

    def test_missing_directory_is_not_an_error(self, tmp_path):
        from utils.atomic_write import sweep_orphaned_temps

        assert sweep_orphaned_temps(str(tmp_path / "gone")) == 0


@posix_only
def test_repair_after_extract_keeps_sidecar_readable(tmp_path):
    from services.embedded_extractor import _repair_sidecar_file

    sub = tmp_path / "show.de.srt"
    sub.write_bytes(b"\xef\xbb\xbf" + SRT.replace(b"\n", b"\r\n"))
    os.chmod(sub, 0o644)
    old = os.umask(0o022)
    try:
        changed = _repair_sidecar_file(str(sub))
    finally:
        os.umask(old)
    assert changed is True, "fixture must actually need a repair"
    assert _mode(sub) == 0o644, f"expected 0644, got {oct(_mode(sub))}"


@posix_only
def test_diff_apply_keeps_sidecar_readable(client, tmp_path):
    from tests.test_diff_endpoint import MOD_ASS, ORIG_ASS

    sub = tmp_path / "test.de.ass"
    sub.write_text(ORIG_ASS, encoding="utf-8")
    os.chmod(sub, 0o644)
    old = os.umask(0o022)
    try:
        resp = client.post(
            "/api/v1/tools/diff/apply",
            json={
                "file_path": str(sub),
                "original": ORIG_ASS,
                "modified": MOD_ASS,
                "rejected_indices": [],
            },
        )
    finally:
        os.umask(old)
    assert resp.status_code == 200, resp.get_json()
    assert _mode(sub) == 0o644, f"expected 0644, got {oct(_mode(sub))}"


@posix_only
def test_remux_track_keeps_the_videos_mode(tmp_path, app_ctx):
    from services.subtitle_health.fixers import remux_track

    video = tmp_path / "x.mkv"
    video.write_bytes(b"original")
    os.chmod(video, 0o664)
    fake_json = {
        "tracks": [
            {"id": 0, "type": "video", "codec": "AVC/H.264"},
            {"id": 1, "type": "subtitles", "codec": "SubRip/SRT", "properties": {}},
        ]
    }

    def fake_mkvmerge(src, out, *args, **kwargs):
        with open(out, "wb") as fh:
            fh.write(b"remuxed")
        return True

    prefix = "services.subtitle_health.fixers.remux_track"
    with (
        patch(f"{prefix}._mkvmerge_identify", return_value=fake_json),
        patch(f"{prefix}.extract_track_raw", return_value=SRT),
        patch(f"{prefix}._run_mkvmerge_replace", side_effect=fake_mkvmerge),
        patch(f"{prefix}._make_backup", return_value="/trash/x.mkv"),
        patch(f"{prefix}._validate_remux", return_value=None),
    ):
        res = remux_track.apply(str(video), sub_index=0, codec="subrip", lang="ger")

    assert res["changed"] is True
    assert video.read_bytes() == b"remuxed"
    assert _mode(video) == 0o664, f"expected 0664, got {oct(_mode(video))}"


class TestSweepIsCheap:
    """Cold review (Codex, 2026-09-17): the sweep ran on every atomic write and
    stat-ed every entry of the directory first."""

    def test_the_sweep_is_throttled_per_directory(self, tmp_path, monkeypatch):
        import utils.atomic_write as aw

        clock = {"now": 10_000.0}
        monkeypatch.setattr(aw, "_now", lambda: clock["now"])
        monkeypatch.setattr(aw, "_swept_at", {})

        first = tmp_path / ".sublarr-one.srt"
        first.write_bytes(b"x")
        _age(first, 7 * 3600)
        assert aw.sweep_orphaned_temps(str(tmp_path)) == 1

        second = tmp_path / ".sublarr-two.srt"
        second.write_bytes(b"x")
        _age(second, 7 * 3600)
        assert aw.sweep_orphaned_temps(str(tmp_path)) == 0, "a second sweep right after is skipped"
        assert second.exists()

        clock["now"] += aw._SWEEP_INTERVAL_S + 1
        assert aw.sweep_orphaned_temps(str(tmp_path)) == 1
        assert not second.exists()

    def test_only_candidate_names_are_inspected(self, tmp_path, monkeypatch):
        import utils.atomic_write as aw

        monkeypatch.setattr(aw, "_swept_at", {})
        for i in range(5):
            (tmp_path / f"Episode {i}.mkv").write_bytes(b"v")
        stale = tmp_path / ".sublarr-x.srt"
        stale.write_bytes(b"x")
        _age(stale, 7 * 3600)

        stat_calls = []
        real_stat = os.stat

        def counting_stat(path, *args, **kwargs):
            stat_calls.append(str(path))
            return real_stat(path, *args, **kwargs)

        monkeypatch.setattr(aw.os, "stat", counting_stat)
        assert aw.sweep_orphaned_temps(str(tmp_path)) == 1
        assert not [c for c in stat_calls if c.endswith(".mkv")], stat_calls
