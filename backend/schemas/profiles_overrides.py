"""Pydantic v2 schemas for the profiles-overrides API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, model_validator

# Whitelist of allowed override fields and their per-field validation rules.
_ENUM_FIELDS: dict[str, set[str]] = {
    "forced_preference": {"include", "prefer", "exclude", "only", "disabled", "separate", "auto"},
    "hi_preference": {"include", "prefer", "exclude", "only"},
    "forced_scoring": {"include", "prefer", "exclude", "only"},
}
_BOOL_FIELDS: set[str] = {"cleanup_foreign_tracks"}
_INT_FIELDS: set[str] = {"preferred_audio_track_index", "min_attempts_per_day"}
_STRING_FIELDS: set[str] = {"cutoff_language", "priority_override"}
_LANG_ARRAY_FIELDS: set[str] = {"target_languages", "audio_exclude_languages"}
_STRING_ARRAY_FIELDS: set[str] = {"must_contain", "must_not_contain"}

ALL_OVERRIDE_FIELDS: set[str] = (
    set(_ENUM_FIELDS)
    | _BOOL_FIELDS
    | _INT_FIELDS
    | _STRING_FIELDS
    | _LANG_ARRAY_FIELDS
    | _STRING_ARRAY_FIELDS
)

# ISO-639-1 + a few common 3-letter codes Sublarr uses
_ALLOWED_LANG_CODES = {
    "de",
    "en",
    "fr",
    "es",
    "it",
    "pt",
    "nl",
    "ja",
    "ko",
    "zh",
    "ru",
    "pl",
    "tr",
    "ar",
    "und",
    "und1",
    "und2",  # plus undefined sentinels
}


class OverridePatch(BaseModel):
    """PATCH body for /series/<id> and /movie/<id>. Single field per
    request — the body is the literal `{ field_name: value | null }`
    shape, not wrapped."""

    model_config = ConfigDict(extra="forbid")

    changes: dict[str, Any]

    @model_validator(mode="before")
    @classmethod
    def _wrap(cls, data: Any) -> dict[str, Any]:
        # Allow callers to pass either {field: value} or {"changes": {...}}
        if isinstance(data, dict) and "changes" in data and len(data) == 1:
            return data
        return {"changes": data}

    @model_validator(mode="after")
    def _validate_each(self) -> OverridePatch:
        for key, value in self.changes.items():
            if key not in ALL_OVERRIDE_FIELDS:
                raise ValueError(f"unknown override field: {key}")
            if value is None:
                continue  # null clears override — always allowed
            if key in _ENUM_FIELDS:
                if value not in _ENUM_FIELDS[key]:
                    raise ValueError(f"{key}: '{value}' not in {_ENUM_FIELDS[key]}")
            elif key in _BOOL_FIELDS:
                if not isinstance(value, bool):
                    raise ValueError(f"{key} must be bool or null")
            elif key in _INT_FIELDS:
                if not isinstance(value, int) or isinstance(value, bool):
                    raise ValueError(f"{key} must be int or null")
            elif key in _STRING_FIELDS:
                if not isinstance(value, str):
                    raise ValueError(f"{key} must be string or null")
            elif key in _LANG_ARRAY_FIELDS:
                if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                    raise ValueError(f"{key} must be a list of strings or null")
                for code in value:
                    if code not in _ALLOWED_LANG_CODES:
                        raise ValueError(f"{key}: '{code}' is not a recognised language code")
            elif key in _STRING_ARRAY_FIELDS:
                if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                    raise ValueError(f"{key} must be a list of strings or null")
        return self


class ChainStepSchema(BaseModel):
    scope: Literal["global", "profile", "series", "movie"]
    value: Any
    label: str


class ResolvedSettingSchema(BaseModel):
    effective: Any
    source: Literal["global", "profile", "series", "movie"]
    chain: list[ChainStepSchema]


class ScopeRefSchema(BaseModel):
    type: Literal["global", "profile", "series", "movie"]
    id: int | None = None
    name: str


class ResolvedSettingsResponse(BaseModel):
    scope: ScopeRefSchema
    settings: dict[str, ResolvedSettingSchema]


class ProfileTreeNode(BaseModel):
    id: int
    name: str
    is_default: bool
    series: list[dict[str, Any]]  # {id, title}
    movies: list[dict[str, Any]]


class ScopesTreeResponse(BaseModel):
    profiles: list[ProfileTreeNode]
    unassigned_series: list[dict[str, Any]]
    unassigned_movies: list[dict[str, Any]]
