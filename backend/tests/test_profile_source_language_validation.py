"""A profile's source language must be a language tag (#80 follow-up).

Since #80 the profile source names temporary files in the wanted search, so
a value like "../x" must be refused when the profile is saved.
"""

import pytest

from services.profile_service import (
    ProfileValidationError,
    validate_create_profile_data,
    validate_update_profile_fields,
)

_BASE = {"name": "P", "target_languages": ["de"], "translation_backend": "ollama"}


@pytest.mark.parametrize("bad", ["../x", "en/..", "EN GLISH", "", "e", "toolongcode"])
def test_create_refuses_a_source_that_is_not_a_language_tag(bad):
    with pytest.raises(ProfileValidationError, match="source_language"):
        validate_create_profile_data({**_BASE, "source_language": bad})


@pytest.mark.parametrize("good", ["en", "ja", "pt-BR", "zh-Hans"])
def test_create_accepts_language_tags(good):
    assert validate_create_profile_data({**_BASE, "source_language": good})["source_lang"] == good


def test_create_defaults_to_en():
    assert validate_create_profile_data(dict(_BASE))["source_lang"] == "en"


def test_update_refuses_a_bad_source():
    with pytest.raises(ProfileValidationError, match="source_language"):
        validate_update_profile_fields({"source_language": "../x"})


@pytest.mark.parametrize(
    ("raw", "clean"), [("EN", "en"), (" de ", "de"), ("PT-BR", "pt-BR"), ("Ja", "ja")]
)
def test_create_normalises_case_and_spaces(raw, clean):
    # A profile saved before the validation may hold "EN"; refusing it would
    # block every later save of that profile from the UI.
    assert validate_create_profile_data({**_BASE, "source_language": raw})["source_lang"] == clean


def test_update_normalises_a_legacy_upper_case_source():
    assert validate_update_profile_fields({"source_language": "EN"})["source_language"] == "en"
