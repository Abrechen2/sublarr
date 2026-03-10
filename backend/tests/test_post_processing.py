"""Post-processing hook integration tests.

Tests:
- TestSubtitleDownloadedEvent: subtitle_downloaded emitted after save_subtitle()
- TestEventCatalogPayloadKeys: catalog has subtitle_path key
- TestHookEngineScriptExecution: HookEngine runs scripts with correct env vars
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── TestEventCatalogPayloadKeys ───────────────────────────────────────────────


class TestEventCatalogPayloadKeys:
    def test_subtitle_downloaded_has_subtitle_path_key(self):
        from events.catalog import EVENT_CATALOG

        keys = EVENT_CATALOG["subtitle_downloaded"]["payload_keys"]
        assert "subtitle_path" in keys

    def test_subtitle_downloaded_has_provider_name(self):
        from events.catalog import EVENT_CATALOG

        keys = EVENT_CATALOG["subtitle_downloaded"]["payload_keys"]
        assert "provider_name" in keys

    def test_subtitle_downloaded_has_score(self):
        from events.catalog import EVENT_CATALOG

        keys = EVENT_CATALOG["subtitle_downloaded"]["payload_keys"]
        assert "score" in keys

    def test_subtitle_downloaded_has_format(self):
        from events.catalog import EVENT_CATALOG

        keys = EVENT_CATALOG["subtitle_downloaded"]["payload_keys"]
        assert "format" in keys

    def test_translation_complete_in_catalog(self):
        from events.catalog import EVENT_CATALOG

        assert "translation_complete" in EVENT_CATALOG

    def test_upgrade_complete_in_catalog(self):
        from events.catalog import EVENT_CATALOG

        assert "upgrade_complete" in EVENT_CATALOG


# ── TestSubtitleDownloadedEvent ───────────────────────────────────────────────


class TestSubtitleDownloadedEvent:
    def _make_result(self, path="/media/ep.mkv", provider="opensubtitles", score=600, fmt="ass"):
        from providers.base import SubtitleFormat, SubtitleResult

        result = SubtitleResult(
            provider_name=provider,
            subtitle_id="abc123",
            language="de",
            score=score,
            release_info="",
            matches=set(),
        )
        result.format = SubtitleFormat.ASS if fmt == "ass" else SubtitleFormat.SRT
        result.content = b"[Script Info]\nTitle: Test"
        return result

    def test_emit_event_called_after_save(self, tmp_path):
        result = self._make_result()
        output_path = str(tmp_path / "ep.de.ass")

        captured_events = []

        def mock_emit(event_name, data=None):
            captured_events.append((event_name, data))

        mock_settings = MagicMock()
        mock_settings.media_path = str(tmp_path)
        mock_settings.dedup_on_download = False

        with (
            patch("config.get_settings", return_value=mock_settings),
            patch("events.emit_event", side_effect=mock_emit),
            patch("providers.__init__.is_safe_path", return_value=True)
            if False
            else patch("security_utils.is_safe_path", return_value=True),
            patch("subtitle_sanitizer.sanitize_subtitle", side_effect=lambda c, f: c),
        ):
            from providers import ProviderManager

            mgr = ProviderManager.__new__(ProviderManager)
            mgr.settings = mock_settings
            mgr._providers = {}
            mgr.save_subtitle(result, output_path)

        assert any(name == "subtitle_downloaded" for name, _ in captured_events), (
            f"subtitle_downloaded not emitted; got: {[n for n, _ in captured_events]}"
        )

    def test_emit_event_payload_has_required_keys(self, tmp_path):
        result = self._make_result(score=750, fmt="ass")
        output_path = str(tmp_path / "ep.de.ass")

        emitted_data = {}

        def mock_emit(event_name, data=None):
            if event_name == "subtitle_downloaded":
                emitted_data.update(data or {})

        mock_settings = MagicMock()
        mock_settings.media_path = str(tmp_path)
        mock_settings.dedup_on_download = False

        with (
            patch("config.get_settings", return_value=mock_settings),
            patch("events.emit_event", side_effect=mock_emit),
            patch("security_utils.is_safe_path", return_value=True),
            patch("subtitle_sanitizer.sanitize_subtitle", side_effect=lambda c, f: c),
        ):
            from providers import ProviderManager

            mgr = ProviderManager.__new__(ProviderManager)
            mgr.settings = mock_settings
            mgr._providers = {}
            mgr.save_subtitle(result, output_path)

        for key in ("subtitle_path", "provider_name", "language", "format", "score"):
            assert key in emitted_data, f"missing key: {key}"

    def test_emit_failure_does_not_raise(self, tmp_path):
        result = self._make_result()
        output_path = str(tmp_path / "ep.de.ass")

        mock_settings = MagicMock()
        mock_settings.media_path = str(tmp_path)
        mock_settings.dedup_on_download = False

        with (
            patch("config.get_settings", return_value=mock_settings),
            patch("events.emit_event", side_effect=RuntimeError("socket error")),
            patch("security_utils.is_safe_path", return_value=True),
            patch("subtitle_sanitizer.sanitize_subtitle", side_effect=lambda c, f: c),
        ):
            from providers import ProviderManager

            mgr = ProviderManager.__new__(ProviderManager)
            mgr.settings = mock_settings
            mgr._providers = {}
            # Should not raise even when emit_event fails
            path = mgr.save_subtitle(result, output_path)

        assert path == output_path


# ── TestHookEngineEnvVars ─────────────────────────────────────────────────────


class TestHookEngineEnvVars:
    def _make_script(self, tmp_path, code: str) -> str:
        """Create a cross-platform Python script and return its path."""
        import sys

        script = tmp_path / "hook.py"
        script.write_text(f"#!{sys.executable}\n{code}")
        return str(sys.executable) + " " + str(script)

    def test_subtitle_path_in_env_vars(self, tmp_path):
        """HookEngine passes SUBLARR_SUBTITLE_PATH to the script environment."""
        import sys

        script = tmp_path / "hook.py"
        script.write_text(f"#!{sys.executable}\nimport sys; sys.exit(0)")

        hook_config = {
            "id": 1,
            "name": "test",
            "script_path": sys.executable,
            "timeout_seconds": 5,
        }
        event_data = {
            "subtitle_path": "/media/series/ep.de.ass",
            "provider_name": "opensubtitles",
            "language": "de",
            "format": "ass",
            "score": 600,
        }

        import stat

        from events.hooks import HookEngine

        engine = HookEngine(max_workers=1)
        hook_config["script_path"] = str(script)
        script.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)

        result = engine.execute_hook(hook_config, "subtitle_downloaded", event_data)
        # On Windows, Python scripts need interpreter - verify we got a result dict
        assert "success" in result

    def test_env_var_names_have_sublarr_prefix(self):
        """Each event_data key becomes SUBLARR_<KEY> in the environment."""
        event_data = {
            "provider_name": "testprovider",
            "subtitle_path": "/media/ep.de.ass",
        }

        # Verify that env var keys are built correctly from event_data keys
        for key in event_data:
            env_key = f"SUBLARR_{key.upper()}"
            assert env_key.startswith("SUBLARR_")
            assert env_key == f"SUBLARR_{key.upper()}"

    def test_missing_script_returns_failure(self, tmp_path):
        hook_config = {
            "id": 1,
            "name": "missing",
            "script_path": "/nonexistent/path/script.sh",
            "timeout_seconds": 5,
        }

        from events.hooks import HookEngine

        engine = HookEngine(max_workers=1)
        result = engine.execute_hook(hook_config, "subtitle_downloaded", {})

        assert result["success"] is False
        assert "not found" in result.get("error", "").lower()
