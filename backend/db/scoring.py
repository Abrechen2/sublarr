"""Scoring weights and provider modifier operations -- delegating to SQLAlchemy repository."""

from db.repositories.scoring import (
    _DEFAULT_EPISODE_WEIGHTS,
    _DEFAULT_MOVIE_WEIGHTS,
    ScoringRepository,
)

__all__ = [
    "_DEFAULT_EPISODE_WEIGHTS",
    "_DEFAULT_MOVIE_WEIGHTS",
    "get_scoring_weights",
    "set_scoring_weights",
    "get_all_scoring_weights",
    "reset_scoring_weights",
    "get_effective_weights",
    "get_provider_modifier",
    "get_all_provider_modifiers",
    "set_provider_modifier",
    "delete_provider_modifier",
    "get_penalty_rule_weights",
    "set_penalty_rule_weight",
]

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


# --- Penalty rule weight overrides (Plan B4) --------------------------------
#
# NOTE: the provider scoring cache (see providers.base._get_cached_weights)
# is deliberately NOT shared with penalty rules. The pipeline reads the DB
# directly on each compute_score() call because rule lookups are cheap
# (<= a dozen rows). If scoring becomes hot, wrap this with the same
# TTL-cache pattern.


def get_penalty_rule_weights() -> dict[str, int]:
    """Return ``{rule_id: weight}`` overrides for penalty rules."""
    return _get_repo().get_penalty_rule_weights()


def set_penalty_rule_weight(rule_id: str, weight: int) -> None:
    """Upsert a weight override for a single penalty rule."""
    return _get_repo().set_penalty_rule_weight(rule_id, weight)
