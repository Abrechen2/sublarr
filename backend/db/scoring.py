"""Scoring weights and provider modifier operations -- delegating to SQLAlchemy repository."""

from db.repositories.scoring import ScoringRepository

_repo = None


def _get_repo():
    global _repo
    if _repo is None:
        _repo = ScoringRepository()
    return _repo


# --- Scoring weights CRUD ---

def get_scoring_weights(score_type: str) -> dict:
    """Get scoring weight overrides for a given type."""
    return _get_repo().get_scoring_weights(score_type)


def set_scoring_weights(score_type: str, weights_dict: dict) -> None:
    """Set scoring weight overrides for a given type."""
    return _get_repo().set_scoring_weights(score_type, weights_dict)


def get_all_scoring_weights() -> dict:
    """Get all scoring weights with defaults filled in."""
    return _get_repo().get_all_scoring_weights()


def reset_scoring_weights(score_type: str = None) -> None:
    """Delete scoring weight overrides."""
    return _get_repo().reset_scoring_weights(score_type)


def get_effective_weights(score_type: str) -> dict:
    """Get effective weights (defaults merged with DB overrides)."""
    return _get_repo().get_all_scoring_weights().get(score_type, {})


# --- Provider score modifiers CRUD ---

def get_provider_modifier(provider_name: str) -> int:
    """Get the score modifier for a provider."""
    return _get_repo().get_provider_modifier(provider_name)


def get_all_provider_modifiers() -> dict:
    """Get all provider score modifiers."""
    return _get_repo().get_all_provider_modifiers()


def set_provider_modifier(provider_name: str, modifier: int) -> None:
    """Set or update the score modifier for a provider."""
    return _get_repo().set_provider_modifier(provider_name, modifier)


def delete_provider_modifier(provider_name: str) -> None:
    """Delete the score modifier for a provider."""
    return _get_repo().delete_provider_modifier(provider_name)
