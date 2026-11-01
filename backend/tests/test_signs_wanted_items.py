"""Which wanted items exist for full and forced / signs & songs subtitles.

Found while building signs & songs support: the scanner only created a
[Forced] item when the full subtitle was missing, cleanup removed a [Forced]
item as soon as the full subtitle existed, and standalone mode never created
one. A library that already had subtitles therefore never got its signs.
"""

from unittest.mock import MagicMock, patch

import pytest

ASS = """[Script Info]
ScriptType: v4.00+

[V4+ Styles]
Format: Name, Fontname, Fontsize
Style: Default,Arial,20

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,Hello
"""

_DIALOGUE_STREAM = {
    "codec_type": "subtitle",
    "codec_name": "ass",
    "disposition": {},
    "tags": {"language": "eng", "title": "Dialogue"},
}
_SIGNS_STREAM = {
    "codec_type": "subtitle",
    "codec_name": "ass",
    "disposition": {"forced": 1},
    "tags": {"language": "eng", "title": "Signs & Songs"},
}


@pytest.fixture
def video(tmp_path):
    path = tmp_path / "Show - S01E02.mkv"
    path.write_bytes(b"x")
    return path


def _sidecar(video, suffix):
    path = video.with_name(video.stem + suffix)
    path.write_text(ASS, encoding="utf-8")
    return path


# --- detection of what already exists ------------------------------------


def test_an_embedded_signs_track_covers_forced_but_not_full(video):
    from translator import detect_existing_target_for_lang

    probe = {"streams": [_SIGNS_STREAM]}

    assert detect_existing_target_for_lang(str(video), "en", probe, subtitle_type="forced") == "ass"
    assert detect_existing_target_for_lang(str(video), "en", probe) is None


def test_an_embedded_full_plus_signs_track_is_a_dialogue_track(video):
    from translator import detect_existing_target_for_lang

    stream = {**_DIALOGUE_STREAM, "tags": {"language": "eng", "title": "Full + Signs"}}
    probe = {"streams": [stream]}

    assert detect_existing_target_for_lang(str(video), "en", probe) == "ass"
    assert detect_existing_target_for_lang(str(video), "en", probe, subtitle_type="forced") is None


def test_an_embedded_dialogue_track_covers_full_but_not_forced(video):
    from translator import detect_existing_target_for_lang

    probe = {"streams": [_DIALOGUE_STREAM]}

    assert detect_existing_target_for_lang(str(video), "en", probe) == "ass"
    assert detect_existing_target_for_lang(str(video), "en", probe, subtitle_type="forced") is None


def test_a_forced_sidecar_is_not_the_full_subtitle(video):
    from translator import detect_existing_target_for_lang

    _sidecar(video, ".en.forced.ass")

    assert detect_existing_target_for_lang(str(video), "en") is None
    assert detect_existing_target_for_lang(str(video), "en", subtitle_type="forced") == "ass"


# --- cleanup ---------------------------------------------------------------


def _cleanup(items, monkeypatch):
    from services.wanted_scanner_core import WantedScanner

    removed = []
    monkeypatch.setattr("db.wanted.get_wanted_items_for_cleanup", lambda: items)
    monkeypatch.setattr("db.wanted.delete_wanted_items_by_ids", lambda ids: removed.extend(ids))
    monkeypatch.setattr("services.standalone_library.wanted_item_path_refusal", lambda item: None)
    scanner = object.__new__(WantedScanner)
    scanner._cleanup(set())
    return removed


def _item(item_id, video, subtitle_type):
    return {
        "id": item_id,
        "file_path": str(video),
        "target_language": "en",
        "instance_name": "",
        "subtitle_type": subtitle_type,
    }


def test_cleanup_keeps_a_forced_item_when_only_the_full_subtitle_exists(video, monkeypatch):
    _sidecar(video, ".en.ass")

    removed = _cleanup([_item(1, video, "full"), _item(2, video, "forced")], monkeypatch)

    assert removed == [1]


def test_cleanup_removes_a_forced_item_once_its_file_exists(video, monkeypatch):
    _sidecar(video, ".en.forced.ass")

    removed = _cleanup([_item(1, video, "full"), _item(2, video, "forced")], monkeypatch)

    assert removed == [2]


# --- which items a profile asks for ----------------------------------------


@pytest.mark.parametrize(
    ("profile", "expected"),
    [
        ({}, (True, False)),
        ({"forced_preference": "separate"}, (True, True)),
        ({"prefer_signs": True}, (True, True)),
        ({"prefer_signs": True, "download_full": False}, (False, True)),
        ({"forced_preference": "auto"}, (True, False)),
    ],
)
def test_wanted_kinds(profile, expected):
    from services.wanted_item_scanner import _wanted_kinds

    assert _wanted_kinds(profile) == expected


def test_standalone_creates_the_forced_item_next_to_an_existing_full_subtitle(video):
    from standalone.scanner import StandaloneScanner

    _sidecar(video, ".en.ass")
    scanner = object.__new__(StandaloneScanner)
    upserts = []
    with (
        patch("db.wanted.upsert_wanted_item", side_effect=lambda **kw: upserts.append(kw)),
        patch.object(StandaloneScanner, "_check_existing_subtitle", return_value="ass"),
        patch.object(StandaloneScanner, "_requeue_status", return_value="wanted"),
        patch.object(StandaloneScanner, "_language_satisfied", return_value=True),
    ):
        written = scanner._upsert_wanted_for_language(
            item_type="episode",
            file_path=str(video),
            title="Show -- S01E02",
            target_lang="en",
            owner={"standalone_series_id": 7},
            kinds=(True, True),
            unwanted={"full": set(), "forced": set()},
            season_episode="S01E02",
        )

    assert written == 1
    assert [(u["subtitle_type"], u["title"]) for u in upserts] == [
        ("forced", "Show -- S01E02 [Forced]")
    ]
    assert upserts[0]["standalone_series_id"] == 7


