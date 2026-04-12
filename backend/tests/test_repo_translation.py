"""Tests for db.repositories.translation.TranslationRepository.

Covers: config history, glossary CRUD, merged glossary, search,
prompt presets, backend stats, translation memory cache.
"""

import pytest

from db.repositories.translation import TranslationRepository


@pytest.fixture
def repo(app_ctx):
    """Create a TranslationRepository instance within app context."""
    return TranslationRepository()


# ---------------------------------------------------------------------------
# Translation Config History
# ---------------------------------------------------------------------------


class TestTranslationConfigHistory:
    def test_record_new_config(self, repo):
        """Recording a new config hash creates a history entry."""
        repo.record_translation_config("hash1", "llama3", "Translate: {text}", "de")

        entries = repo.get_translation_config_history()
        assert len(entries) == 1
        assert entries[0]["config_hash"] == "hash1"
        assert entries[0]["ollama_model"] == "llama3"
        assert entries[0]["prompt_template"] == "Translate: {text}"
        assert entries[0]["target_language"] == "de"

    def test_record_existing_config_updates_last_used(self, repo):
        """Recording the same config hash updates last_used_at, not duplicate."""
        repo.record_translation_config("hash1", "llama3", "prompt", "de")
        first = repo.get_translation_config_history()[0]

        repo.record_translation_config("hash1", "llama3", "prompt", "de")
        entries = repo.get_translation_config_history()

        assert len(entries) == 1
        assert entries[0]["last_used_at"] >= first["last_used_at"]

    def test_multiple_configs_ordered_by_last_used(self, repo):
        """Config history is ordered by last_used_at descending."""
        repo.record_translation_config("older", "m1", "p1", "de")
        repo.record_translation_config("newer", "m2", "p2", "en")

        entries = repo.get_translation_config_history()
        assert len(entries) == 2
        assert entries[0]["config_hash"] == "newer"
        assert entries[1]["config_hash"] == "older"

    def test_empty_config_history(self, repo):
        """Empty history returns an empty list."""
        assert repo.get_translation_config_history() == []


# ---------------------------------------------------------------------------
# Glossary CRUD
# ---------------------------------------------------------------------------


