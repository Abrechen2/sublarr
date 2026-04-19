"""Plan B5 — integration: save_subtitle calls subtitle_repair."""

from pathlib import Path

from providers.base import SubtitleFormat, SubtitleResult


def test_save_subtitle_calls_repair(tmp_path, monkeypatch):
    """save_subtitle() must run repair_bytes() on result.content before writing."""
    # Content with BOM + wrong newlines — must come out clean on disk
    dirty = b"\xef\xbb\xbf1\r\r\n00:00:01,000 --> 00:00:02,000\r\r\nHi\r\r\n"

    result = SubtitleResult(
        provider_name="p",
        subtitle_id="1",
        language="en",
        format=SubtitleFormat.SRT,
        content=dirty,
    )

    from providers.download_manager import save_subtitle

    out_path = tmp_path / "test.en.srt"

    # save_subtitle validates path is under media_path via a function-local import;
    # monkeypatch the source module so the import inside save_subtitle picks it up.
    monkeypatch.setattr(
        "security_utils.is_safe_path",
        lambda *args, **kw: True,
        raising=False,
    )

    saved = save_subtitle(result, str(out_path))

    on_disk = Path(saved).read_bytes()
    assert not on_disk.startswith(b"\xef\xbb\xbf"), "BOM must be stripped"
    assert b"\r\r\n" not in on_disk, "Wrong newlines must be normalized"
    # Content preserved
    assert b"Hi" in on_disk


def test_save_subtitle_skips_repair_when_flag_disabled(tmp_path, monkeypatch):
    """When enable_subtitle_repair=False, save_subtitle writes raw bytes."""
    dirty = b"\xef\xbb\xbf1\n00:00:01,000 --> 00:00:02,000\nHi\n"

    result = SubtitleResult(
        provider_name="p",
        subtitle_id="2",
        language="en",
        format=SubtitleFormat.SRT,
        content=dirty,
    )

    monkeypatch.setattr(
        "security_utils.is_safe_path",
        lambda *args, **kw: True,
        raising=False,
    )
    # Force the feature flag off via the Settings singleton
    from config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "enable_subtitle_repair", False, raising=False)

    from providers.download_manager import save_subtitle

    out_path = tmp_path / "no_repair.en.srt"
    saved = save_subtitle(result, str(out_path))
    on_disk = Path(saved).read_bytes()
    # BOM should survive
    assert on_disk.startswith(b"\xef\xbb\xbf")
