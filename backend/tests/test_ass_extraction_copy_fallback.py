"""ASS/SSA embedded extraction prefers stream-copy and falls back safely."""

import os
from unittest.mock import MagicMock

import pytest


@pytest.mark.parametrize("extension", ["ass", "ssa"])
def test_ass_and_ssa_extraction_uses_stream_copy_first(tmp_path, app_ctx, monkeypatch, extension):
    from ass_probe import extract_subtitle_stream

    output = tmp_path / f"episode.en.{extension}"
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        with open(command[-1], "wb") as extracted:
            extracted.write(b"[Script Info]\nTitle: original\n")
        return MagicMock(returncode=0, stderr="")

    monkeypatch.setattr("ass_probe.subprocess.run", fake_run)
    monkeypatch.setattr(
        "ass_probe.get_settings",
        lambda: MagicMock(ffmpeg_timeout=5, embedded_extract_ass_stream_copy=True),
    )

    extract_subtitle_stream(
        str(tmp_path / "episode.mkv"),
        {"sub_index": 0, "format": extension},
        str(output),
    )

    assert len(calls) == 1
    assert calls[0][calls[0].index("-c:s") + 1] == "copy"
    assert output.read_bytes() == b"[Script Info]\nTitle: original\n"


@pytest.mark.parametrize("extension", ["ass", "ssa"])
def test_ass_and_ssa_copy_failure_retries_with_existing_encoder(
    tmp_path, app_ctx, monkeypatch, extension
):
    from ass_probe import extract_subtitle_stream

    output = tmp_path / f"episode.en.{extension}"
    calls = []

    def fake_run(command, **kwargs):
        encoder = command[command.index("-c:s") + 1]
        calls.append(encoder)
        temp_output = command[-1]
        if encoder == "copy":
            with open(temp_output, "wb") as partial:
                partial.write(b"partial copy")
            return MagicMock(returncode=1, stderr="copy not supported")

        # The failed copy's partial output must be gone before the fallback.
        assert not os.path.exists(temp_output)
        with open(temp_output, "wb") as extracted:
            extracted.write(b"[Script Info]\nTitle: encoded fallback\n")
        return MagicMock(returncode=0, stderr="")

    monkeypatch.setattr("ass_probe.subprocess.run", fake_run)
    monkeypatch.setattr(
        "ass_probe.get_settings",
        lambda: MagicMock(ffmpeg_timeout=5, embedded_extract_ass_stream_copy=True),
    )

    extract_subtitle_stream(
        str(tmp_path / "episode.mkv"),
        {"sub_index": 0, "format": extension},
        str(output),
    )

    assert calls == ["copy", "ass"]
    assert output.read_bytes() == b"[Script Info]\nTitle: encoded fallback\n"


@pytest.mark.parametrize(
    ("extension", "expected_encoder"),
    [("srt", "srt"), ("vtt", "webvtt")],
)
def test_non_ass_formats_keep_their_existing_encoder(
    tmp_path, app_ctx, monkeypatch, extension, expected_encoder
):
    from ass_probe import extract_subtitle_stream

    output = tmp_path / f"episode.en.{extension}"
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        with open(command[-1], "wb") as extracted:
            extracted.write(b"subtitle output")
        return MagicMock(returncode=0, stderr="")

    monkeypatch.setattr("ass_probe.subprocess.run", fake_run)
    monkeypatch.setattr(
        "ass_probe.get_settings",
        lambda: MagicMock(ffmpeg_timeout=5, embedded_extract_ass_stream_copy=True),
    )

    extract_subtitle_stream(
        str(tmp_path / "episode.mkv"),
        {"sub_index": 0, "format": extension},
        str(output),
    )

    assert len(calls) == 1
    assert calls[0][calls[0].index("-c:s") + 1] == expected_encoder
    assert output.read_bytes() == b"subtitle output"


def test_a_copy_that_times_out_is_not_retried(tmp_path, app_ctx, monkeypatch):
    import subprocess

    from ass_probe import extract_subtitle_stream

    calls = []

    def fake_run(command, **kwargs):
        calls.append(command[command.index("-c:s") + 1])
        raise subprocess.TimeoutExpired(command, kwargs.get("timeout"))

    monkeypatch.setattr("ass_probe.subprocess.run", fake_run)
    monkeypatch.setattr(
        "ass_probe.get_settings",
        lambda: MagicMock(ffmpeg_timeout=5, embedded_extract_ass_stream_copy=True),
    )

    with pytest.raises(subprocess.TimeoutExpired):
        extract_subtitle_stream(
            str(tmp_path / "episode.mkv"),
            {"sub_index": 0, "format": "ass"},
            str(tmp_path / "episode.en.ass"),
        )
    assert calls == ["copy"]


def test_stream_copy_is_opt_in(tmp_path, app_ctx, monkeypatch):
    from ass_probe import extract_subtitle_stream

    encoders = []

    def fake_run(command, **kwargs):
        encoders.append(command[command.index("-c:s") + 1])
        with open(command[-1], "wb") as extracted:
            extracted.write(b"[Script Info]\n")
        return MagicMock(returncode=0, stderr="")

    monkeypatch.setattr("ass_probe.subprocess.run", fake_run)
    monkeypatch.setattr(
        "ass_probe.get_settings",
        lambda: MagicMock(ffmpeg_timeout=5, embedded_extract_ass_stream_copy=False),
    )
    extract_subtitle_stream(
        str(tmp_path / "episode.mkv"), {"sub_index": 0}, str(tmp_path / "episode.en.ass")
    )
    assert encoders == ["ass"]