class TestGlossaryCRUD:
    def test_add_and_get_glossary_entry(self, repo):
        """Adding a glossary entry returns its ID and it can be retrieved."""
        entry_id = repo.add_glossary_entry(
            series_id=1,
            source_term=" Naruto ",
            target_term=" Naruto ",
            notes=" main character ",
            term_type="character",
            confidence=0.95,
            approved=1,
        )
        assert isinstance(entry_id, int)

        entry = repo.get_glossary_entry(entry_id)
        assert entry is not None
        assert entry["source_term"] == "Naruto"  # stripped
        assert entry["target_term"] == "Naruto"
        assert entry["notes"] == "main character"
        assert entry["term_type"] == "character"
        assert entry["confidence"] == pytest.approx(0.95)
        assert entry["approved"] == 1
        assert entry["series_id"] == 1

    def test_add_global_glossary_entry(self, repo):
        """Glossary entry with series_id=None is a global entry."""
        entry_id = repo.add_glossary_entry(
            series_id=None,
            source_term="Attack",
            target_term="Angriff",
        )
        entry = repo.get_glossary_entry(entry_id)
        assert entry["series_id"] is None

    def test_get_glossary_entries_for_series(self, repo):
        """Get entries filtered by series_id, ordered by source_term."""
        repo.add_glossary_entry(series_id=1, source_term="Bee", target_term="Biene")
        repo.add_glossary_entry(series_id=1, source_term="Apple", target_term="Apfel")
        repo.add_glossary_entry(series_id=2, source_term="Cat", target_term="Katze")

        entries = repo.get_glossary_entries(series_id=1)
        assert len(entries) == 2
        assert entries[0]["source_term"] == "Apple"
        assert entries[1]["source_term"] == "Bee"

    def test_get_glossary_entry_not_found(self, repo):
        """Getting a non-existent entry returns None."""
        assert repo.get_glossary_entry(999) is None

    def test_update_glossary_entry_all_fields(self, repo):
        """Updating all fields on a glossary entry succeeds."""
        entry_id = repo.add_glossary_entry(
            series_id=1, source_term="Old", target_term="Alt"
        )
        result = repo.update_glossary_entry(
            entry_id,
            source_term=" New ",
            target_term=" Neu ",
            notes=" updated ",
            term_type="place",
            confidence=0.5,
            approved=0,
        )
        assert result is True

        entry = repo.get_glossary_entry(entry_id)
        assert entry["source_term"] == "New"
        assert entry["target_term"] == "Neu"
        assert entry["notes"] == "updated"
        assert entry["term_type"] == "place"
        assert entry["confidence"] == pytest.approx(0.5)
        assert entry["approved"] == 0

    def test_update_glossary_entry_partial(self, repo):
        """Updating only source_term leaves other fields unchanged."""
        entry_id = repo.add_glossary_entry(
            series_id=1,
            source_term="Hello",
            target_term="Hallo",
            notes="greeting",
            term_type="other",
        )
        repo.update_glossary_entry(entry_id, source_term="Hi")

        entry = repo.get_glossary_entry(entry_id)
        assert entry["source_term"] == "Hi"
        assert entry["target_term"] == "Hallo"
        assert entry["notes"] == "greeting"

    def test_update_glossary_entry_clear_confidence(self, repo):
        """Passing confidence=None explicitly clears confidence."""
        entry_id = repo.add_glossary_entry(
            series_id=1,
            source_term="X",
            target_term="Y",
            confidence=0.9,
        )
        repo.update_glossary_entry(entry_id, confidence=None)
        entry = repo.get_glossary_entry(entry_id)
        assert entry["confidence"] is None

    def test_update_glossary_entry_no_changes(self, repo):
        """Calling update with no fields returns False."""
        entry_id = repo.add_glossary_entry(
            series_id=1, source_term="X", target_term="Y"
        )
        # All kwargs at their default sentinel values -> no update
        result = repo.update_glossary_entry(entry_id)
        assert result is False

    def test_update_glossary_entry_not_found(self, repo):
        """Updating a non-existent entry returns False."""
        assert repo.update_glossary_entry(999, source_term="X") is False

    def test_delete_glossary_entry(self, repo):
        """Deleting an entry removes it from the database."""
        entry_id = repo.add_glossary_entry(
            series_id=1, source_term="Del", target_term="Weg"
        )
        assert repo.delete_glossary_entry(entry_id) is True
        assert repo.get_glossary_entry(entry_id) is None

    def test_delete_glossary_entry_not_found(self, repo):
        """Deleting a non-existent entry returns False."""
        assert repo.delete_glossary_entry(999) is False

    def test_delete_glossary_entries_for_series(self, repo):
        """Bulk delete removes all entries for a series."""
        repo.add_glossary_entry(series_id=10, source_term="A", target_term="A")
        repo.add_glossary_entry(series_id=10, source_term="B", target_term="B")
        repo.add_glossary_entry(series_id=20, source_term="C", target_term="C")

        deleted = repo.delete_glossary_entries_for_series(10)
        assert deleted == 2
        assert len(repo.get_glossary_entries(10)) == 0
        assert len(repo.get_glossary_entries(20)) == 1

    def test_delete_glossary_entries_for_series_none_exist(self, repo):
        """Bulk delete on a series with no entries returns 0."""
        assert repo.delete_glossary_entries_for_series(999) == 0


# ---------------------------------------------------------------------------
# Glossary for Translation Pipeline
# ---------------------------------------------------------------------------


class TestGlossaryForSeries:
    def test_get_glossary_for_series_limited(self, repo):
        """get_glossary_for_series returns max 15 entries."""
        for i in range(20):
            repo.add_glossary_entry(
                series_id=1, source_term=f"term{i:02d}", target_term=f"ziel{i:02d}"
            )
        result = repo.get_glossary_for_series(1)
        assert len(result) == 15
        # Should have source_term and target_term keys only
        assert set(result[0].keys()) == {"source_term", "target_term"}

    def test_get_glossary_for_series_empty(self, repo):
        """get_glossary_for_series returns empty list for unknown series."""
        assert repo.get_glossary_for_series(999) == []


# ---------------------------------------------------------------------------
# Global Glossary
# ---------------------------------------------------------------------------


