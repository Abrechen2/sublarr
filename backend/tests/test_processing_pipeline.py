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
    assert result["common_fixes"] is True  # untouched
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


def test_pipeline_triggered_after_successful_download(tmp_path, monkeypatch):
    """Processing pipeline runs when _run_pipeline_for_path is called with HI removal enabled."""
    from unittest.mock import patch

    monkeypatch.setenv("SUBLARR_MEDIA_PATH", str(tmp_path))
    monkeypatch.setenv("SUBLARR_AUTO_PROCESS_HI_REMOVAL", "true")
    from config import reload_settings

    reload_settings()

    called_with = []

    def mock_apply_mods(path, mods, dry_run=False):
        called_with.append(path)
        from subtitle_processor import ProcessingResult

        return ProcessingResult(changes=[], backed_up=False, output_path=path, dry_run=dry_run)

    sub = tmp_path / "ep.en.srt"
    sub.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n\n", encoding="utf-8")

    from subtitle_processor import ModConfig, ModName

    known_mods = [ModConfig(mod=ModName.HI_REMOVAL)]

    with (
        patch("subtitle_processor.apply_mods", side_effect=mock_apply_mods),
        patch("subtitle_processor.resolve_config", return_value={"hi_removal": True, "common_fixes": False, "credit_removal": False}),
        patch("routes.subtitle_processor._build_pipeline_mods", return_value=known_mods),
    ):
        from routes.subtitle_processor import _run_pipeline_for_path

        _run_pipeline_for_path(str(sub), series_id=None)

    assert len(called_with) == 1
    assert called_with[0] == str(sub)


def test_pipeline_noop_when_no_mods_enabled(tmp_path, monkeypatch):
    """Pipeline is a no-op when all auto_process flags are False."""
    from unittest.mock import patch

    monkeypatch.setenv("SUBLARR_MEDIA_PATH", str(tmp_path))
    monkeypatch.setenv("SUBLARR_AUTO_PROCESS_HI_REMOVAL", "false")
    monkeypatch.setenv("SUBLARR_AUTO_PROCESS_COMMON_FIXES", "false")
    monkeypatch.setenv("SUBLARR_AUTO_PROCESS_CREDIT_REMOVAL", "false")
    from config import reload_settings

    reload_settings()

    sub = tmp_path / "ep.en.srt"
    sub.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n\n", encoding="utf-8")

    called = []
    with patch("subtitle_processor.apply_mods", side_effect=lambda *a, **k: called.append(a)):
        from routes.subtitle_processor import _run_pipeline_for_path

        _run_pipeline_for_path(str(sub), series_id=None)

    assert called == []
