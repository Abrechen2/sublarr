"""A provider download whose letters contradict the language it was sold as
is refused before it reaches the disk.

Prod 2026-09-06 05:15: OpenSubtitles delivered "German" (score 4) for HELL
MODE S02E04. The file was Traditional Chinese. It was saved as ``.de.srt``,
the wanted item closed, and the player offered Chinese under the German flag.
"""

from __future__ import annotations

import pytest

from providers.base import SubtitleFormat, SubtitleResult

CHINESE_SRT = (
    "1\n00:00:00,538 --> 00:00:05,162\n彷彿在夢境中遨遊\n\n"
    "2\n00:00:05,163 --> 00:00:10,006\n因淡淡的期待而心情雀躍\n\n"
    "3\n00:00:10,007 --> 00:00:15,672\n將胸口的光芒緊緊藏起\n\n"
    "4\n00:00:15,673 --> 00:00:20,467\n某天的日常變得格外令人懷念呢\n\n"
    "5\n00:00:20,468 --> 00:00:25,272\n甚至能笑著這麼說 每天都在成長\n\n"
).encode()

GERMAN_SRT = (
    "1\n00:00:00,538 --> 00:00:05,162\nAls würde ich durch einen Traum wandern\n\n"
    "2\n00:00:05,163 --> 00:00:10,006\nMein Herz hüpft vor leiser Erwartung\n\n"
    "3\n00:00:10,007 --> 00:00:15,672\nDas Licht in meiner Brust halte ich fest verborgen\n\n"
).encode()


@pytest.fixture
def allow_paths(monkeypatch):
    monkeypatch.setattr("security_utils.is_safe_path", lambda *a, **k: True, raising=False)


def _result(content: bytes, language: str) -> SubtitleResult:
    return SubtitleResult(
        provider_name="opensubtitles",
        subtitle_id="1",
        language=language,
        format=SubtitleFormat.SRT,
        content=content,
    )


def test_chinese_payload_sold_as_german_is_refused(tmp_path, allow_paths):
    from providers.download_manager import save_subtitle

    out = tmp_path / "ep.de.srt"
    with pytest.raises(RuntimeError, match="script"):
        save_subtitle(_result(CHINESE_SRT, "de"), str(out))
    assert not out.exists()


def test_german_payload_sold_as_german_is_saved(tmp_path, allow_paths):
    from providers.download_manager import save_subtitle

    out = tmp_path / "ep.de.srt"
    saved = save_subtitle(_result(GERMAN_SRT, "de"), str(out))
    assert saved.endswith(".de.srt")
    assert out.exists()


def test_chinese_payload_sold_as_chinese_is_saved(tmp_path, allow_paths):
    from providers.download_manager import save_subtitle

    out = tmp_path / "ep.zh.srt"
    save_subtitle(_result(CHINESE_SRT, "zh"), str(out))
    assert out.exists()
