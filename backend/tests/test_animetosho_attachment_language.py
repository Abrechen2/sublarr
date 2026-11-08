"""An attachment's own language tag decides its language, for every language.

Prod 2026-11-07: Gachiakuta S01E22 got ``Vietnamese_Tieng_Viet.vie.ass`` as its
English subtitle. ``vie`` was missing from the provider's short ISO table, so
the language fell through to the filename guess, whose default is "en". The
same path saved Indonesian (``ind``) and Catalan (``cat``) tracks as English.
"""

import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from providers.animetosho import AnimeToshoProvider
from providers.base import VideoQuery


def _attachment(info: dict) -> dict:
    return {
        "id": 3085253,
        "type": "subtitle",
        "url": "https://storage.animetosho.xyz/attachments/0028d/c80.xz",
        "info": {"format": "ASS", **info},
    }


def _results(info: dict, languages: list[str]):
    provider = AnimeToshoProvider()
    provider.session = MagicMock()
    detail = MagicMock()
    detail.status_code = 200
    detail.json.return_value = {
        "files": [{"filename": "Gachiakuta - S01E22.mkv", "attachments": [_attachment(info)]}]
    }
    provider.session.get.return_value = detail
    entry = {"id": 683348, "title": "[LbE3L] Gachiakuta S01 [Multi-Subs]", "num_files": 1}
    query = VideoQuery(series_title="Gachiakuta", episode=22, languages=languages)
    return provider._process_entry(entry, query)


@pytest.mark.parametrize(
    "code, name, expected",
    [("vie", "Vietnamese", "vi"), ("ind", "Indonesian", "id"), ("cat", "Catalan", "ca")],
)
def test_a_tagged_foreign_track_is_not_offered_as_english(code, name, expected):
    assert _results({"language_code": code, "language": name}, ["en"]) == []
    found = _results({"language_code": code, "language": name}, [expected])
    assert [r.language for r in found] == [expected]


def test_an_unknown_tag_is_not_guessed_into_english():
    assert _results({"language_code": "qaa", "language": "Klingon"}, ["en"]) == []


def test_the_common_tags_still_resolve():
    assert [r.language for r in _results({"language_code": "ger"}, ["de"])] == ["de"]
    assert [r.language for r in _results({"lang": "eng"}, ["en"])] == ["en"]


def test_an_untagged_track_still_falls_back_to_the_filename_guess():
    assert [r.language for r in _results({"language": "English"}, ["en"])] == ["en"]
    assert [r.language for r in _results({"language_code": "und"}, ["en"])] == ["en"]


def test_an_untagged_track_named_after_its_language_keeps_it():
    assert _results({"language": "Vietnamese"}, ["en"]) == []
    assert [r.language for r in _results({"language": "Vietnamese"}, ["vi"])] == ["vi"]
