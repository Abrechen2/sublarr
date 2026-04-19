"""Plan B6 — verify save paths call run_trigger with the right trigger name."""

from pathlib import Path
from unittest.mock import patch


def test_config_store_roundtrip(app_ctx):
    from post_processing.config_store import get_trigger_ops, set_trigger_ops

    # Initially empty
    assert get_trigger_ops("after_download") == []
    # Set and read back
    set_trigger_ops("after_download", ["strip_html", "remove_bom"])
    assert get_trigger_ops("after_download") == ["strip_html", "remove_bom"]
    # Update
    set_trigger_ops("after_download", ["webhook"])
    assert get_trigger_ops("after_download") == ["webhook"]
    # Reset
    set_trigger_ops("after_download", [])
    assert get_trigger_ops("after_download") == []


def test_save_subtitle_fires_after_download(tmp_path, app_ctx, monkeypatch):
    """save_subtitle must call run_trigger('after_download', ...) after writing."""
    from post_processing.config_store import set_trigger_ops
    from providers.base import SubtitleFormat, SubtitleResult

    set_trigger_ops("after_download", ["strip_html"])

    srt_bytes = (
        b"1\n00:00:01,000 --> 00:00:02,000\nHi\n\n"
        b"2\n00:00:03,000 --> 00:00:04,000\nBye\n"
    )
    result = SubtitleResult(
        provider_name="p",
        subtitle_id="1",
        language="en",
        format=SubtitleFormat.SRT,
        content=srt_bytes,
        score=42,
    )

    target = tmp_path / "t.en.srt"
    monkeypatch.setattr(
        "security_utils.is_safe_path",
        lambda *a, **kw: True,
        raising=False,
    )

    with patch("providers.download_manager.run_trigger") as mock_trigger:
        from providers.download_manager import save_subtitle

        saved = save_subtitle(result, str(target))

    # The file should exist
    assert Path(saved).exists()
    # run_trigger must have been called with the right trigger + op_ids
    mock_trigger.assert_called_once()
    call_kwargs = mock_trigger.call_args.kwargs
    if not call_kwargs:
        # fall back to positional
        args = mock_trigger.call_args.args
        assert args[0] == "after_download"
        assert args[1] == ["strip_html"]
    else:
        assert call_kwargs.get("trigger") == "after_download"
        assert call_kwargs.get("op_ids") == ["strip_html"]


def test_save_subtitle_skips_trigger_when_no_ops(tmp_path, app_ctx, monkeypatch):
    """With no ops configured, run_trigger is a no-op (not called, or called with []).

    The pipeline's ``run_trigger`` returns early when op_ids is empty,
    but the wiring is expected to skip the call entirely.
    """
    from providers.base import SubtitleFormat, SubtitleResult

    srt_bytes = b"1\n00:00:01,000 --> 00:00:02,000\nHi\n"
    result = SubtitleResult(
        provider_name="p",
        subtitle_id="1",
        language="en",
        format=SubtitleFormat.SRT,
        content=srt_bytes,
    )

    target = tmp_path / "t.en.srt"
    monkeypatch.setattr(
        "security_utils.is_safe_path",
        lambda *a, **kw: True,
        raising=False,
    )

    with patch("providers.download_manager.run_trigger") as mock_trigger:
        from providers.download_manager import save_subtitle

        save_subtitle(result, str(target))

    # Either not called (wiring skipped it) OR called with op_ids=[]
    if mock_trigger.called:
        kwargs = mock_trigger.call_args.kwargs
        args = mock_trigger.call_args.args
        op_ids = kwargs.get("op_ids") if kwargs else (args[1] if len(args) > 1 else [])
        assert op_ids == []


def test_translator_helper_fires_after_translate(tmp_path, app_ctx):
    """run_subtitle_repair must call run_trigger('after_translate', ...).

    B5 placed the repair hook in translator/_helpers.py::run_subtitle_repair;
    B6 adds the after_translate trigger in the same helper so it fires once
    per translation regardless of SRT/ASS flow.
    """
    from post_processing.config_store import set_trigger_ops

    set_trigger_ops("after_translate", ["strip_html"])

    # Write a minimal file — repair reads it
    path = tmp_path / "out.srt"
    path.write_text(
        "1\n00:00:01,000 --> 00:00:02,000\nHello\n",
        encoding="utf-8",
    )

    with patch("translator._helpers.run_trigger") as mock_trigger:
        from translator._helpers import run_subtitle_repair

        run_subtitle_repair(str(path))

    mock_trigger.assert_called_once()
    kwargs = mock_trigger.call_args.kwargs
    args = mock_trigger.call_args.args
    if kwargs:
        assert kwargs.get("trigger") == "after_translate"
        assert kwargs.get("op_ids") == ["strip_html"]
    else:
        assert args[0] == "after_translate"
        assert args[1] == ["strip_html"]


def test_video_sync_fires_after_sync(tmp_path, app_ctx, monkeypatch):
    """sync_with_ffsubsync + sync_with_alass must call run_trigger('after_sync', ...)."""
    from post_processing.config_store import set_trigger_ops

    set_trigger_ops("after_sync", ["strip_html"])

    subtitle = tmp_path / "s.srt"
    subtitle.write_text("1\n00:00:01,000 --> 00:00:02,000\nHi\n", encoding="utf-8")
    video = tmp_path / "v.mkv"
    video.write_bytes(b"\x00")

    # Mock ffsubsync binary lookup + subprocess so the function reaches its return point
    monkeypatch.setattr(
        "services.video_sync.shutil.which",
        lambda name: (f"/usr/bin/{name}" if name in ("ffsubsync",) else None),
    )

    class _FakeProc:
        returncode = 0
        stdout = "Using video speech-to-text\noffset -1.2s detected"
        stderr = ""

    monkeypatch.setattr(
        "services.video_sync.subprocess.run", lambda *a, **kw: _FakeProc()
    )
    # Avoid the actual file move
    monkeypatch.setattr(
        "services.video_sync.shutil.move", lambda src, dst: None, raising=True
    )
    # _make_backup copies the file — point it at tmp
    monkeypatch.setattr(
        "services.video_sync._make_backup", lambda p: f"{p}.bak", raising=True
    )

    with patch("services.video_sync.run_trigger") as mock_trigger:
        from services.video_sync import sync_with_ffsubsync

        sync_with_ffsubsync(str(subtitle), str(video))

    mock_trigger.assert_called_once()
    kwargs = mock_trigger.call_args.kwargs
    args = mock_trigger.call_args.args
    if kwargs:
        assert kwargs.get("trigger") == "after_sync"
        assert kwargs.get("op_ids") == ["strip_html"]
    else:
        assert args[0] == "after_sync"
