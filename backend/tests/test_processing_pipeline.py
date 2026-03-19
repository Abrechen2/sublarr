# backend/tests/test_processing_pipeline.py
"""Tests for series override config merging and pipeline resolution."""


def test_resolve_config_null_uses_global():
    from subtitle_processor import resolve_config

    global_cfg = {"hi_removal": True, "common_fixes": False}
    series_cfg = {"hi_removal": None}  # null = use global

    result = resolve_config(global_cfg, series_cfg)
    assert result["hi_removal"] is True  # global value preserved


def test_resolve_config_false_overrides_globally_enabled():
    from subtitle_processor import resolve_config

    global_cfg = {"hi_removal": True}
    series_cfg = {"hi_removal": False}

    result = resolve_config(global_cfg, series_cfg)
    assert result["hi_removal"] is False


def test_resolve_config_true_overrides_globally_disabled():
    from subtitle_processor import resolve_config

    global_cfg = {"hi_removal": False}
    series_cfg = {"hi_removal": True}

    result = resolve_config(global_cfg, series_cfg)
    assert result["hi_removal"] is True


def test_resolve_config_partial_override():
    from subtitle_processor import resolve_config

    global_cfg = {"hi_removal": True, "common_fixes": True, "credit_removal": False}
    series_cfg = {"hi_removal": False}  # only override hi_removal

    result = resolve_config(global_cfg, series_cfg)
    assert result["hi_removal"] is False
    assert result["common_fixes"] is True   # untouched
    assert result["credit_removal"] is False  # untouched


def test_resolve_config_none_series_returns_global():
    from subtitle_processor import resolve_config

    global_cfg = {"hi_removal": True}
    result = resolve_config(global_cfg, None)
    assert result == global_cfg


def test_resolve_config_missing_key_treated_as_null():
    from subtitle_processor import resolve_config

    global_cfg = {"hi_removal": True, "common_fixes": True}
    series_cfg = {}  # missing key = same as null

    result = resolve_config(global_cfg, series_cfg)
    assert result["hi_removal"] is True
    assert result["common_fixes"] is True
