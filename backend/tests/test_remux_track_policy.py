"""remove_foreign_subtitle_streams delegates to select_tracks."""

import json
from pathlib import Path
from unittest.mock import patch

import remux
from services.foreign_tracks.select import TrackPolicy

_DE_EN = {"de", "deu", "ger", "german", "en", "eng", "english"}


def _probe():
    path = Path(__file__).parent / "fixtures" / "ffprobe_oshi_no_ko_s02e01.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _run(**kw):
    with (
        patch.object(remux, "check_hardlink_policy", return_value=True),
        patch.object(remux, "get_media_streams", return_value=_probe()),
        patch.object(remux, "remove_subtitle_streams", return_value="/bak") as strip,
    ):
        remux.remove_foreign_subtitle_streams(video_path="/m/x.mkv", target_languages=_DE_EN, **kw)
    return strip


def test_without_a_policy_the_strip_set_is_unchanged():
    strip = _run()
    removed = sorted(i for i, _ in strip.call_args.kwargs["streams"])
    assert removed == [7, 8, 9, 10, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22]


def test_one_per_language_also_strips_variants():
    strip = _run(policy=TrackPolicy(mode="one_per_language"))
    removed = sorted(i for i, _ in strip.call_args.kwargs["streams"])
    assert 6 in removed and 4 not in removed and 5 not in removed


def test_sub_only_index_is_passed_for_mkvmerge():
    strip = _run(policy=TrackPolicy(mode="one_per_language"))
    pairs = dict(strip.call_args.kwargs["streams"])
    assert pairs[6] == 2 and pairs[7] == 3
