"""Translation config, glossary, preset, and backend stats operations -- delegating to SQLAlchemy repository."""


from db.repositories.translation import TranslationRepository

_repo = None


def _get_repo():
    global _repo
    if _repo is None:
        _repo = TranslationRepository()
    return _repo


# --- Translation Config History ---

def record_translation_config(config_hash: str, ollama_model: str,
                               prompt_template: str, target_language: str):
    """Record or update a translation config hash."""
    return _get_repo().record_translation_config(
        config_hash, ollama_model, prompt_template, target_language
    )


# --- Glossary Operations ---

def add_glossary_entry(series_id: int | None = None, source_term: str = "",
                       target_term: str = "", notes: str = "") -> int:
    """Add a new glossary entry. Returns the entry ID.

    When series_id is None, creates a global glossary entry.
    """
    return _get_repo().add_glossary_entry(series_id, source_term, target_term, notes)


def get_glossary_entries(series_id: int | None = None) -> list:
    """Get glossary entries. When series_id is None, returns global entries."""
    if series_id is None:
        return get_global_glossary()
    return _get_repo().get_glossary_entries(series_id)


def get_global_glossary() -> list:
    """Get all global glossary entries (series_id IS NULL)."""
    return _get_repo().get_global_glossary()


def get_merged_glossary_for_series(series_id: int) -> list:
    """Get merged glossary entries for a series (global + per-series, series overrides)."""
    return _get_repo().get_merged_glossary_for_series(series_id)


def get_glossary_for_series(series_id: int) -> list:
    """Get glossary entries for a series, optimized for translation pipeline."""
    return _get_repo().get_glossary_for_series(series_id)


def get_glossary_entry(entry_id: int) -> dict | None:
    """Get a single glossary entry by ID."""
    return _get_repo().get_glossary_entry(entry_id)


def update_glossary_entry(entry_id: int, source_term: str = None,
                          target_term: str = None, notes: str = None) -> bool:
    """Update a glossary entry. Returns True if updated."""
    return _get_repo().update_glossary_entry(entry_id, source_term, target_term, notes)


def delete_glossary_entry(entry_id: int) -> bool:
    """Delete a glossary entry. Returns True if deleted."""
    return _get_repo().delete_glossary_entry(entry_id)


def delete_glossary_entries_for_series(series_id: int) -> int:
    """Delete all glossary entries for a series. Returns count deleted."""
    return _get_repo().delete_glossary_entries_for_series(series_id)


def search_glossary_terms(series_id: int | None = None, query: str = "") -> list:
    """Search glossary entries by source or target term (case-insensitive).

    When series_id is None, searches global entries only.
    """
    return _get_repo().search_glossary_terms(series_id, query)


# --- Prompt Presets Operations ---

def add_prompt_preset(name: str, prompt_template: str, is_default: bool = False) -> int:
    """Add a new prompt preset. Returns the preset ID."""
    return _get_repo().add_prompt_preset(name, prompt_template, is_default)


def get_prompt_presets() -> list:
    """Get all prompt presets."""
    return _get_repo().get_prompt_presets()


def get_prompt_preset(preset_id: int) -> dict | None:
    """Get a single prompt preset by ID."""
    return _get_repo().get_prompt_preset(preset_id)


def get_default_prompt_preset() -> dict | None:
    """Get the default prompt preset."""
    return _get_repo().get_default_prompt_preset()


def update_prompt_preset(preset_id: int, name: str = None,
                         prompt_template: str = None, is_default: bool = None) -> bool:
    """Update a prompt preset. Returns True if updated."""
    return _get_repo().update_prompt_preset(preset_id, name, prompt_template, is_default)


def delete_prompt_preset(preset_id: int) -> bool:
    """Delete a prompt preset. Returns True if deleted."""
    return _get_repo().delete_prompt_preset(preset_id)


# --- Translation Backend Stats Operations ---

def record_backend_success(backend_name: str, response_time_ms: float, characters_used: int):
    """Record a successful translation for a backend."""
    return _get_repo().record_backend_success(backend_name, response_time_ms, characters_used)


def record_backend_failure(backend_name: str, error_msg: str):
    """Record a failed translation for a backend."""
    return _get_repo().record_backend_failure(backend_name, error_msg)


def get_backend_stats() -> list:
    """Get stats for all translation backends."""
    return _get_repo().get_backend_stats()


def get_all_backend_stats() -> list:
    """Get stats for all translation backends (alias)."""
    return _get_repo().get_backend_stats()


def get_backend_stat(backend_name: str) -> dict | None:
    """Get stats for a single translation backend."""
    return _get_repo().get_backend_stat(backend_name)


def reset_backend_stats(backend_name: str) -> bool:
    """Reset stats for a backend. Returns True if a row was deleted."""
    return _get_repo().reset_backend_stats(backend_name)


# --- Translation Memory Cache Operations ---

def lookup_translation_cache(
    source_lang: str,
    target_lang: str,
    source_text: str,
    similarity_threshold: float = 1.0,
) -> str | None:
    """Look up a cached translation.

    Args:
        source_lang: ISO 639-1 source language code.
        target_lang: ISO 639-1 target language code.
        source_text: Raw source text (normalized internally).
        similarity_threshold: Minimum ratio for fuzzy match (1.0 = exact only).

    Returns:
        Cached translated text, or None if not found.
    """
    return _get_repo().lookup_translation_cache(
        source_lang, target_lang, source_text, similarity_threshold
    )


def store_translation_cache(
    source_lang: str,
    target_lang: str,
    source_text: str,
    translated_text: str,
) -> None:
    """Store a translation in the persistent memory cache."""
    return _get_repo().store_translation_cache(
        source_lang, target_lang, source_text, translated_text
    )


def clear_translation_cache() -> int:
    """Delete all entries from the translation memory cache.

    Returns:
        Number of rows deleted.
    """
    return _get_repo().clear_translation_cache()


def get_translation_cache_stats() -> dict:
    """Return cache statistics dict with "entries" count."""
    return _get_repo().get_translation_cache_stats()
