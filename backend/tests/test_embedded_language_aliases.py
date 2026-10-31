"""The embedded provider reads language tags like the rest of Sublarr.

Audit #61 A22: it had its own short ISO 639-2 table, so a track tagged
"German" or "nob" was skipped by the embedded search while the scanner and the
MediaInfo fallback recognised it.
"""

import pytest

from config_language_data import normalize_language_code
from providers.embedded import EmbeddedSubtitlesProvider, _normalize_lang


@pytest.mark.parametrize("tag", ["ger", "deu", "German", "nob", "eng", "jpn", "chi", "pt-BR"])
def test_a_known_alias_is_the_central_answer(tag):
    assert _normalize_lang(tag) == normalize_language_code(tag)


@pytest.mark.parametrize("tag", ["und", "zzz", ""])
def test_an_unknown_tag_is_no_language(tag):
    assert _normalize_lang(tag) is None


def test_every_canonical_language_can_be_requested():
    assert {"de", "no", "ja", "pt"} <= EmbeddedSubtitlesProvider.languages
