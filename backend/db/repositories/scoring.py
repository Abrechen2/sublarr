"""Scoring weights and provider modifier repository using SQLAlchemy ORM.

Replaces the raw sqlite3 queries in db/scoring.py with SQLAlchemy ORM
operations. Return types match the existing functions exactly.
"""

import logging

from sqlalchemy import select, delete

from db.models.providers import ScoringWeights, ProviderScoreModifier
from db.repositories.base import BaseRepository

logger = logging.getLogger(__name__)

# Default weights used when no DB overrides exist (same as db/scoring.py)
_DEFAULT_EPISODE_WEIGHTS = {
    "hash": 359,
    "series": 180,
    "year": 90,
    "season": 30,
    "episode": 30,
    "release_group": 14,
    "source": 7,
    "audio_codec": 3,
    "resolution": 2,
    "hearing_impaired": 1,
    "format_bonus": 50,
}

_DEFAULT_MOVIE_WEIGHTS = {
    "hash": 119,
    "title": 60,
    "year": 30,
    "release_group": 13,
    "source": 7,
    "audio_codec": 3,
    "resolution": 2,
    "hearing_impaired": 1,
    "format_bonus": 50,
}


class ScoringRepository(BaseRepository):
    """Repository for scoring_weights and provider_score_modifiers tables."""

    # ---- Scoring weights CRUD ------------------------------------------------

    def get_scoring_weights(self, score_type: str) -> dict:
        """Get scoring weight overrides for a given type.

        Returns only the DB overrides (not merged with defaults).

        Returns:
            Dict mapping weight_key -> weight_value. Empty if no overrides.
        """
        stmt = select(ScoringWeights).where(ScoringWeights.score_type == score_type)
        entries = self.session.execute(stmt).scalars().all()
        return {e.weight_key: e.weight_value for e in entries}

    def set_scoring_weights(self, score_type: str, weights_dict: dict) -> None:
        """Set scoring weight overrides for a given type.

        Uses merge (INSERT OR REPLACE) for each key-value pair.
        """
        now = self._now()
        for key, value in weights_dict.items():
            # Find existing entry by composite unique (score_type, weight_key)
            existing = self.session.execute(
                select(ScoringWeights).where(
                    ScoringWeights.score_type == score_type,
                    ScoringWeights.weight_key == key,
                )
            ).scalar_one_or_none()

            if existing:
                existing.weight_value = int(value)
                existing.updated_at = now
            else:
                entry = ScoringWeights(
                    score_type=score_type,
                    weight_key=key,
                    weight_value=int(value),
                    updated_at=now,
                )
                self.session.add(entry)
        self._commit()

    def get_all_scoring_weights(self) -> dict:
        """Get all scoring weights with defaults filled in.

        Returns:
            {'episode': {...}, 'movie': {...}} with defaults merged with DB overrides.
        """
        episode_overrides = self.get_scoring_weights("episode")
        movie_overrides = self.get_scoring_weights("movie")

        return {
            "episode": {**_DEFAULT_EPISODE_WEIGHTS, **episode_overrides},
            "movie": {**_DEFAULT_MOVIE_WEIGHTS, **movie_overrides},
        }

    def reset_scoring_weights(self, score_type: str = None) -> None:
        """Delete scoring weight overrides.

        Args:
            score_type: If provided, delete only for this type. If None, delete all.
        """
        if score_type:
            self.session.execute(
                delete(ScoringWeights).where(ScoringWeights.score_type == score_type)
            )
        else:
            self.session.execute(delete(ScoringWeights))
        self._commit()

    # ---- Provider score modifiers CRUD ----------------------------------------

    def get_provider_modifier(self, provider_name: str) -> int:
        """Get the score modifier for a provider.

        Returns:
            Integer modifier (positive = bonus, negative = penalty). 0 if not set.
        """
        entry = self.session.get(ProviderScoreModifier, provider_name)
        if entry is None:
            return 0
        return entry.modifier

    def get_all_provider_modifiers(self) -> dict:
        """Get all provider score modifiers.

        Returns:
            Dict mapping provider_name -> modifier (int).
        """
        stmt = (
            select(ProviderScoreModifier)
            .order_by(ProviderScoreModifier.provider_name)
        )
        entries = self.session.execute(stmt).scalars().all()
        return {e.provider_name: e.modifier for e in entries}

    def set_provider_modifier(self, provider_name: str, modifier: int) -> None:
        """Set or update the score modifier for a provider."""
        now = self._now()
        entry = ProviderScoreModifier(
            provider_name=provider_name,
            modifier=int(modifier),
            updated_at=now,
        )
        self.session.merge(entry)
        self._commit()

    def delete_provider_modifier(self, provider_name: str) -> None:
        """Delete the score modifier for a provider."""
        entry = self.session.get(ProviderScoreModifier, provider_name)
        if entry:
            self.session.delete(entry)
            self._commit()
