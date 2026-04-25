"""Tests for the inheritance resolver service."""
from __future__ import annotations

import pytest

from services.inheritance_resolver import (
    INHERITABLE_FIELDS,
    InheritableField,
    ResolvedSetting,
)


def test_registry_has_twelve_fields():
    assert len(INHERITABLE_FIELDS) == 12


def test_registry_field_names_unique():
    names = [f.display_name for f in INHERITABLE_FIELDS]
    assert len(names) == len(set(names))


def test_registry_includes_known_fields():
    names = {f.display_name for f in INHERITABLE_FIELDS}
    assert names == {
        "cleanup_foreign_tracks",
        "forced_preference",
        "hi_preference",
        "forced_scoring",
        "target_languages",
        "cutoff_language",
        "must_contain",
        "must_not_contain",
        "audio_exclude_languages",
        "preferred_audio_track_index",
        "priority_override",
        "min_attempts_per_day",
    }


def test_resolved_setting_typed_dict_shape():
    r: ResolvedSetting = {
        "effective": True,
        "source": "series",
        "chain": [
            {"scope": "global", "value": False, "label": "Global default"},
            {"scope": "series", "value": True, "label": "Frieren"},
        ],
    }
    assert r["source"] == "series"


# ---------------------------------------------------------------------------
# resolve_for_series tests (Task 5)
# ---------------------------------------------------------------------------
from datetime import datetime, timezone
from unittest.mock import MagicMock

from services.inheritance_resolver import resolve_for_series


def _mk_global(**overrides):
    defaults = {
        "cleanup_foreign_tracks_default": False,
        "forced_preference": "include",
        "hi_preference": "include",
        "provider_priorities": "animetosho,jimaku",
    }
    defaults.update(overrides)
    mock = MagicMock()
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


def _mk_series(**overrides):
    from db.models.core import SeriesSettings
    ss = SeriesSettings(
        sonarr_series_id=1,
        updated_at=datetime.now(timezone.utc),
    )
    for k, v in overrides.items():
        setattr(ss, k, v)
    return ss


def _mk_profile(**overrides):
    from db.models.core import LanguageProfile
    lp = LanguageProfile(
        id=10, name="Anime DE", source_language="en", source_language_name="English",
        target_languages_json='["de"]', target_language_names_json='["German"]',
        is_default=0, created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    for k, v in overrides.items():
        setattr(lp, k, v)
    return lp


def test_resolve_series_uses_series_value_when_set():
    result = resolve_for_series(
        series=_mk_series(cleanup_foreign_tracks=True),
        profile=None,
        global_cfg=_mk_global(cleanup_foreign_tracks_default=False),
    )
    r = result["cleanup_foreign_tracks"]
    assert r["effective"] is True
    assert r["source"] == "series"


def test_resolve_series_falls_through_to_profile_when_series_null():
    result = resolve_for_series(
        series=_mk_series(),  # all NULL
        profile=_mk_profile(forced_preference="prefer"),
        global_cfg=_mk_global(forced_preference="include"),
    )
    r = result["forced_preference"]
    assert r["effective"] == "prefer"
    assert r["source"] == "profile"


def test_resolve_series_falls_through_to_global_when_profile_null():
    result = resolve_for_series(
        series=_mk_series(),
        profile=_mk_profile(forced_preference=None),
        global_cfg=_mk_global(forced_preference="exclude"),
    )
    r = result["forced_preference"]
    assert r["effective"] == "exclude"
    assert r["source"] == "global"


def test_resolve_series_skips_profile_step_for_series_only_fields():
    """min_attempts_per_day has no profile_attr — chain length 2 (Series, no global)."""
    result = resolve_for_series(
        series=_mk_series(min_attempts_per_day=3),
        profile=_mk_profile(),
        global_cfg=_mk_global(),
    )
    r = result["min_attempts_per_day"]
    assert r["effective"] == 3
    assert r["source"] == "series"
    # Profile step omitted from chain
    scopes = [step["scope"] for step in r["chain"]]
    assert "profile" not in scopes


def test_resolve_series_with_no_profile_assigned():
    """Series without a LanguageProfile gets a chain that skips profile entirely."""
    result = resolve_for_series(
        series=_mk_series(),
        profile=None,
        global_cfg=_mk_global(forced_preference="include"),
    )
    r = result["forced_preference"]
    assert r["effective"] == "include"
    assert r["source"] == "global"
    scopes = [step["scope"] for step in r["chain"]]
    assert "profile" not in scopes


def test_resolve_series_json_array_decoded():
    result = resolve_for_series(
        series=_mk_series(target_languages_override='["de","fr"]'),
        profile=_mk_profile(target_languages_json='["de"]'),
        global_cfg=_mk_global(),
    )
    r = result["target_languages"]
    assert r["effective"] == ["de", "fr"]
    assert r["source"] == "series"


def test_resolve_returns_all_twelve_fields():
    result = resolve_for_series(
        series=_mk_series(), profile=None, global_cfg=_mk_global()
    )
    assert len(result) == 12
