"""select_tracks — the single keep/strip decision for embedded subtitle tracks."""

import json
from pathlib import Path

import pytest

from services.foreign_tracks.select import TrackPolicy, select_tracks

_DE_EN = {"de", "deu", "ger", "german", "en", "eng", "english"}
_ONE = TrackPolicy(mode="one_per_language")


def _oshi():
    path = Path(__file__).parent / "fixtures" / "ffprobe_oshi_no_ko_s02e01.json"
    return json.loads(path.read_text(encoding="utf-8"))["streams"]


def _sub(index, lang, codec="subrip", title="", forced=0, sdh=0, default=0):
    return {
        "index": index,
        "codec_type": "subtitle",
        "codec_name": codec,
        "disposition": {"forced": forced, "hearing_impaired": sdh, "default": default},
        "tags": {"language": lang, "title": title},
    }


def _kept(verdicts):
    return sorted(v.index for v in verdicts if v.keep)


def test_legacy_policy_keeps_every_track_of_a_kept_language():
    verdicts = select_tracks(_oshi(), TrackPolicy(), _DE_EN, False, set())
    assert _kept(verdicts) == [4, 5, 6, 11]
    assert {v.reason for v in verdicts if not v.keep} == {"stripped_language"}


def test_one_per_language_keeps_main_and_forced():
    verdicts = select_tracks(_oshi(), _ONE, _DE_EN, False, set())
    by_index = {v.index: v for v in verdicts}
    assert _kept(verdicts) == [4, 5, 11]
    assert by_index[5].reason == "kept_main"
    assert by_index[4].reason == "kept_forced"
    assert by_index[6].reason == "stripped_variant"


def test_keep_sdh_toggle_keeps_the_sdh_track():
    policy = TrackPolicy(mode="one_per_language", keep_sdh=True)
    assert 6 in _kept(select_tracks(_oshi(), policy, _DE_EN, False, set()))


def test_keep_forced_off_strips_the_forced_track():
    policy = TrackPolicy(mode="one_per_language", keep_forced=False)
    assert 4 not in _kept(select_tracks(_oshi(), policy, _DE_EN, False, set()))


def test_ass_beats_srt_beats_image_for_the_main_track():
    streams = [
        _sub(2, "eng", "hdmv_pgs_subtitle", "English", default=1),
        _sub(3, "eng", "subrip", "English"),
        _sub(4, "eng", "ass", "English"),
    ]
    verdicts = select_tracks(streams, _ONE, _DE_EN, False, set())
    assert _kept(verdicts) == [4]


def test_signs_only_ass_is_not_the_main_track():
    streams = [
        _sub(2, "eng", "ass", "Signs & Songs"),
        _sub(3, "eng", "subrip", "English (SDH)", sdh=1),
    ]
    by_index = {v.index: v for v in select_tracks(streams, _ONE, _DE_EN, False, set())}
    assert by_index[3].reason == "kept_main"
    assert by_index[2].reason == "kept_forced"


def test_two_tags_of_one_language_share_one_main_slot():
    streams = [_sub(2, "en", "ass", "English"), _sub(3, "eng", "subrip", "English")]
    assert _kept(select_tracks(streams, _ONE, _DE_EN, False, set())) == [2]


def test_default_flag_breaks_a_format_tie():
    streams = [_sub(2, "eng", "ass", "A"), _sub(3, "eng", "ass", "B", default=1)]
    assert _kept(select_tracks(streams, _ONE, _DE_EN, False, set())) == [3]


def test_event_count_breaks_a_remaining_tie():
    streams = [_sub(2, "eng", "ass", "A"), _sub(3, "eng", "ass", "B")]
    counts = {2: 40, 3: 380}
    verdicts = select_tracks(streams, _ONE, _DE_EN, False, set(), count_events=counts.__getitem__)
    assert _kept(verdicts) == [3]


def test_events_are_not_counted_without_a_tie():
    streams = [_sub(2, "eng", "ass", "A"), _sub(3, "eng", "subrip", "B")]

    def boom(_index):
        raise AssertionError("counted events although format already decided")

    select_tracks(streams, _ONE, _DE_EN, False, set(), count_events=boom)


def test_unknown_kind_counts_as_full():
    streams = [_sub(2, "eng", "ass", "")]
    verdicts = select_tracks(streams, _ONE, _DE_EN, False, set())
    assert verdicts[0].kind == "full" and verdicts[0].keep


def test_real_sidecar_drops_the_embedded_main_track_under_policy_b():
    policy = TrackPolicy(mode="one_per_language", sidecar_policy="drop_if_real_sidecar")
    verdicts = select_tracks(_oshi(), policy, _DE_EN, False, {"de"})
    by_index = {v.index: v for v in verdicts}
    assert by_index[11].reason == "stripped_sidecar"
    assert by_index[5].reason == "kept_main", "no English sidecar — English main stays"


def test_policy_b_without_a_sidecar_keeps_the_last_track():
    policy = TrackPolicy(mode="one_per_language", sidecar_policy="drop_if_real_sidecar")
    streams = [_sub(2, "ger", "subrip", "German")]
    assert _kept(select_tracks(streams, policy, _DE_EN, False, set())) == [2]


def test_policy_b_works_in_mode_all_too():
    policy = TrackPolicy(sidecar_policy="drop_if_real_sidecar")
    streams = [_sub(2, "ger", "subrip", "German"), _sub(3, "ger", "ass", "Signs", forced=1)]
    by_index = {v.index: v for v in select_tracks(streams, policy, _DE_EN, False, {"de"})}
    assert by_index[2].reason == "stripped_sidecar"
    assert by_index[3].keep


def test_und_follows_keep_und():
    streams = [_sub(2, "und", "subrip", "")]
    assert _kept(select_tracks(streams, _ONE, _DE_EN, True, set())) == [2]
    assert _kept(select_tracks(streams, _ONE, _DE_EN, False, set())) == []


def test_sub_index_counts_only_subtitle_streams():
    verdicts = select_tracks(_oshi(), TrackPolicy(), _DE_EN, False, set())
    assert [v.sub_index for v in verdicts] == list(range(19))


@pytest.mark.parametrize("empty", [set(), {""}])
def test_an_empty_keep_set_keeps_everything(empty):
    verdicts = select_tracks(_oshi(), _ONE, empty, False, set())
    assert all(v.keep for v in verdicts)
