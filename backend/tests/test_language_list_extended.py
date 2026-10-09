"""Every ISO 639-1 language is selectable, named in English and German (1.16.0).

The picker stopped at 64 languages while providers serve far more; the
catalog providers alone declare 224 codes. The extension must not move any
existing tag: foreign-track cleanup decides keep/strip from these tables.
"""

from collections import Counter

from config_language_data import _LANGUAGE_TAGS, SUPPORTED_LANGUAGES, normalize_language_code
from config_language_names import EXTRA_LANGUAGES, GERMAN_NAMES


def test_every_language_has_an_english_and_a_german_name():
    assert len(SUPPORTED_LANGUAGES) >= 180
    assert all(entry["name"] and entry["name_de"] for entry in SUPPORTED_LANGUAGES)
    assert {e["code"]: e["name_de"] for e in SUPPORTED_LANGUAGES}["de"] == "Deutsch"


def test_codes_are_unique_and_sorted_by_english_name():
    codes = [entry["code"] for entry in SUPPORTED_LANGUAGES]
    assert len(codes) == len(set(codes))
    names = [entry["name"] for entry in SUPPORTED_LANGUAGES]
    assert names == sorted(names)


def test_core_languages_keep_a_german_name_each():
    core = {entry["code"] for entry in SUPPORTED_LANGUAGES} - {row[0] for row in EXTRA_LANGUAGES}
    assert core <= set(GERMAN_NAMES)


def test_three_letter_tags_of_new_languages_resolve():
    assert normalize_language_code("bel") == "be"
    assert normalize_language_code("wel") == "cy"
    assert normalize_language_code("cym") == "cy"
    assert normalize_language_code("tib") == "bo"
    assert normalize_language_code("kurdish") == "ku"


def test_existing_tags_did_not_move():
    assert normalize_language_code("ger") == "de"
    assert normalize_language_code("nob") == "no"
    assert normalize_language_code("pob") == "pt"
    assert normalize_language_code("chi-tra") == "zh-hant"


def test_no_tag_belongs_to_two_languages():
    counts = Counter(tag for tags in _LANGUAGE_TAGS.values() for tag in tags)
    assert [tag for tag, n in counts.items() if n > 1] == []


def test_lat_stays_unknown_because_it_often_means_latin_american_spanish():
    assert normalize_language_code("lat") == "lat"
    assert normalize_language_code("la") == "la"
