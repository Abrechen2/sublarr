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

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, TypedDict

if TYPE_CHECKING:
    from db.models.core import LanguageProfile, MovieSettings, SeriesSettings


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
    InheritableField(
        "cleanup_foreign_tracks", None, "cleanup_foreign_tracks", "cleanup_foreign_tracks_default"
    ),
    InheritableField(
        "forced_preference", "forced_preference", "forced_preference_override", "forced_preference"
    ),
    InheritableField("hi_preference", "hi_preference", "hi_preference_override", "hi_preference"),
    InheritableField("forced_scoring", "forced_scoring", "forced_scoring_override", None),
    InheritableField(
        "target_languages", "target_languages_json", "target_languages_override", None, "json_array"
    ),
    InheritableField("cutoff_language", "cutoff_language", "cutoff_language_override", None),
    InheritableField(
        "must_contain", "must_contain_json", "must_contain_override", None, "json_array"
    ),
    InheritableField(
        "must_not_contain", "must_not_contain_json", "must_not_contain_override", None, "json_array"
    ),
    InheritableField(
        "audio_exclude_languages",
        "audio_exclude_languages_json",
        "audio_exclude_languages_override",
        None,
        "json_array",
    ),
    InheritableField("preferred_audio_track_index", None, "preferred_audio_track_index", None),
    InheritableField("priority_override", None, "priority_override", "provider_priorities"),
    InheritableField("min_attempts_per_day", None, "min_attempts_per_day", None),
)


def _decode(value: Any, kind: Literal["scalar", "json_array"]) -> Any:
    """Decode a raw stored value according to its kind.

    Exported at module level so Task 9 (movie resolver) can reuse it.
    """
    if value is None:
        return None
    if kind == "json_array":
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return None
        return value
    return value


def resolve_for_series(
    *,
    series: SeriesSettings | None,
    profile: LanguageProfile | None,
    global_cfg: Any,
) -> dict[str, ResolvedSetting]:
    """Walk Global → Profile → Series for each inheritable field.

    Returns dict keyed by display_name; each value is a ResolvedSetting
    with `effective`, `source`, and full `chain`. The chain only contains
    steps that exist for the field — e.g. fields without `profile_attr`
    omit the profile step; fields without `global_key` omit the global step.
    """
    result: dict[str, ResolvedSetting] = {}
    profile_label = profile.name if profile else None

    for field in INHERITABLE_FIELDS:
        chain: list[ChainStep] = []

        # 1. Global step
        if field.global_key is not None:
            raw_global = getattr(global_cfg, field.global_key, None)
            chain.append(
                {
                    "scope": "global",
                    "value": _decode(raw_global, field.value_kind),
                    "label": "Global default",
                }
            )

        # 2. Profile step
        if field.profile_attr is not None and profile is not None:
            raw_profile = getattr(profile, field.profile_attr, None)
            chain.append(
                {
                    "scope": "profile",
                    "value": _decode(raw_profile, field.value_kind),
                    "label": profile_label or "Profile",
                }
            )

        # 3. Series step
        raw_series = getattr(series, field.override_col, None) if series else None
        chain.append(
            {
                "scope": "series",
                "value": _decode(raw_series, field.value_kind),
                "label": "This series",
            }
        )

        # Walk chain bottom-up: last non-None wins (most specific scope).
        effective = None
        source: ScopeKind = "global"
        for step in reversed(chain):
            if step["value"] is not None:
                effective = step["value"]
                source = step["scope"]
                break
        # If everything was None, fall back to first chain step's value
        if effective is None and chain:
            effective = chain[0]["value"]
            source = chain[0]["scope"]

        result[field.display_name] = {
            "effective": effective,
            "source": source,
            "chain": chain,
        }
    return result


def resolve_for_movie(
    *,
    movie: MovieSettings | None,
    profile: LanguageProfile | None,
    global_cfg: Any,
) -> dict[str, ResolvedSetting]:
    """Mirror of resolve_for_series for movies. Uses 'movie' scope label
    in chain instead of 'series'."""
    result: dict[str, ResolvedSetting] = {}
    profile_label = profile.name if profile else None

    for field in INHERITABLE_FIELDS:
        chain: list[ChainStep] = []

        if field.global_key is not None:
            raw_global = getattr(global_cfg, field.global_key, None)
            chain.append(
                {
                    "scope": "global",
                    "value": _decode(raw_global, field.value_kind),
                    "label": "Global default",
                }
            )

        if field.profile_attr is not None and profile is not None:
            raw_profile = getattr(profile, field.profile_attr, None)
            chain.append(
                {
                    "scope": "profile",
                    "value": _decode(raw_profile, field.value_kind),
                    "label": profile_label or "Profile",
                }
            )

        raw_movie = getattr(movie, field.override_col, None) if movie else None
        chain.append(
            {
                "scope": "movie",
                "value": _decode(raw_movie, field.value_kind),
                "label": "This movie",
            }
        )

        effective = None
        source: ScopeKind = "global"
        for step in reversed(chain):
            if step["value"] is not None:
                effective = step["value"]
                source = step["scope"]
                break
        if effective is None and chain:
            effective = chain[0]["value"]
            source = chain[0]["scope"]

        result[field.display_name] = {
            "effective": effective,
            "source": source,
            "chain": chain,
        }
    return result