class TestGlobalGlossary:
    def test_get_global_glossary(self, repo):
        """get_global_glossary returns only entries with series_id=None."""
        repo.add_glossary_entry(series_id=None, source_term="Global", target_term="Weltweit")
        repo.add_glossary_entry(series_id=1, source_term="Local", target_term="Lokal")

        entries = repo.get_global_glossary()
        assert len(entries) == 1
        assert entries[0]["source_term"] == "Global"
        assert entries[0]["series_id"] is None

    def test_get_global_glossary_empty(self, repo):
        """Empty global glossary returns empty list."""
        assert repo.get_global_glossary() == []


# ---------------------------------------------------------------------------
# Merged Glossary
# ---------------------------------------------------------------------------


class TestMergedGlossary:
    def test_merged_glossary_global_only(self, repo):
        """Merged glossary with no series entries returns global entries."""
        repo.add_glossary_entry(series_id=None, source_term="Hello", target_term="Hallo")
        result = repo.get_merged_glossary_for_series(1)
        assert len(result) == 1
        assert result[0]["source_term"] == "Hello"

    def test_merged_glossary_series_overrides_global(self, repo):
        """Series entry overrides global entry with same source_term."""
        repo.add_glossary_entry(
            series_id=None, source_term="Attack", target_term="Angriff"
        )
        repo.add_glossary_entry(
            series_id=1, source_term="Attack", target_term="Attacke"
        )

        result = repo.get_merged_glossary_for_series(1)
        assert len(result) == 1
        assert result[0]["target_term"] == "Attacke"

    def test_merged_glossary_case_insensitive_override(self, repo):
        """Override matching is case-insensitive on source_term."""
        repo.add_glossary_entry(
            series_id=None, source_term="HELLO", target_term="Hallo"
        )
        repo.add_glossary_entry(
            series_id=1, source_term="hello", target_term="Hi"
        )

        result = repo.get_merged_glossary_for_series(1)
        assert len(result) == 1
        assert result[0]["target_term"] == "Hi"

    def test_merged_glossary_combined(self, repo):
        """Merged glossary combines global and series entries."""
        repo.add_glossary_entry(
            series_id=None, source_term="GlobalOnly", target_term="NurGlobal"
        )
        repo.add_glossary_entry(
            series_id=1, source_term="SeriesOnly", target_term="NurSerie"
        )

        result = repo.get_merged_glossary_for_series(1)
        terms = {r["source_term"] for r in result}
        assert "GlobalOnly" in terms
        assert "SeriesOnly" in terms

    def test_merged_glossary_max_30(self, repo):
        """Merged glossary returns at most 30 entries."""
        for i in range(20):
            repo.add_glossary_entry(
                series_id=None, source_term=f"global{i:02d}", target_term=f"g{i:02d}"
            )
        for i in range(20):
            repo.add_glossary_entry(
                series_id=1, source_term=f"series{i:02d}", target_term=f"s{i:02d}"
            )

        result = repo.get_merged_glossary_for_series(1)
        assert len(result) <= 30


# ---------------------------------------------------------------------------
# Glossary Search
# ---------------------------------------------------------------------------


class TestGlossarySearch:
    def test_search_by_source_term(self, repo):
        """Search matches source_term substring (case-insensitive in SQLite)."""
        repo.add_glossary_entry(series_id=1, source_term="Naruto", target_term="Naruto")
        repo.add_glossary_entry(series_id=1, source_term="Sasuke", target_term="Sasuke")

        results = repo.search_glossary_terms(series_id=1, query="naru")
        assert len(results) == 1
        assert results[0]["source_term"] == "Naruto"

    def test_search_by_target_term(self, repo):
        """Search matches target_term substring."""
        repo.add_glossary_entry(
            series_id=1, source_term="Fire", target_term="Feuer"
        )
        results = repo.search_glossary_terms(series_id=1, query="euer")
        assert len(results) == 1
        assert results[0]["target_term"] == "Feuer"

    def test_search_global_entries(self, repo):
        """Search with series_id=None searches global entries."""
        repo.add_glossary_entry(
            series_id=None, source_term="GlobalTerm", target_term="GlobalZiel"
        )
        repo.add_glossary_entry(
            series_id=1, source_term="GlobalTerm", target_term="SeriesZiel"
        )

        results = repo.search_glossary_terms(series_id=None, query="Global")
        assert len(results) == 1
        assert results[0]["series_id"] is None

    def test_search_no_results(self, repo):
        """Search with no matches returns empty list."""
        repo.add_glossary_entry(series_id=1, source_term="Cat", target_term="Katze")
        assert repo.search_glossary_terms(series_id=1, query="zzz") == []


