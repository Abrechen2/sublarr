"""Filter presets database operations -- delegating to SQLAlchemy repository.

Thin wrapper with lazy-initialized repository for convenience access
from route handlers and other modules.
"""

from db.repositories.presets import FilterPresetsRepository

_repo = None


def _get_repo():
    global _repo
    if _repo is None:
        _repo = FilterPresetsRepository()
    return _repo


def list_presets(scope: str) -> list[dict]:
    """List all filter presets for a given scope."""
    return _get_repo().list_presets(scope)


def get_preset(preset_id: int) -> dict | None:
    """Get a single filter preset by ID."""
    return _get_repo().get_preset(preset_id)


def create_preset(name: str, scope: str, conditions: dict, is_default: bool = False) -> dict:
    """Create a new filter preset."""
    return _get_repo().create_preset(name, scope, conditions, is_default)


def update_preset(
    preset_id: int, name: str = None, conditions: dict = None, is_default: bool = None
) -> dict | None:
    """Update an existing filter preset."""
    return _get_repo().update_preset(preset_id, name, conditions, is_default)


def delete_preset(preset_id: int) -> bool:
    """Delete a filter preset by ID."""
    return _get_repo().delete_preset(preset_id)


def build_preset_clause(preset_id: int, field_map: dict):
    """Load a preset by ID and return its build_clause() result.

    Convenience function that loads conditions from a preset and converts
    them into a SQLAlchemy WHERE clause ready for .where().

    Args:
        preset_id: The preset ID to load.
        field_map: Maps field name strings to SQLAlchemy column objects.

    Returns:
        SQLAlchemy clause, or None if preset not found.

    Raises:
        ValueError: If preset conditions contain invalid fields/operators.
    """
    preset = _get_repo().get_preset(preset_id)
    if not preset:
        return None
    return _get_repo().build_clause(preset["conditions"], field_map)
