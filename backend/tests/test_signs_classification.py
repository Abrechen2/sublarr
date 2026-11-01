"""Search-time recognition of signs & songs and forced subtitles.

Track names below are the ones AnimeTosho returned for ten random English
wanted episodes on the RC (2026-11-01). Before, 1 of 18 signs tracks was
recognised: AnimeTosho's secure_filename turns "Signs & Songs" into
"Signs__Songs", which no pattern matched, and the per-track MKV flags the API
sends were ignored.
"""

import pytest

from forced_detection import classify_result_kind, classify_track_label


@pytest.mark.parametrize(
    "label",
    [
        "Signs & Songs",
        "Signs__Songs.eng.ass",
        "Signs_Songs",
        "neoHEVC_Signs_Songs.enm.ass",
        "Signs__Songs_CR.eng.ass",
        "Signs__Songs_AnimeChap_neoDESU.eng.ass",
        "Signs + Songs",
        "Signs and Songs",
        "Signs Only",
        "Songs Only",
        "[Group] Show - 01 (Signs & Songs).ass",
    ],
)
def test_explicit_signs_names_are_signs(label):
    kind, confidence = classify_track_label(label)
    assert kind == "signs"
    assert confidence >= 0.8


@pytest.mark.parametrize("label", ["English (Signs) Official", "English_Signs_Official.eng.ass"])
def test_a_bare_signs_word_is_signs_with_lower_confidence(label):
    kind, confidence = classify_track_label(label)
    assert kind == "signs"
    assert confidence < 0.9


@pytest.mark.parametrize(
    "label", ["Forced", "Forced.eng.ass", "English Forced", "Foreign parts", "English_Forced"]
)
def test_forced_names_are_forced(label):
    assert classify_track_label(label)[0] == "forced"


@pytest.mark.parametrize(
    "label",
    [
        "Dialogue",
        "Dialogue.eng.ass",
        "Full Subtitles",
        "Full + Signs",
        "Dialogue & Signs",
        "English",
        "English_subs.eng.ass",
        "track4.eng.ass",
        "English_Anime_Chap.eng.ass",
        "Full (with songs)",
    ],
)
def test_dialogue_tracks_are_full(label):
    assert classify_track_label(label)[0] == "full"


def test_a_series_called_signs_is_not_signs():
    # Bare filenames are only matched on explicit forms; a title word is not one.
    assert classify_result_kind("Signs.2002.1080p.BluRay.en.srt", {}) == ("full", 1.0, "default")


def test_the_animetosho_track_flag_counts():
    kind, _, source = classify_result_kind(
        "track3.eng.ass", {"track_name": "English", "track_forced": True}
    )
    assert (kind, source) == ("forced", "provider_flag")


def test_the_track_name_refines_the_flag_to_signs():
    kind, confidence, _ = classify_result_kind(
        "Signs__Songs.eng.ass", {"track_name": "Signs & Songs", "track_forced": True}
    )
    assert kind == "signs"
    assert confidence >= 0.9


def test_an_unflagged_signs_track_is_still_signs():
    # forced=false on the MKV track must not veto an explicit name.
    kind, _, _ = classify_result_kind(
        "Signs__Songs.eng.ass", {"track_name": "Signs & Songs", "track_forced": False}
    )
    assert kind == "signs"


def test_a_flagged_track_named_dialogue_stays_forced_with_low_confidence():
    kind, confidence, source = classify_result_kind(
        "Dialogue.eng.ass", {"track_name": "Dialogue", "track_forced": True}
    )
    assert (kind, source) == ("forced", "conflict")
    assert confidence < 0.9


def test_opensubtitles_foreign_parts_only_is_forced():
    assert classify_result_kind("x.srt", {"foreign_parts_only": True})[0] == "forced"


def test_old_cached_results_without_track_name_use_the_filename():
    assert classify_result_kind("Signs__Songs.eng.ass", {})[0] == "signs"
