"""What the translation pipeline loads from the glossary.

Two leaks, both found reading the code for the 2026-11-14 glossary benchmark:
the loader dropped the ``approved`` flag on the way out, so a pending AI
suggestion was injected into prompts as if it had been accepted; and a global
entry reached every translation whatever its target language.
"""

from __future__ import annotations

import pytest

from translation.llm_utils import build_prompt_with_glossary


@pytest.fixture
def repo(app_ctx):
    from db.repositories.translation import TranslationRepository

    return TranslationRepository()


def _prompt(entries, line):
    return build_prompt_with_glossary("Translate:", entries, [line])


def test_a_pending_global_suggestion_never_reaches_the_prompt(repo):
    from translator.manager import _load_glossary_entries

    repo.add_glossary_entry(
        series_id=None, source_term="Kijin", target_term="Oni-Mensch", approved=0
    )

    entries = _load_glossary_entries(None, "de")
    assert "Oni-Mensch" not in _prompt(entries, "The Kijin are here.")


def test_a_pending_series_suggestion_never_reaches_the_prompt(repo):
    from translator.manager import _load_glossary_entries

    repo.add_glossary_entry(series_id=7, source_term="Kijin", target_term="Oni-Mensch", approved=0)

    entries = _load_glossary_entries(7, "de")
    assert "Oni-Mensch" not in _prompt(entries, "The Kijin are here.")


def test_an_approved_entry_reaches_the_prompt(repo):
    from translator.manager import _load_glossary_entries

    repo.add_glossary_entry(series_id=None, source_term="Demon Lord", target_term="Dämonenfürst")

    entries = _load_glossary_entries(None, "de")
    assert "Dämonenfürst" in _prompt(entries, "The Demon Lord awakens.")


def test_an_entry_for_another_target_language_is_not_loaded(repo):
    from translator.manager import _load_glossary_entries

    repo.add_glossary_entry(
        series_id=None, source_term="Demon Lord", target_term="Dämonenfürst", target_language="de"
    )

    assert not _load_glossary_entries(None, "fr")
    assert not _load_glossary_entries(7, "fr")
    assert _load_glossary_entries(7, "de")


def test_pending_entries_are_not_handed_to_any_backend(repo):
    # DeepL and Google build their native glossaries straight from these
    # entries without looking at ``approved``; the filter has to sit here.
    from translator.manager import _load_glossary_entries

    repo.add_glossary_entry(
        series_id=None, source_term="Kijin", target_term="Oni-Mensch", approved=0
    )
    repo.add_glossary_entry(series_id=7, source_term="Ogre", target_term="Oger", approved=0)
    repo.add_glossary_entry(series_id=None, source_term="Demon Lord", target_term="Dämonenfürst")

    for series_id in (None, 7):
        terms = {e["source_term"] for e in _load_glossary_entries(series_id, "de") or []}
        assert terms == {"Demon Lord"}
