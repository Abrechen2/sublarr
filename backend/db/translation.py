"""Translation config, glossary, preset, and backend stats operations -- delegating to SQLAlchemy repository."""

from typing import Optional

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

def add_glossary_entry(series_id: int, source_term: str, target_term: str, notes: str = "") -> int:
    """Add a new glossary entry for a series. Returns the entry ID."""
    return _get_repo().add_glossary_entry(series_id, source_term, target_term, notes)


def get_glossary_entries(series_id: int) -> list:
    """Get all glossary entries for a series."""
    return _get_repo().get_glossary_entries(series_id)


def get_glossary_for_series(series_id: int) -> list:
    """Get glossary entries for a series, optimized for translation pipeline."""
    return _get_repo().get_glossary_for_series(series_id)


def get_glossary_entry(entry_id: int) -> Optional[dict]:
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


def search_glossary_terms(series_id: int, query: str) -> list:
    """Search glossary entries by source or target term (case-insensitive)."""
    return _get_repo().search_glossary_terms(series_id, query)


# --- Prompt Presets Operations ---

def add_prompt_preset(name: str, prompt_template: str, is_default: bool = False) -> int:
    """Add a new prompt preset. Returns the preset ID."""
    return _get_repo().add_prompt_preset(name, prompt_template, is_default)


def get_prompt_presets() -> list:
    """Get all prompt presets."""
    return _get_repo().get_prompt_presets()


def get_prompt_preset(preset_id: int) -> Optional[dict]:
    """Get a single prompt preset by ID."""
    return _get_repo().get_prompt_preset(preset_id)


def get_default_prompt_preset() -> Optional[dict]:
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


def get_backend_stat(backend_name: str) -> Optional[dict]:
    """Get stats for a single translation backend."""
    return _get_repo().get_backend_stat(backend_name)


def reset_backend_stats(backend_name: str) -> bool:
    """Reset stats for a backend. Returns True if a row was deleted."""
    return _get_repo().reset_backend_stats(backend_name)
