"""Translation config, glossary, prompt preset, and backend stats repository.

Replaces the raw sqlite3 queries in db/translation.py with SQLAlchemy ORM
operations. Return types match the existing functions exactly.

The backend_stats functions preserve the weighted running average logic
for avg_response_time_ms exactly as in the original module.
"""

import logging

from sqlalchemy import func, select

from db.models.translation import (
    GlossaryEntry,
    PromptPreset,
    TranslationBackendStats,
    TranslationConfigHistory,
)
from db.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class TranslationRepository(BaseRepository):
    """Repository for translation-related table operations."""

    # ---- Translation Config History ------------------------------------------

    def record_translation_config(
        self, config_hash: str, ollama_model: str, prompt_template: str, target_language: str
    ):
        """Record or update a translation config hash."""
        now = self._now()

        existing = self.session.execute(
            select(TranslationConfigHistory).where(
                TranslationConfigHistory.config_hash == config_hash
            )
        ).scalar_one_or_none()

        if existing:
            existing.last_used_at = now
        else:
            entry = TranslationConfigHistory(
                config_hash=config_hash,
                ollama_model=ollama_model,
                prompt_template=prompt_template,
                target_language=target_language,
                first_used_at=now,
                last_used_at=now,
            )
            self.session.add(entry)
        self._commit()

    def get_translation_config_history(self) -> list[dict]:
        """Get translation config history entries."""
        stmt = select(TranslationConfigHistory).order_by(
            TranslationConfigHistory.last_used_at.desc()
        )
        entries = self.session.execute(stmt).scalars().all()
        return [self._to_dict(e) for e in entries]

    # ---- Glossary Operations -------------------------------------------------

    def add_glossary_entry(
        self, series_id: int | None, source_term: str, target_term: str, notes: str = ""
    ) -> int:
        """Add a new glossary entry. Returns the entry ID.

        When series_id is None, creates a global glossary entry.
        """
        now = self._now()
        entry = GlossaryEntry(
            series_id=series_id,
            source_term=source_term.strip(),
            target_term=target_term.strip(),
            notes=notes.strip(),
            created_at=now,
            updated_at=now,
        )
        self.session.add(entry)
        self._commit()
        return entry.id

    def get_glossary_entries(self, series_id: int) -> list[dict]:
        """Get all glossary entries for a series."""
        stmt = (
            select(GlossaryEntry)
            .where(GlossaryEntry.series_id == series_id)
            .order_by(GlossaryEntry.source_term.asc(), GlossaryEntry.created_at.asc())
        )
        entries = self.session.execute(stmt).scalars().all()
        return [self._to_dict(e) for e in entries]

    def get_glossary_for_series(self, series_id: int) -> list[dict]:
        """Get glossary entries for a series, optimized for translation pipeline.

        Returns:
            List of {source_term, target_term} dicts, limited to 15 most recent.
        """
        stmt = (
            select(GlossaryEntry.source_term, GlossaryEntry.target_term)
            .where(GlossaryEntry.series_id == series_id)
            .order_by(GlossaryEntry.updated_at.desc(), GlossaryEntry.created_at.desc())
            .limit(15)
        )
        rows = self.session.execute(stmt).all()
        return [{"source_term": r.source_term, "target_term": r.target_term} for r in rows]

    def get_global_glossary(self) -> list[dict]:
        """Get all global glossary entries (series_id IS NULL).

        Returns:
            List of glossary entry dicts, ordered by source_term ascending.
        """
        stmt = (
            select(GlossaryEntry)
            .where(GlossaryEntry.series_id.is_(None))
            .order_by(GlossaryEntry.source_term.asc())
        )
        entries = self.session.execute(stmt).scalars().all()
        return [self._to_dict(e) for e in entries]

    def get_merged_glossary_for_series(self, series_id: int) -> list[dict]:
        """Get merged glossary entries for a series (global + per-series).

        Per-series entries override global entries with the same source_term
        (case-insensitive). Limited to 30 most recent entries per source.

        Returns:
            List of {source_term, target_term} dicts, max 30 entries.
        """
        # Global entries
        global_stmt = (
            select(GlossaryEntry.source_term, GlossaryEntry.target_term)
            .where(GlossaryEntry.series_id.is_(None))
            .order_by(GlossaryEntry.updated_at.desc())
            .limit(30)
        )
        global_rows = self.session.execute(global_stmt).all()
        global_dict = {
            r.source_term.lower(): {"source_term": r.source_term, "target_term": r.target_term}
            for r in global_rows
        }

        # Series-specific entries (override global on same source_term)
        series_stmt = (
            select(GlossaryEntry.source_term, GlossaryEntry.target_term)
            .where(GlossaryEntry.series_id == series_id)
            .order_by(GlossaryEntry.updated_at.desc())
            .limit(30)
        )
        series_rows = self.session.execute(series_stmt).all()
        series_dict = {
            r.source_term.lower(): {"source_term": r.source_term, "target_term": r.target_term}
            for r in series_rows
        }

        # Merge: global first, series overrides
        merged = {**global_dict, **series_dict}
        return list(merged.values())[:30]

    def get_glossary_entry(self, entry_id: int) -> dict | None:
        """Get a single glossary entry by ID."""
        entry = self.session.get(GlossaryEntry, entry_id)
        return self._to_dict(entry)

    def update_glossary_entry(
        self, entry_id: int, source_term: str = None, target_term: str = None, notes: str = None
    ) -> bool:
        """Update a glossary entry. Returns True if updated."""
        entry = self.session.get(GlossaryEntry, entry_id)
        if entry is None:
            return False

        updated = False
        if source_term is not None:
            entry.source_term = source_term.strip()
            updated = True
        if target_term is not None:
            entry.target_term = target_term.strip()
            updated = True
        if notes is not None:
            entry.notes = notes.strip()
            updated = True

        if not updated:
            return False

        entry.updated_at = self._now()
        self._commit()
        return True

    def delete_glossary_entry(self, entry_id: int) -> bool:
        """Delete a glossary entry. Returns True if deleted."""
        entry = self.session.get(GlossaryEntry, entry_id)
        if entry is None:
            return False
        self.session.delete(entry)
        self._commit()
        return True

    def delete_glossary_entries_for_series(self, series_id: int) -> int:
        """Delete all glossary entries for a series. Returns count deleted."""
        from sqlalchemy import delete as sa_delete

        result = self.session.execute(
            sa_delete(GlossaryEntry).where(GlossaryEntry.series_id == series_id)
        )
        self._commit()
        return result.rowcount

    def search_glossary_terms(self, series_id: int | None, query: str) -> list[dict]:
        """Search glossary entries by source or target term (case-insensitive).

        When series_id is None, searches global entries only.
        When series_id is an int, searches per-series entries only.
        """
        search_pattern = f"%{query}%"

        if series_id is None:
            series_filter = GlossaryEntry.series_id.is_(None)
        else:
            series_filter = GlossaryEntry.series_id == series_id

        stmt = (
            select(GlossaryEntry)
            .where(
                series_filter,
                (
                    GlossaryEntry.source_term.like(search_pattern)
                    | GlossaryEntry.target_term.like(search_pattern)
                ),
            )
            .order_by(GlossaryEntry.source_term.asc())
        )
        entries = self.session.execute(stmt).scalars().all()
        return [self._to_dict(e) for e in entries]

    # ---- Prompt Presets Operations -------------------------------------------

    def add_prompt_preset(self, name: str, prompt_template: str, is_default: bool = False) -> int:
        """Add a new prompt preset. Returns the preset ID."""
        now = self._now()

        with self.batch():
            # If this is set as default, unset other defaults
            if is_default:
                self._unset_default_presets()

            entry = PromptPreset(
                name=name.strip(),
                prompt_template=prompt_template.strip(),
                is_default=1 if is_default else 0,
                created_at=now,
                updated_at=now,
            )
            self.session.add(entry)

        return entry.id

    def get_prompt_presets(self) -> list[dict]:
        """Get all prompt presets."""
        stmt = select(PromptPreset).order_by(
            PromptPreset.is_default.desc(), PromptPreset.name.asc()
        )
        entries = self.session.execute(stmt).scalars().all()
        return [self._to_dict(e) for e in entries]

    def get_prompt_preset(self, preset_id: int) -> dict | None:
        """Get a single prompt preset by ID."""
        entry = self.session.get(PromptPreset, preset_id)
        return self._to_dict(entry)

    def get_default_prompt_preset(self) -> dict | None:
        """Get the default prompt preset."""
        stmt = select(PromptPreset).where(PromptPreset.is_default == 1).limit(1)
        entry = self.session.execute(stmt).scalar_one_or_none()
        return self._to_dict(entry)

    def update_prompt_preset(
        self, preset_id: int, name: str = None, prompt_template: str = None, is_default: bool = None
    ) -> bool:
        """Update a prompt preset. Returns True if updated."""
        entry = self.session.get(PromptPreset, preset_id)
        if entry is None:
            return False

        updated = False
        if name is not None:
            entry.name = name.strip()
            updated = True
        if prompt_template is not None:
            entry.prompt_template = prompt_template.strip()
            updated = True
        if is_default is not None:
            entry.is_default = 1 if is_default else 0
            updated = True

        if not updated:
            return False

        entry.updated_at = self._now()

        with self.batch():
            # If setting as default, unset other defaults atomically
            if is_default:
                self._unset_default_presets(exclude_id=preset_id)
            # entry is already attached to session, commit via batch

        return True

    def delete_prompt_preset(self, preset_id: int) -> bool:
        """Delete a prompt preset. Returns True if deleted.

        Cannot delete if it's the only preset.
        """
        count = self.session.execute(select(func.count()).select_from(PromptPreset)).scalar() or 0

        if count <= 1:
            return False

        entry = self.session.get(PromptPreset, preset_id)
        if entry is None:
            return False

        self.session.delete(entry)
        self._commit()
        return True

    def _unset_default_presets(self, exclude_id: int = None):
        """Set is_default=0 for all presets, optionally excluding one.

        Does NOT commit — callers are responsible for committing (use batch()).
        """
        stmt = select(PromptPreset).where(PromptPreset.is_default == 1)
        if exclude_id is not None:
            stmt = stmt.where(PromptPreset.id != exclude_id)
        presets = self.session.execute(stmt).scalars().all()
        for p in presets:
            p.is_default = 0

    # ---- Translation Backend Stats Operations --------------------------------

    def record_backend_success(
        self, backend_name: str, response_time_ms: float, characters_used: int
    ):
        """Record a successful translation for a backend.

        Uses upsert logic. Updates running average response time using
        weighted formula: (old_avg * (n-1) + new) / n.
        """
        now = self._now()
        existing = self.session.get(TranslationBackendStats, backend_name)

        if existing:
            total = existing.total_requests or 0
            old_avg = existing.avg_response_time_ms or 0
            new_total = total + 1
            new_avg = (
                (old_avg * total + response_time_ms) / new_total
                if new_total > 0
                else response_time_ms
            )

            existing.total_requests = new_total
            existing.successful_translations = (existing.successful_translations or 0) + 1
            existing.total_characters = (existing.total_characters or 0) + characters_used
            existing.avg_response_time_ms = new_avg
            existing.last_response_time_ms = response_time_ms
            existing.last_success_at = now
            existing.consecutive_failures = 0
            existing.updated_at = now
        else:
            entry = TranslationBackendStats(
                backend_name=backend_name,
                total_requests=1,
                successful_translations=1,
                total_characters=characters_used,
                avg_response_time_ms=response_time_ms,
                last_response_time_ms=response_time_ms,
                last_success_at=now,
                consecutive_failures=0,
                updated_at=now,
            )
            self.session.add(entry)
        self._commit()

    def record_backend_failure(self, backend_name: str, error_msg: str):
        """Record a failed translation for a backend.

        Uses upsert logic. Increments consecutive failures and records error.
        """
        now = self._now()
        existing = self.session.get(TranslationBackendStats, backend_name)

        if existing:
            existing.total_requests = (existing.total_requests or 0) + 1
            existing.failed_translations = (existing.failed_translations or 0) + 1
            existing.consecutive_failures = (existing.consecutive_failures or 0) + 1
            existing.last_failure_at = now
            existing.last_error = error_msg[:500]
            existing.updated_at = now
        else:
            entry = TranslationBackendStats(
                backend_name=backend_name,
                total_requests=1,
                failed_translations=1,
                consecutive_failures=1,
                last_failure_at=now,
                last_error=error_msg[:500],
                updated_at=now,
            )
            self.session.add(entry)
        self._commit()

    def get_backend_stats(self) -> list[dict]:
        """Get stats for all translation backends."""
        stmt = select(TranslationBackendStats).order_by(TranslationBackendStats.backend_name.asc())
        entries = self.session.execute(stmt).scalars().all()
        return [self._to_dict(e) for e in entries]

    def get_backend_stat(self, backend_name: str) -> dict | None:
        """Get stats for a single translation backend."""
        entry = self.session.get(TranslationBackendStats, backend_name)
        return self._to_dict(entry)

    def reset_backend_stats(self, backend_name: str) -> bool:
        """Reset stats for a backend. Returns True if a row was deleted."""
        entry = self.session.get(TranslationBackendStats, backend_name)
        if entry is None:
            return False
        self.session.delete(entry)
        self._commit()
        return True

    # ---- Translation Memory Cache Operations ---------------------------------

    @staticmethod
    def _normalize_text(text: str) -> str:
        """Normalize source text for cache key computation.

        Strips leading/trailing whitespace, lowercases, and collapses internal
        whitespace sequences to a single space.
        """
        import re as _re

        return _re.sub(r"\s+", " ", text.strip().lower())

    @staticmethod
    def _hash_text(normalized_text: str) -> str:
        """Return SHA-256 hex digest of a normalized text string."""
        import hashlib

        return hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()

    def lookup_translation_cache(
        self,
        source_lang: str,
        target_lang: str,
        source_text: str,
        similarity_threshold: float = 1.0,
    ) -> str | None:
        """Look up a translation in the memory cache.

        Performs an exact hash match first. When similarity_threshold < 1.0,
        falls back to a difflib similarity scan over all entries for the same
        language pair.

        Args:
            source_lang: ISO 639-1 source language code.
            target_lang: ISO 639-1 target language code.
            source_text: Raw source text (will be normalized internally).
            similarity_threshold: Minimum SequenceMatcher ratio (0.0-1.0).
                                  1.0 means exact match only (default).

        Returns:
            Cached translated text, or None if no match found.
        """
        from db.models.translation import TranslationMemory

        normalized = self._normalize_text(source_text)
        text_hash = self._hash_text(normalized)

        # --- Exact match via hash index ---
        exact = self.session.execute(
            select(TranslationMemory.translated_text).where(
                TranslationMemory.source_lang == source_lang,
                TranslationMemory.target_lang == target_lang,
                TranslationMemory.text_hash == text_hash,
            )
        ).scalar_one_or_none()

        if exact is not None:
            return exact

        # --- Optional similarity scan ---
        if similarity_threshold >= 1.0:
            return None

        import difflib

        candidates = self.session.execute(
            select(
                TranslationMemory.source_text_normalized,
                TranslationMemory.translated_text,
            ).where(
                TranslationMemory.source_lang == source_lang,
                TranslationMemory.target_lang == target_lang,
            )
        ).all()

        best_ratio = 0.0
        best_translation: str | None = None

        for row in candidates:
            ratio = difflib.SequenceMatcher(None, normalized, row.source_text_normalized).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_translation = row.translated_text

        if best_ratio >= similarity_threshold:
            return best_translation

        return None

    def store_translation_cache(
        self,
        source_lang: str,
        target_lang: str,
        source_text: str,
        translated_text: str,
    ) -> None:
        """Store a translation in the memory cache (upsert by unique key).

        Args:
            source_lang: ISO 639-1 source language code.
            target_lang: ISO 639-1 target language code.
            source_text: Raw source text (normalized internally).
            translated_text: The translated output to cache.
        """
        from db.models.translation import TranslationMemory

        normalized = self._normalize_text(source_text)
        text_hash = self._hash_text(normalized)
        now = self._now()

        existing = self.session.execute(
            select(TranslationMemory).where(
                TranslationMemory.source_lang == source_lang,
                TranslationMemory.target_lang == target_lang,
                TranslationMemory.text_hash == text_hash,
            )
        ).scalar_one_or_none()

        if existing:
            # Update the cached translation (the source text remains identical)
            existing.translated_text = translated_text
        else:
            entry = TranslationMemory(
                source_lang=source_lang,
                target_lang=target_lang,
                source_text_normalized=normalized,
                text_hash=text_hash,
                translated_text=translated_text,
                created_at=now,
            )
            self.session.add(entry)

        self._commit()

    def clear_translation_cache(self) -> int:
        """Delete all entries from the translation memory cache.

        Returns:
            Number of rows deleted.
        """
        from sqlalchemy import delete as sa_delete

        from db.models.translation import TranslationMemory

        result = self.session.execute(sa_delete(TranslationMemory))
        self._commit()
        return result.rowcount

    def get_translation_cache_stats(self) -> dict:
        """Return basic statistics for the translation memory cache.

        Returns:
            Dict with "entries" count.
        """
        from db.models.translation import TranslationMemory

        count = (
            self.session.execute(select(func.count()).select_from(TranslationMemory)).scalar() or 0
        )
        return {"entries": count}