# ---------------------------------------------------------------------------
# Prompt Presets
# ---------------------------------------------------------------------------


class TestPromptPresets:
    def test_add_and_get_preset(self, repo):
        """Adding a preset returns its ID and it can be retrieved."""
        pid = repo.add_prompt_preset(
            name=" Standard ", prompt_template=" Translate: {text} ", is_default=False
        )
        assert isinstance(pid, int)

        preset = repo.get_prompt_preset(pid)
        assert preset["name"] == "Standard"  # stripped
        assert preset["prompt_template"] == "Translate: {text}"
        assert preset["is_default"] == 0

    def test_add_default_preset_unsets_others(self, repo):
        """Setting a new preset as default unsets any previous default."""
        p1 = repo.add_prompt_preset("First", "tpl1", is_default=True)
        p2 = repo.add_prompt_preset("Second", "tpl2", is_default=True)

        first = repo.get_prompt_preset(p1)
        second = repo.get_prompt_preset(p2)
        assert first["is_default"] == 0
        assert second["is_default"] == 1

    def test_get_prompt_presets_ordered(self, repo):
        """Presets are returned with default first, then alphabetical."""
        repo.add_prompt_preset("Zebra", "z", is_default=False)
        repo.add_prompt_preset("Alpha", "a", is_default=True)

        presets = repo.get_prompt_presets()
        assert presets[0]["name"] == "Alpha"  # default first
        assert presets[1]["name"] == "Zebra"

    def test_get_default_prompt_preset(self, repo):
        """get_default_prompt_preset returns the one marked default."""
        repo.add_prompt_preset("NotDefault", "nd", is_default=False)
        repo.add_prompt_preset("Default", "d", is_default=True)

        default = repo.get_default_prompt_preset()
        assert default is not None
        assert default["name"] == "Default"

    def test_get_default_prompt_preset_none(self, repo):
        """get_default_prompt_preset returns None when no default exists."""
        repo.add_prompt_preset("NoDefault", "nd", is_default=False)
        assert repo.get_default_prompt_preset() is None

    def test_get_prompt_preset_not_found(self, repo):
        """Getting a non-existent preset returns None."""
        assert repo.get_prompt_preset(999) is None

    def test_update_prompt_preset(self, repo):
        """Updating a preset changes its fields."""
        pid = repo.add_prompt_preset("Old", "old_tpl", is_default=False)

        result = repo.update_prompt_preset(
            pid, name=" New ", prompt_template=" new_tpl ", is_default=True
        )
        assert result is True

        preset = repo.get_prompt_preset(pid)
        assert preset["name"] == "New"
        assert preset["prompt_template"] == "new_tpl"
        assert preset["is_default"] == 1

    def test_update_prompt_preset_no_changes(self, repo):
        """Calling update with no fields returns False."""
        pid = repo.add_prompt_preset("X", "x")
        assert repo.update_prompt_preset(pid) is False

    def test_update_prompt_preset_not_found(self, repo):
        """Updating a non-existent preset returns False."""
        assert repo.update_prompt_preset(999, name="X") is False

    def test_update_preset_to_default_unsets_others(self, repo):
        """Setting a preset as default via update unsets other defaults."""
        p1 = repo.add_prompt_preset("P1", "t1", is_default=True)
        p2 = repo.add_prompt_preset("P2", "t2", is_default=False)

        repo.update_prompt_preset(p2, is_default=True)

        assert repo.get_prompt_preset(p1)["is_default"] == 0
        assert repo.get_prompt_preset(p2)["is_default"] == 1

    def test_delete_prompt_preset(self, repo):
        """Deleting a preset removes it (when more than one exists)."""
        p1 = repo.add_prompt_preset("A", "a")
        p2 = repo.add_prompt_preset("B", "b")

        assert repo.delete_prompt_preset(p1) is True
        assert repo.get_prompt_preset(p1) is None
        # p2 still exists
        assert repo.get_prompt_preset(p2) is not None

    def test_delete_last_preset_prevented(self, repo):
        """Cannot delete the only remaining preset."""
        pid = repo.add_prompt_preset("Only", "only")
        assert repo.delete_prompt_preset(pid) is False
        assert repo.get_prompt_preset(pid) is not None

    def test_delete_prompt_preset_not_found(self, repo):
        """Deleting a non-existent preset returns False."""
        repo.add_prompt_preset("Exists", "e")  # need at least 2 for deletion to be allowed
        repo.add_prompt_preset("Exists2", "e2")
        assert repo.delete_prompt_preset(999) is False


