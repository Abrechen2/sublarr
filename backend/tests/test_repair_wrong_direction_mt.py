"""Repair machine translations written in the wrong language.

Until 1.14.3 every Ollama request asked for the global direction (English to
German), so a job for any other target wrote German into e.g. ``.en.srt``.
The repair trashes exactly those files — recorded as a machine translation,
labelled with a non-configured language, and whose CONTENT is the configured
target language — and hands the episode back to the search.
"""

from datetime import UTC, datetime

import pytest

from db.models.core import WantedItem
from extensions import db

GERMAN = (
    "1\n00:00:03,560 --> 00:00:05,190\nSilvesterabend. Wir gehen gleich los.\n\n"
    "2\n00:00:07,500 --> 00:00:12,260\nIch mag den Gesangswettstreit wirklich sehr.\n\n"
    "3\n00:00:12,260 --> 00:00:16,760\nBist du sicher, dass du das wirklich willst?\n"
)
ENGLISH = (
    "1\n00:00:03,560 --> 00:00:05,190\nNew Year's Eve. We are heading out soon.\n\n"
    "2\n00:00:07,500 --> 00:00:12,260\nI really love the song battle every year.\n\n"
    "3\n00:00:12,260 --> 00:00:16,760\nAre you sure that you really want to do this?\n"
)


def _record(video, lang, fmt, source="machine_translation"):
    from db.providers import record_subtitle_download

    record_subtitle_download(
        "translation", f"mt:{lang}.{fmt}", lang, fmt, video, 0, source=source, record_stats=False
    )


def _mt_rows(video):
    from db.providers import get_machine_translation_sidecars

    return sorted(get_machine_translation_sidecars(video))


def _wanted(video, lang, status, pending=None):
    now = datetime(2026, 9, 16, tzinfo=UTC)
    item = WantedItem(
        item_type="episode",
        file_path=video,
        title="T",
        season_episode="S01E01",
        existing_sub="",
        missing_languages="[]",
        embedded_languages="[]",
        target_language=lang,
        subtitle_type="full",
        status=status,
        added_at=now,
        updated_at=now,
        mt_pending_original=pending,
    )
    db.session.add(item)
    db.session.commit()
    return item.id


@pytest.fixture
def library(app_ctx, tmp_path, monkeypatch):
    from config import get_settings

    monkeypatch.setattr(get_settings(), "media_path", str(tmp_path))
    monkeypatch.setattr(get_settings(), "target_language", "de")
    mkv = tmp_path / "ep.mkv"
    mkv.touch()
    return tmp_path, str(mkv)


def test_german_text_in_an_english_machine_translation_is_a_candidate(library):
    from scripts.repair_wrong_direction_mt import find_candidates

    root, video = library
    (root / "ep.en.srt").write_text(GERMAN, encoding="utf-8")
    _record(video, "en", "srt")

    candidates = find_candidates()

    assert [(c.path, c.language, c.detected) for c in candidates] == [
        (str(root / "ep.en.srt"), "en", "de")
    ]


def test_a_correct_english_translation_is_left_alone(library):
    from scripts.repair_wrong_direction_mt import find_candidates

    root, video = library
    (root / "ep.en.srt").write_text(ENGLISH, encoding="utf-8")
    _record(video, "en", "srt")

    assert find_candidates() == []


def test_a_subtitle_that_is_not_a_machine_translation_is_left_alone(library):
    from scripts.repair_wrong_direction_mt import find_candidates

    root, video = library
    (root / "ep.en.srt").write_text(GERMAN, encoding="utf-8")

    assert find_candidates() == []


def test_translations_for_the_configured_target_are_not_candidates(library):
    from scripts.repair_wrong_direction_mt import find_candidates

    root, video = library
    (root / "ep.de.srt").write_text(GERMAN, encoding="utf-8")
    _record(video, "de", "srt")

    assert find_candidates() == []


def test_dry_run_changes_nothing(library):
    from scripts.repair_wrong_direction_mt import find_candidates, repair

    root, video = library
    (root / "ep.en.srt").write_text(GERMAN, encoding="utf-8")
    _record(video, "en", "srt")

    report = repair(find_candidates(), apply=False)

    assert report.trashed == [] and len(report.planned) == 1
    assert (root / "ep.en.srt").exists()
    assert _mt_rows(video) == [("en", "srt")]


def test_apply_trashes_forgets_the_translation_and_searches_again(library):
    from db.wanted import get_wanted_item
    from scripts.repair_wrong_direction_mt import find_candidates, repair

    root, video = library
    (root / "ep.en.srt").write_text(GERMAN, encoding="utf-8")
    (root / "ep.en.srt.quality.json").write_text("{}")
    (root / "ep.de.srt").write_text(GERMAN, encoding="utf-8")
    _record(video, "en", "srt")
    _record(video, "de", "srt")
    provisional = _wanted(video, "en", "provisional", pending='{"provider": "animetosho"}')

    report = repair(find_candidates(), apply=True)

    assert len(report.trashed) == 1 and report.errors == []
    assert not (root / "ep.en.srt").exists()
    assert list((root / ".sublarr_trash").rglob("ep.en.srt"))
    assert (root / "ep.de.srt").exists()
    # The German MT for the German target is untouched, the wrong one is forgotten.
    assert _mt_rows(video) == [("de", "srt")]
    item = get_wanted_item(provisional)
    assert item["status"] == "wanted"
    # A found original stays approvable.
    assert item["mt_pending_original"] is not None
