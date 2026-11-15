"""Bundled glossary suggestions: offered, never applied on their own.

A fresh install has an empty glossary, and the 2026-11-14 benchmark showed
what that costs: without one, "Demon Lord" came out as two different German
terms in a single episode. The presets are a starting list the user imports
with one click — nothing reaches a prompt until they do (new automations are
opt-in).
"""

from __future__ import annotations

import pytest


@pytest.fixture
def repo(app_ctx):
    from db.repositories.translation import TranslationRepository

    return TranslationRepository()


class TestBundledPresets:
    def test_anime_presets_exist_for_both_directions(self):
        from glossary_presets import load_bundled_presets

        pairs = {(p["source_language"], p["target_language"]) for p in load_bundled_presets()}
        assert {("en", "de"), ("de", "en")} <= pairs

    def test_every_entry_has_both_terms(self):
        from glossary_presets import load_bundled_presets

        for preset in load_bundled_presets():
            assert preset["entries"], preset["id"]
            for entry in preset["entries"]:
                assert entry["source_term"].strip() and entry["target_term"].strip()

    def test_familiar_is_not_suggested(self):
        # "familiar" is far more often the adjective ("vertraut") than the
        # summoned creature; the benchmark caught it misfiring.
        from glossary_presets import get_bundled_preset

        terms = {e["source_term"].lower() for e in get_bundled_preset("anime-en-de")["entries"]}
        assert "familiar" not in terms

    def test_nothing_is_in_the_glossary_before_an_import(self, repo):
        from db.translation import get_global_glossary

        assert get_global_glossary() == []


class TestImport:
    def test_import_adds_approved_global_entries_for_the_target_language(self, repo):
        from db.translation import get_global_glossary
        from services.glossary_presets_service import import_preset

        result = import_preset("anime-en-de")

        entries = get_global_glossary()
        assert result["added"] == len(entries) > 0
        assert all(e["series_id"] is None and e["approved"] == 1 for e in entries)
        assert {e["target_language"] for e in entries} == {"de"}

    def test_import_keeps_terms_the_user_already_has(self, repo):
        from db.translation import get_global_glossary
        from services.glossary_presets_service import import_preset

        repo.add_glossary_entry(
            series_id=None, source_term="demon lord", target_term="Dämonenherrscher"
        )

        result = import_preset("anime-en-de")

        demon_lord = [e for e in get_global_glossary() if e["source_term"].lower() == "demon lord"]
        assert [e["target_term"] for e in demon_lord] == ["Dämonenherrscher"]
        assert result["skipped"] >= 1

    def test_a_second_import_adds_nothing(self, repo):
        from services.glossary_presets_service import import_preset

        import_preset("anime-en-de")
        assert import_preset("anime-en-de")["added"] == 0

    def test_a_term_for_another_language_does_not_block_the_import(self, repo):
        from services.glossary_presets_service import import_preset

        repo.add_glossary_entry(
            series_id=None,
            source_term="Demon Lord",
            target_term="Seigneur démon",
            target_language="fr",
        )

        import_preset("anime-en-de")
        from db.translation import get_global_glossary

        assert any(e["target_term"] == "Dämonenfürst" for e in get_global_glossary("de"))

    def test_unknown_preset_raises(self, repo):
        from services.glossary_presets_service import UnknownPresetError, import_preset

        with pytest.raises(UnknownPresetError):
            import_preset("nope")


class TestRoutes:
    def test_list_and_import(self, client):
        listed = client.get("/api/v1/glossary/presets")
        assert listed.status_code == 200
        ids = [p["id"] for p in listed.get_json()["presets"]]
        assert "anime-en-de" in ids

        imported = client.post("/api/v1/glossary/presets/anime-en-de/import")
        assert imported.status_code == 200
        assert imported.get_json()["added"] > 0

    def test_import_of_unknown_preset_is_404(self, client):
        assert client.post("/api/v1/glossary/presets/nope/import").status_code == 404