# ---------------------------------------------------------------------------
# Backend Stats
# ---------------------------------------------------------------------------


class TestBackendStats:
    def test_record_success_new_backend(self, repo):
        """Recording success for a new backend creates an entry."""
        repo.record_backend_success("ollama", 150.0, 500)

        stats = repo.get_backend_stat("ollama")
        assert stats is not None
        assert stats["backend_name"] == "ollama"
        assert stats["total_requests"] == 1
        assert stats["successful_translations"] == 1
        assert stats["total_characters"] == 500
        assert stats["avg_response_time_ms"] == pytest.approx(150.0)
        assert stats["last_response_time_ms"] == pytest.approx(150.0)
        assert stats["consecutive_failures"] == 0

    def test_record_success_existing_backend_weighted_avg(self, repo):
        """Second success updates weighted running average correctly."""
        repo.record_backend_success("ollama", 100.0, 200)
        repo.record_backend_success("ollama", 200.0, 300)

        stats = repo.get_backend_stat("ollama")
        assert stats["total_requests"] == 2
        assert stats["successful_translations"] == 2
        assert stats["total_characters"] == 500
        # Weighted average: (100*1 + 200) / 2 = 150
        assert stats["avg_response_time_ms"] == pytest.approx(150.0)
        assert stats["last_response_time_ms"] == pytest.approx(200.0)

    def test_record_success_resets_consecutive_failures(self, repo):
        """A success after failures resets consecutive_failures to 0."""
        repo.record_backend_failure("ollama", "timeout")
        repo.record_backend_failure("ollama", "timeout")
        repo.record_backend_success("ollama", 100.0, 100)

        stats = repo.get_backend_stat("ollama")
        assert stats["consecutive_failures"] == 0

    def test_record_failure_new_backend(self, repo):
        """Recording failure for a new backend creates an entry."""
        repo.record_backend_failure("deepl", "connection error")

        stats = repo.get_backend_stat("deepl")
        assert stats is not None
        assert stats["total_requests"] == 1
        assert stats["failed_translations"] == 1
        assert stats["consecutive_failures"] == 1
        assert stats["last_error"] == "connection error"

    def test_record_failure_existing_backend(self, repo):
        """Recording failures increments counters correctly."""
        repo.record_backend_failure("deepl", "error 1")
        repo.record_backend_failure("deepl", "error 2")

        stats = repo.get_backend_stat("deepl")
        assert stats["total_requests"] == 2
        assert stats["failed_translations"] == 2
        assert stats["consecutive_failures"] == 2
        assert stats["last_error"] == "error 2"

    def test_record_failure_truncates_long_error(self, repo):
        """Error messages are truncated to 500 characters."""
        long_msg = "x" * 600
        repo.record_backend_failure("test", long_msg)

        stats = repo.get_backend_stat("test")
        assert len(stats["last_error"]) == 500

    def test_get_backend_stats_all(self, repo):
        """get_backend_stats returns all backends, ordered by name."""
        repo.record_backend_success("zebra", 10.0, 10)
        repo.record_backend_success("alpha", 20.0, 20)

        all_stats = repo.get_backend_stats()
        assert len(all_stats) == 2
        assert all_stats[0]["backend_name"] == "alpha"
        assert all_stats[1]["backend_name"] == "zebra"

    def test_get_backend_stat_not_found(self, repo):
        """Getting stats for a non-existent backend returns None."""
        assert repo.get_backend_stat("nonexistent") is None

    def test_reset_backend_stats(self, repo):
        """Resetting stats removes the entry."""
        repo.record_backend_success("ollama", 100.0, 50)
        assert repo.reset_backend_stats("ollama") is True
        assert repo.get_backend_stat("ollama") is None

    def test_reset_backend_stats_not_found(self, repo):
        """Resetting non-existent backend returns False."""
        assert repo.reset_backend_stats("nonexistent") is False

    def test_get_backend_stats_empty(self, repo):
        """get_backend_stats returns empty list when no entries exist."""
        assert repo.get_backend_stats() == []