@pytest.mark.parametrize(("kind", "expected"), [("full", [1]), ("forced", [2])])
def test_a_kind_the_profile_no_longer_wants_is_dropped(video, kind, expected):
    from services.wanted_item_scanner import _drop_pending

    rows = {
        "full": [(1, str(video), "en"), (3, str(video), "de")],
        "forced": [(2, str(video), "en")],
    }
    deleted = []
    with (
        patch("db.wanted.get_wanted_ids_of_kind", side_effect=lambda paths, k: rows[k]),
        patch("db.wanted.delete_wanted_items_by_ids", side_effect=deleted.extend),
    ):
        _drop_pending({"full": set(), "forced": set(), kind: {(str(video), "en")}})

    assert deleted == expected


def test_the_kind_lookup_is_one_query_per_kind(client):
    from db.wanted import get_wanted_ids_of_kind, upsert_wanted_item

    with client.application.app_context():
        for i, kind in enumerate(("full", "forced", "full")):
            upsert_wanted_item(
                item_type="episode",
                file_path=f"/media/a{i}.mkv",
                title="x",
                target_language="en",
                missing_languages=["en"],
                subtitle_type=kind,
            )
        found = get_wanted_ids_of_kind(["/media/a0.mkv", "/media/a1.mkv"], "forced")

    assert [(path, lang) for _id, path, lang in found] == [("/media/a1.mkv", "en")]


# --- the downloaded file itself -----------------------------------------------


def _ass(dialogue_lines, signs_lines):
    head = ASS.split("[Events]")[0].replace(
        "Style: Default,Arial,20", "Style: Default,Arial,20\nStyle: Signs,Arial,20"
    )
    events = [
        f"Dialogue: 0,0:00:{i % 60:02d}.00,0:00:{i % 60:02d}.50,Default,,0,0,0,,line {i}"
        for i in range(dialogue_lines)
    ] + [
        f"Dialogue: 0,0:00:{i % 60:02d}.00,0:00:{i % 60:02d}.50,Signs,,0,0,0,,sign {i}"
        for i in range(signs_lines)
    ]
    return (
        head + "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
        "Effect, Text\n" + "\n".join(events) + "\n"
    ).encode()


def _ass_result(kind):
    from providers.base import SubtitleFormat, SubtitleResult

    result = SubtitleResult(
        provider_name="animetosho", subtitle_id="1", language="en", format=SubtitleFormat.ASS
    )
    result.set_kind(kind, 0.95)
    return result


def test_a_forced_item_refuses_a_signs_file_that_is_full_dialogue():
    from forced_detection import content_kind_mismatch

    query = MagicMock(forced_only=True, full_only=False)

    assert content_kind_mismatch(_ass_result("signs"), _ass(300, 20), query)
    assert content_kind_mismatch(_ass_result("signs"), _ass(10, 40), query) is None


def test_a_full_item_refuses_a_file_of_only_signs_styles():
    from forced_detection import content_kind_mismatch

    query = MagicMock(forced_only=False, full_only=True)

    assert content_kind_mismatch(_ass_result("full"), _ass(0, 40), query)
    assert content_kind_mismatch(_ass_result("full"), _ass(300, 20), query) is None


def test_the_content_check_ignores_srt_and_unreadable_files():
    from forced_detection import content_kind_mismatch
    from providers.base import SubtitleFormat

    query = MagicMock(forced_only=True, full_only=False)
    srt = _ass_result("signs")
    srt.format = SubtitleFormat.SRT

    assert content_kind_mismatch(srt, b"1\n00:00:01,000 --> 00:00:02,000\nHi\n", query) is None
    assert content_kind_mismatch(_ass_result("signs"), b"\xff\xfe garbage", query) is None


# --- before the search ----------------------------------------------------------


def test_a_forced_item_is_not_settled_by_the_full_subtitle(video, client):
    """Codex P1: the existing-sidecar check marked new [Forced] items done."""
    from wanted_search.process import _check_existing_sidecar

    _sidecar(video, ".en.ass")
    settings = MagicMock(upgrade_enabled=False)
    item = {"file_path": str(video), "subtitle_type": "forced"}

    with (
        client.application.app_context(),
        patch("wanted_search.process.update_existing_sub"),
        patch("wanted_search.process.update_wanted_status") as status,
    ):
        assert _check_existing_sidecar(item, 1, "en", settings) is None
        status.assert_not_called()

        _sidecar(video, ".en.forced.ass")
        assert _check_existing_sidecar(item, 1, "en", settings)["status"] == "skipped"


def test_cutoff_and_audio_gates_skip_forced_items(video):
    """A [Forced] item is wanted because the audio already is the target language."""
    from wanted_search.process import _check_profile_cutoff_and_audio

    pf = {"cutoff_language": "en", "audio_exclude_languages": ["en"]}
    _sidecar(video, ".en.ass")

    assert (
        _check_profile_cutoff_and_audio(
            {"file_path": str(video), "subtitle_type": "forced"}, 1, "en", pf
        )
        is None
    )
