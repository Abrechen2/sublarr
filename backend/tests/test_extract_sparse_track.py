"""A signs-only embedded track must not become the full sidecar.

Prod 2026-11-08: Hell's Paradise S01E10 carries a German SRT track, default,
not forced, titled "de-DE" — eight lines of title cards and credits for a
24-minute episode. Auto-extract wrote it as ``.de.srt``, and the episode
counted as subtitled in German.
"""

from __future__ import annotations

import pytest

_SIGNS = "".join(
    f"{i}\n00:{i:02d}:00,000 --> 00:{i:02d}:04,000\nHell's Paradise\n\n" for i in range(1, 9)
)
_DIALOGUE = "".join(
    f"{i}\n00:{i // 60:02d}:{i % 60:02d},000 --> 00:{i // 60:02d}:{i % 60:02d},900\n"
    f"Line number {i} of the dialogue.\n\n"
    for i in range(1, 301)
)


def _run(tmp_path, monkeypatch, text, kind="full"):
    import services.embedded_extractor as ee

    mkv = tmp_path / "Show - S01E10.mkv"
    mkv.write_bytes(b"\x00")

    def fake_extract(video, stream, out):
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(text)

    trashed: list[str] = []
    monkeypatch.setattr("ass_utils.extract_subtitle_stream", fake_extract)
    monkeypatch.setattr("subtitle_plausibility.video_duration_s", lambda path: 1464.0)
    monkeypatch.setattr(ee, "_sidecar_matches_tag", lambda *a: True)
    monkeypatch.setattr(ee, "_record_extraction", lambda *a: None)
    monkeypatch.setattr(ee, "_trash_path", lambda p: trashed.append(p) or True)

    streams = [
        {"language": "ger", "format": "srt", "sub_index": 0, "stream_index": 2, "kind": kind}
    ]
    result = ee.extract_streams(str(mkv), streams, log_label="test")
    return result, trashed


def test_a_signs_only_full_track_is_dropped_and_kept_in_the_container(tmp_path, monkeypatch):
    (any_extracted, to_remove, extracted), trashed = _run(tmp_path, monkeypatch, _SIGNS)

    assert any_extracted is False
    assert extracted == []
    assert to_remove == [], "the stream must stay in the container"
    assert len(trashed) == 1 and trashed[0].endswith(".srt")


def test_a_dialogue_track_is_extracted(tmp_path, monkeypatch):
    (any_extracted, _to_remove, extracted), trashed = _run(tmp_path, monkeypatch, _DIALOGUE)

    assert any_extracted is True
    assert len(extracted) == 1
    assert trashed == []


@pytest.mark.parametrize("kind", ["forced", "signs"])
def test_a_signs_track_extracted_as_such_is_not_judged(tmp_path, monkeypatch, kind):
    (any_extracted, _to_remove, _extracted), trashed = _run(
        tmp_path, monkeypatch, _SIGNS, kind=kind
    )

    assert any_extracted is True
    assert trashed == []