# ---------------------------------------------------------------------------
# Translation Memory Cache
# ---------------------------------------------------------------------------


class TestTranslationMemoryCache:
    def test_store_and_lookup_exact_match(self, repo):
        """Storing and looking up a translation returns the cached text."""
        repo.store_translation_cache("en", "de", "Hello World", "Hallo Welt")

        result = repo.lookup_translation_cache("en", "de", "Hello World")
        assert result == "Hallo Welt"

    def test_lookup_normalizes_text(self, repo):
        """Lookup normalizes whitespace and case for matching."""
        repo.store_translation_cache("en", "de", "hello world", "Hallo Welt")

        # Extra whitespace and different case should still match
        result = repo.lookup_translation_cache("en", "de", "  Hello   World  ")
        assert result == "Hallo Welt"

    def test_lookup_no_match(self, repo):
        """Lookup returns None when no match exists."""
        result = repo.lookup_translation_cache("en", "de", "Unknown text")
        assert result is None

    def test_lookup_different_language_pair(self, repo):
        """Cache entries are scoped by language pair."""
        repo.store_translation_cache("en", "de", "Hello", "Hallo")

        # Same text, different target language should not match
        result = repo.lookup_translation_cache("en", "fr", "Hello")
        assert result is None

    def test_store_upsert_updates_existing(self, repo):
        """Storing the same text again updates the translation."""
        repo.store_translation_cache("en", "de", "Hello", "Hallo")
        repo.store_translation_cache("en", "de", "Hello", "Hallo (updated)")

        result = repo.lookup_translation_cache("en", "de", "Hello")
        assert result == "Hallo (updated)"

    def test_fuzzy_lookup_below_threshold(self, repo):
        """Fuzzy lookup with low similarity returns None when below threshold."""
        repo.store_translation_cache("en", "de", "The cat sat on the mat", "Die Katze...")

        # Very different text should not match even with low threshold
        result = repo.lookup_translation_cache(
            "en", "de", "XYZ completely different", similarity_threshold=0.8
        )
        assert result is None

    def test_fuzzy_lookup_similar_text(self, repo):
        """Fuzzy lookup finds similar text when threshold is met."""
        repo.store_translation_cache(
            "en", "de", "The cat sat on the mat", "Die Katze sass auf der Matte"
        )

        # Very similar text with a low threshold
        result = repo.lookup_translation_cache(
            "en", "de", "The cat sat on the mat!", similarity_threshold=0.8
        )
        assert result == "Die Katze sass auf der Matte"

    def test_clear_translation_cache(self, repo):
        """Clearing the cache removes all entries."""
        repo.store_translation_cache("en", "de", "A", "B")
        repo.store_translation_cache("en", "de", "C", "D")

        deleted = repo.clear_translation_cache()
        assert deleted == 2

        assert repo.lookup_translation_cache("en", "de", "A") is None

    def test_clear_empty_cache(self, repo):
        """Clearing an empty cache returns 0."""
        assert repo.clear_translation_cache() == 0

    def test_get_translation_cache_stats(self, repo):
        """Cache stats return the correct entry count."""
        assert repo.get_translation_cache_stats() == {"entries": 0}

        repo.store_translation_cache("en", "de", "Hello", "Hallo")
        repo.store_translation_cache("en", "de", "World", "Welt")

        stats = repo.get_translation_cache_stats()
        assert stats["entries"] == 2


# ---------------------------------------------------------------------------
# Static / Utility Methods
# ---------------------------------------------------------------------------


class TestUtilityMethods:
    def test_normalize_text(self):
        """_normalize_text strips, lowercases, and collapses whitespace."""
        assert TranslationRepository._normalize_text("  Hello   World  ") == "hello world"
        assert TranslationRepository._normalize_text("UPPER") == "upper"
        assert TranslationRepository._normalize_text("no\tchange") == "no change"

    def test_hash_text_deterministic(self):
        """_hash_text returns consistent SHA-256 hex digest."""
        h1 = TranslationRepository._hash_text("hello world")
        h2 = TranslationRepository._hash_text("hello world")
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex length

    def test_hash_text_different_inputs(self):
        """Different inputs produce different hashes."""
        h1 = TranslationRepository._hash_text("hello")
        h2 = TranslationRepository._hash_text("world")
        assert h1 != h2
