"""The standalone scanner counts embedded target-language tracks (Forgejo #36).

Discord #general, 2026-09-16: in standalone mode an embedded English ASS track
did not satisfy the profile, so the file became a wanted item and was searched
at providers although ``use_embedded_subs`` was on. The Sonarr/Radarr scanner
probes the container; the standalone one never passed probe data, so only
sidecar files counted and the two scanners disagreed.

Every caller of ``_check_existing_subtitle`` skips a language on ``"ass"`` and
stores anything else as ``existing_sub``; these tests pin what it returns.
"""

from unittest.mock import patch

import pytest

from standalone.scanner import StandaloneScanner

ENG_ASS = {
    "streams": [{"codec_type": "subtitle", "codec_name": "ass", "tags": {"language": "eng"}}]
}
ENG_SRT = {
    "streams": [{"codec_type": "subtitle", "codec_name": "subrip", "tags": {"language": "eng"}}]
}
JPN_ASS = {
    "streams": [{"codec_type": "subtitle", "codec_name": "ass", "tags": {"language": "jpn"}}]
}


@pytest.fixture
def episode(app_ctx, tmp_path, monkeypatch):
    from config import get_settings

    monkeypatch.setattr(get_settings(), "use_embedded_subs", True)
    mkv = tmp_path / "Show - S01E01.mkv"
    mkv.touch()
    return mkv


def _check(path, probe, lang="en"):
    with patch("ass_probe.get_media_streams", return_value=probe) as probed:
        result = StandaloneScanner()._check_existing_subtitle(str(path), lang)
    return result, probed


def test_embedded_target_ass_satisfies_the_language(episode):
    result, _ = _check(episode, ENG_ASS)

    assert result == "embedded_ass"
    assert StandaloneScanner()._language_satisfied(str(episode), "en", result)


def test_embedded_target_srt_is_reported_as_embedded(episode):
    result, _ = _check(episode, ENG_SRT)

    assert result == "embedded_srt"


def test_embedded_track_in_another_language_does_not_count(episode):
    result, _ = _check(episode, JPN_ASS)

    assert result is None


def test_sidecar_srt_is_still_reported_as_srt(episode):
    episode.with_suffix(".en.srt").write_text("1\n00:00:01,000 --> 00:00:02,000\nHi\n")

    result, _ = _check(episode, ENG_SRT)

    assert result == "srt"


def test_embedded_tracks_are_ignored_when_the_setting_is_off(episode, monkeypatch):
    from config import get_settings

    monkeypatch.setattr(get_settings(), "use_embedded_subs", False)

    result, probed = _check(episode, ENG_ASS)

    assert result is None
    probed.assert_not_called()


def test_containers_that_cannot_carry_tracks_are_not_probed(app_ctx, tmp_path, monkeypatch):
    from config import get_settings

    monkeypatch.setattr(get_settings(), "use_embedded_subs", True)
    avi = tmp_path / "Show - S01E01.avi"
    avi.touch()

    result, probed = _check(avi, ENG_ASS)

    assert result is None
    probed.assert_not_called()


def test_a_failing_probe_falls_back_to_sidecars(episode):
    with patch("ass_probe.get_media_streams", side_effect=RuntimeError("ffprobe missing")):
        result = StandaloneScanner()._check_existing_subtitle(str(episode), "en")

    assert result is None


# ── Rows created before the fix ──────────────────────────────────────────────


def _wanted(path, lang, status):
    from datetime import UTC, datetime

    from db.models.core import WantedItem
    from extensions import db

    now = datetime(2026, 9, 16, tzinfo=UTC)
    item = WantedItem(
        item_type="episode",
        file_path=str(path),
        title="T",
        season_episode="S01E01",
        existing_sub="",
        missing_languages="[]",
        embedded_languages="[]",
        target_language=lang,
        subtitle_type="full",
        status=status,
        instance_name="standalone",
        added_at=now,
        updated_at=now,
    )
    db.session.add(item)
    db.session.commit()
    return item.id


def test_a_stale_wanted_row_is_dropped_once_an_embedded_track_satisfies_it(episode):
    from db.wanted import get_wanted_item

    item_id = _wanted(episode, "en", "wanted")

    assert StandaloneScanner()._language_satisfied(str(episode), "en", "embedded_ass")
    assert get_wanted_item(item_id) is None


def test_a_provisional_machine_translation_row_is_never_dropped(episode):
    from db.wanted import get_wanted_item

    item_id = _wanted(episode, "en", "provisional")

    assert StandaloneScanner()._language_satisfied(str(episode), "en", "embedded_ass")
    assert get_wanted_item(item_id) is not None


def test_a_sidecar_ass_does_not_drop_rows(episode):
    """A sidecar .ass may be a kept-seeking machine translation; leave it to cleanup."""
    from db.wanted import get_wanted_item

    item_id = _wanted(episode, "en", "wanted")

    assert StandaloneScanner()._language_satisfied(str(episode), "en", "ass")
    assert get_wanted_item(item_id) is not None


@pytest.mark.parametrize("existing", [None, "srt", "embedded_srt"])
def test_other_results_do_not_satisfy_the_language(episode, existing):
    assert not StandaloneScanner()._language_satisfied(str(episode), "en", existing)
