"""Language profile database operations -- delegating to SQLAlchemy repository."""

from db.repositories.profiles import ProfileRepository

_repo = None


def _get_repo():
    global _repo
    if _repo is None:
        _repo = ProfileRepository()
    return _repo


# ---- Profile CRUD ----


def create_language_profile(
    name: str,
    source_lang: str,
    source_name: str,
    target_langs: list,
    target_names: list,
    translation_backend: str = "ollama",
    fallback_chain: list = None,
    forced_preference: str = "disabled",
) -> int:
    """Create a new language profile. Returns the profile ID."""
    return _get_repo().create_profile(
        name,
        source_lang,
        source_name,
        target_langs,
        target_names,
        translation_backend,
        fallback_chain,
        forced_preference,
    )


def get_language_profile(profile_id: int) -> dict | None:
    """Get a language profile by ID."""
    return _get_repo().get_profile(profile_id)


def get_all_language_profiles() -> list:
    """Get all language profiles, default first."""
    return _get_repo().get_profiles()


def update_language_profile(profile_id: int, **fields):
    """Update a language profile's fields."""
    return _get_repo().update_profile(profile_id, **fields)


def delete_language_profile(profile_id: int) -> bool:
    """Delete a language profile (cannot delete default). Returns True if deleted."""
    return _get_repo().delete_profile(profile_id)


def get_default_profile() -> dict:
    """Get the default language profile."""
    return _get_repo().get_default_profile()


# ---- Series profile assignments ----


def get_series_profile(sonarr_series_id: int) -> dict:
    """Get the language profile assigned to a series. Falls back to default."""
    return _get_repo().get_series_profile(sonarr_series_id)


def get_movie_profile(radarr_movie_id: int) -> dict:
    """Get the language profile assigned to a movie. Falls back to default."""
    return _get_repo().get_movie_profile(radarr_movie_id)


def assign_series_profile(sonarr_series_id: int, profile_id: int):
    """Assign a language profile to a series."""
    return _get_repo().set_series_profile(sonarr_series_id, profile_id)


def assign_movie_profile(radarr_movie_id: int, profile_id: int):
    """Assign a language profile to a movie."""
    return _get_repo().set_movie_profile(radarr_movie_id, profile_id)


def get_series_profile_assignments() -> dict:
    """Get all series -> profile_id assignments."""
    result = _get_repo().get_profile_assignments()
    return result.get("series", {})


def get_movie_profile_assignments() -> dict:
    """Get all movie -> profile_id assignments."""
    result = _get_repo().get_profile_assignments()
    return result.get("movies", {})


def get_series_profile_map() -> dict:
    """Get all series -> {profile_id, profile_name} map for library enrichment."""
    return _get_repo().get_series_profile_map()


def get_series_missing_counts() -> dict:
    """Get wanted item counts per series: {series_id: count}."""
    return _get_repo().get_series_missing_counts()


# Keep private helper for backward compat
def _row_to_profile(row) -> dict:
    """Convert a database row to a profile dict (legacy compat)."""
    if hasattr(row, "__dict__"):
        return _get_repo()._row_to_profile(row)
    return dict(row) if row else None
