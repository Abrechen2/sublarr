"""Inheritance resolver for the Profiles & Overrides UI.

Pure-function service that walks the Global → LanguageProfile → Series/Movie
inheritance chain for each of the 12 inheritable settings. Returns the
effective value plus the full chain so the UI can show every step (Codex
Settings Template C).

Field registry is the single source of truth — referenced by the API
blueprint and the frontend metadata builder. Renaming or adding a field
must update this registry.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, NotRequired, TypedDict


ScopeKind = Literal["global", "profile", "series", "movie"]


class ChainStep(TypedDict):
    scope: ScopeKind
    value: Any
    label: str


class ResolvedSetting(TypedDict):
    effective: Any
    source: ScopeKind
    chain: list[ChainStep]


@dataclass(frozen=True)
class InheritableField:
    """One row of the registry — describes how to walk the chain for a
    single setting.

    `profile_attr` is the attribute name on `LanguageProfile`, or None if
    the setting has no profile-level value (chain skips profile step).
    `override_col` is the column name on `series_settings` and
    `movie_settings` (same name on both tables by design).
    `global_key` is the Pydantic settings attribute name on the global
    config object, or None if there is no global default.
    `value_kind` informs the resolver how to interpret a raw value:
      - "scalar": value used as-is
      - "json_array": stored as JSON-encoded string, decoded on read
    """

    display_name: str
    profile_attr: str | None
    override_col: str
    global_key: str | None
    value_kind: Literal["scalar", "json_array"] = "scalar"


INHERITABLE_FIELDS: tuple[InheritableField, ...] = (
    InheritableField("cleanup_foreign_tracks", None, "cleanup_foreign_tracks", "cleanup_foreign_tracks_default"),
    InheritableField("forced_preference", "forced_preference", "forced_preference_override", "forced_preference"),
    InheritableField("hi_preference", "hi_preference", "hi_preference_override", "hi_preference"),
    InheritableField("forced_scoring", "forced_scoring", "forced_scoring_override", None),
    InheritableField("target_languages", "target_languages_json", "target_languages_override", None, "json_array"),
    InheritableField("cutoff_language", "cutoff_language", "cutoff_language_override", None),
    InheritableField("must_contain", "must_contain_json", "must_contain_override", None, "json_array"),
    InheritableField("must_not_contain", "must_not_contain_json", "must_not_contain_override", None, "json_array"),
    InheritableField("audio_exclude_languages", "audio_exclude_languages_json", "audio_exclude_languages_override", None, "json_array"),
    InheritableField("preferred_audio_track_index", None, "preferred_audio_track_index", None),
    InheritableField("priority_override", None, "priority_override", "provider_priorities"),
    InheritableField("min_attempts_per_day", None, "min_attempts_per_day", None),
)
