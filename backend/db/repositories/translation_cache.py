"""Translation-memory cache mixin for TranslationRepository.

Extracted from db/repositories/translation.py. Provides exact-hash and
fuzzy-match translation-cache lookup, store, clear and stats. Lives in
a mixin so TranslationRepository stays a single class with one
inheritance chain (mixed in via multiple inheritance alongside
BaseRepository).
"""

import logging

from sqlalchemy import func, select

logger = logging.getLogger(__name__)

# Fuzzy scan performance guard: skip similarity scan if cache is too large
_FUZZY_SCAN_LIMIT = 5_000


class _TranslationCacheMixin:
    """Translation-memory cache methods mixed into TranslationRepository."""

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

        # Guard: fuzzy scan is O(N) — skip if cache is too large
        count = (
            self.session.execute(
                select(func.count())
                .select_from(TranslationMemory)
                .where(
                    TranslationMemory.source_lang == source_lang,
                    TranslationMemory.target_lang == target_lang,
                )
            ).scalar()
            or 0
        )
        if count > _FUZZY_SCAN_LIMIT:
            logger.warning(
                "Translation memory too large for fuzzy scan (%d rows for %s→%s); skipping",
                count,
                source_lang,
                target_lang,
            )
            return None

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
        backend: str | None = None,
    ) -> None:
        """Store a translation in the memory cache (upsert by unique key).

        Args:
            source_lang: ISO 639-1 source language code.
            target_lang: ISO 639-1 target language code.
            source_text: Raw source text (normalized internally).
            translated_text: The translated output to cache.
            backend: Optional backend identifier that produced this translation
                (e.g. ``ollama``, ``claude``). Enables backend-filtered purge.
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
            if backend:
                existing.backend = backend
        else:
            entry = TranslationMemory(
                source_lang=source_lang,
                target_lang=target_lang,
                source_text_normalized=normalized,
                text_hash=text_hash,
                translated_text=translated_text,
                backend=backend,
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
