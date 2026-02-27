"""Language profiles repository using SQLAlchemy ORM.

Replaces the raw sqlite3 queries in db/profiles.py with SQLAlchemy ORM operations.
Return types match the existing functions exactly. Profile CRUD with cascade to
SeriesLanguageProfile and MovieLanguageProfile.
"""

import json
import logging

from sqlalchemy import delete, func, select

from config import get_settings
from db.models.core import (
    LanguageProfile,
    MovieLanguageProfile,
    SeriesLanguageProfile,
    WantedItem,
)
from db.repositories.base import BaseRepository

logger = logging.getLogger(__name__)

VALID_FORCED_PREFERENCES = ("disabled", "separate", "auto")


class ProfileRepository(BaseRepository):
    """Repository for language_profiles and assignment table operations."""

    # ---- Profile CRUD ----

    def create_profile(self, name: str, source_lang: str, source_name: str,
                       target_langs: list, target_names: list,
                       translation_backend: str = "ollama",
                       fallback_chain: list = None,
                       forced_preference: str = "disabled") -> int:
        """Create a new language profile. Returns the profile ID."""
        if forced_preference not in VALID_FORCED_PREFERENCES:
            raise ValueError(
                f"Invalid forced_preference '{forced_preference}'. "
                f"Must be one of: {VALID_FORCED_PREFERENCES}"
            )
        if fallback_chain is None:
            fallback_chain = [translation_backend]
        now = self._now()

        profile = LanguageProfile(
            name=name,
            source_language=source_lang,
            source_language_name=source_name,
            target_languages_json=json.dumps(target_langs),
            target_language_names_json=json.dumps(target_names),
            translation_backend=translation_backend,
            fallback_chain_json=json.dumps(fallback_chain),
            forced_preference=forced_preference,
            is_default=0,
            created_at=now,
            updated_at=now,
        )
        self.session.add(profile)
        self._commit()
        return profile.id

    def get_profiles(self) -> list:
        """Get all language profiles, default first."""
        stmt = select(LanguageProfile).order_by(
            LanguageProfile.is_default.desc(),
            LanguageProfile.name.asc(),
        )
        rows = self.session.execute(stmt).scalars().all()
        return [self._row_to_profile(r) for r in rows]

    def get_profile(self, profile_id: int) -> dict | None:
        """Get a language profile by ID."""
        profile = self.session.get(LanguageProfile, profile_id)
        if not profile:
            return None
        return self._row_to_profile(profile)

    def get_default_profile(self) -> dict:
        """Get the default language profile."""
        stmt = select(LanguageProfile).where(LanguageProfile.is_default == 1)
        row = self.session.execute(stmt).scalars().first()

        if not row:
            # Fallback: return first profile
            stmt = select(LanguageProfile).order_by(LanguageProfile.id.asc()).limit(1)
            row = self.session.execute(stmt).scalars().first()

        if not row:
            # No profiles at all -- return synthetic default from config
            s = get_settings()
            return {
                "id": 0,
                "name": "Default",
                "source_language": s.source_language,
                "source_language_name": s.source_language_name,
                "target_languages": [s.target_language],
                "target_language_names": [s.target_language_name],
                "is_default": True,
                "translation_backend": "ollama",
                "fallback_chain": ["ollama"],
            }
        return self._row_to_profile(row)

    def update_profile(self, profile_id: int, **fields) -> bool:
        """Update a language profile's fields. Returns True if found."""
        profile = self.session.get(LanguageProfile, profile_id)
        if not profile:
            return False

        allowed = {"name", "source_language", "source_language_name",
                   "target_languages", "target_language_names",
                   "translation_backend", "fallback_chain", "forced_preference"}

        # Validate forced_preference if provided
        if "forced_preference" in fields:
            fp = fields["forced_preference"]
            if fp not in VALID_FORCED_PREFERENCES:
                raise ValueError(
                    f"Invalid forced_preference '{fp}'. "
                    f"Must be one of: {VALID_FORCED_PREFERENCES}"
                )

        for key, value in fields.items():
            if key not in allowed:
                continue
            if key == "target_languages":
                profile.target_languages_json = json.dumps(value)
            elif key == "target_language_names":
                profile.target_language_names_json = json.dumps(value)
            elif key == "fallback_chain":
                profile.fallback_chain_json = json.dumps(value)
            else:
                setattr(profile, key, value)

        profile.updated_at = self._now()
        self._commit()
        return True

    def delete_profile(self, profile_id: int) -> bool:
        """Delete a language profile (cannot delete default). Returns True if deleted."""
        profile = self.session.get(LanguageProfile, profile_id)
        if not profile:
            return False
        if profile.is_default:
            return False  # Cannot delete default profile

        # Cascade-delete series/movie assignments
        self.session.execute(
            delete(SeriesLanguageProfile).where(
                SeriesLanguageProfile.profile_id == profile_id
            )
        )
        self.session.execute(
            delete(MovieLanguageProfile).where(
                MovieLanguageProfile.profile_id == profile_id
            )
        )
        self.session.delete(profile)
        self._commit()
        return True

    # ---- Series profile assignments ----

    def set_series_profile(self, sonarr_series_id: int, profile_id: int):
        """Assign a language profile to a series."""
        entry = SeriesLanguageProfile(
            sonarr_series_id=sonarr_series_id,
            profile_id=profile_id,
        )
        self.session.merge(entry)
        self._commit()

    def get_series_profile(self, sonarr_series_id: int) -> dict:
        """Get the language profile assigned to a series. Falls back to default."""
        stmt = (
            select(LanguageProfile)
            .join(
                SeriesLanguageProfile,
                SeriesLanguageProfile.profile_id == LanguageProfile.id,
            )
            .where(SeriesLanguageProfile.sonarr_series_id == sonarr_series_id)
        )
        row = self.session.execute(stmt).scalars().first()
        if row:
            return self._row_to_profile(row)
        return self.get_default_profile()

    def remove_series_profile(self, sonarr_series_id: int) -> bool:
        """Remove a series profile assignment. Returns True if deleted."""
        stmt = delete(SeriesLanguageProfile).where(
            SeriesLanguageProfile.sonarr_series_id == sonarr_series_id
        )
        result = self.session.execute(stmt)
        self._commit()
        return result.rowcount > 0

    # ---- Movie profile assignments ----

    def set_movie_profile(self, radarr_movie_id: int, profile_id: int):
        """Assign a language profile to a movie."""
        entry = MovieLanguageProfile(
            radarr_movie_id=radarr_movie_id,
            profile_id=profile_id,
        )
        self.session.merge(entry)
        self._commit()

    def get_movie_profile(self, radarr_movie_id: int) -> dict:
        """Get the language profile assigned to a movie. Falls back to default."""
        stmt = (
            select(LanguageProfile)
            .join(
                MovieLanguageProfile,
                MovieLanguageProfile.profile_id == LanguageProfile.id,
            )
            .where(MovieLanguageProfile.radarr_movie_id == radarr_movie_id)
        )
        row = self.session.execute(stmt).scalars().first()
        if row:
            return self._row_to_profile(row)
        return self.get_default_profile()

    def remove_movie_profile(self, radarr_movie_id: int) -> bool:
        """Remove a movie profile assignment. Returns True if deleted."""
        stmt = delete(MovieLanguageProfile).where(
            MovieLanguageProfile.radarr_movie_id == radarr_movie_id
        )
        result = self.session.execute(stmt)
        self._commit()
        return result.rowcount > 0

    # ---- Profile assignments overview ----

    def get_profile_assignments(self) -> dict:
        """Return {series: [...], movies: [...]} for all assignments."""
        series_stmt = select(
            SeriesLanguageProfile.sonarr_series_id,
            SeriesLanguageProfile.profile_id,
        )
        series_rows = self.session.execute(series_stmt).all()

        movie_stmt = select(
            MovieLanguageProfile.radarr_movie_id,
            MovieLanguageProfile.profile_id,
        )
        movie_rows = self.session.execute(movie_stmt).all()

        return {
            "series": {row[0]: row[1] for row in series_rows},
            "movies": {row[0]: row[1] for row in movie_rows},
        }

    def get_series_profile_map(self) -> dict:
        """Get all series -> {profile_id, profile_name} map for library enrichment."""
        stmt = (
            select(
                SeriesLanguageProfile.sonarr_series_id,
                LanguageProfile.id,
                LanguageProfile.name,
            )
            .join(
                LanguageProfile,
                SeriesLanguageProfile.profile_id == LanguageProfile.id,
            )
        )
        rows = self.session.execute(stmt).all()
        return {
            row[0]: {"profile_id": row[1], "profile_name": row[2]}
            for row in rows
        }

    def get_series_missing_counts(self) -> dict:
        """Get wanted item counts per series: {series_id: count}."""
        stmt = (
            select(WantedItem.sonarr_series_id, func.count())
            .where(
                WantedItem.sonarr_series_id.isnot(None),
                WantedItem.status == "wanted",
            )
            .group_by(WantedItem.sonarr_series_id)
        )
        rows = self.session.execute(stmt).all()
        return {row[0]: row[1] for row in rows}

    # ---- Helpers ----

    def _row_to_profile(self, profile: LanguageProfile) -> dict:
        """Convert a LanguageProfile model to a dict. Parse JSON columns."""
        d = self._to_dict(profile)
        d["is_default"] = bool(d.get("is_default", 0))

        try:
            d["target_languages"] = json.loads(d.get("target_languages_json", "[]"))
        except json.JSONDecodeError:
            d["target_languages"] = []
        if "target_languages_json" in d:
            del d["target_languages_json"]

        try:
            d["target_language_names"] = json.loads(
                d.get("target_language_names_json", "[]")
            )
        except json.JSONDecodeError:
            d["target_language_names"] = []
        if "target_language_names_json" in d:
            del d["target_language_names_json"]

        # Translation backend fields (added in Phase 2)
        d["translation_backend"] = d.get("translation_backend", "ollama")
        try:
            d["fallback_chain"] = json.loads(
                d.get("fallback_chain_json", '["ollama"]')
            )
        except (json.JSONDecodeError, TypeError):
            d["fallback_chain"] = ["ollama"]
        if "fallback_chain_json" in d:
            del d["fallback_chain_json"]

        # Forced subtitle preference (added in Phase 6)
        d["forced_preference"] = d.get("forced_preference", "disabled")

        return d
