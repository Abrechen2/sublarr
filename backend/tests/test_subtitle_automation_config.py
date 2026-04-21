"""Config-key tests for 0.71.0 subtitle automation (Phase 2).

Pins the 7 new Pydantic fields on `Settings` with defaults + types:

- `subtitle_automation_enabled` — master toggle (off by default)
- `subtitle_automation_queue_enabled` — drain worker on/off
- `subtitle_automation_drain_interval_minutes` — scheduler tick cadence
- `embedded_allow_sdh` — SDH tracks usable as source (default on)
- `embedded_sdh_penalty` — scoring penalty so non-SDH wins ties
- `cleanup_foreign_tracks_default` — global default when per-series is NULL
- `cleanup_foreign_tracks_keep_und` — keep language=und streams even when cleaning
"""

from config_settings import Settings


class TestAutomationMasterToggle:
    def test_master_default_off(self):
        s = Settings()
        assert s.subtitle_automation_enabled is False

    def test_queue_drain_default_on(self):
        s = Settings()
        assert s.subtitle_automation_queue_enabled is True

    def test_drain_interval_default_two_minutes(self):
        s = Settings()
        assert s.subtitle_automation_drain_interval_minutes == 2
        assert isinstance(s.subtitle_automation_drain_interval_minutes, int)


class TestSdhTolerance:
    def test_allow_sdh_default_on(self):
        s = Settings()
        assert s.embedded_allow_sdh is True

    def test_sdh_penalty_default_small_positive(self):
        s = Settings()
        # Small integer penalty (5-20 range); exact value is a design knob.
        assert isinstance(s.embedded_sdh_penalty, int)
        assert 0 < s.embedded_sdh_penalty <= 50


class TestForeignTrackCleanup:
    def test_cleanup_default_off(self):
        """Destructive feature — must be opt-in globally."""
        s = Settings()
        assert s.cleanup_foreign_tracks_default is False

    def test_keep_und_default_off(self):
        """`und` (language=undetermined) tracks — strip them by default.

        Design choice: `und` tracks are usually unwanted fallbacks; keeping
        them requires explicit opt-in. True would preserve them."""
        s = Settings()
        assert s.cleanup_foreign_tracks_keep_und is False


class TestEnvOverrides:
    """All 7 keys must respect the SUBLARR_ env-var prefix."""

    def test_master_toggle_env_override(self, monkeypatch):
        monkeypatch.setenv("SUBLARR_SUBTITLE_AUTOMATION_ENABLED", "true")
        s = Settings()
        assert s.subtitle_automation_enabled is True

    def test_sdh_penalty_env_override(self, monkeypatch):
        monkeypatch.setenv("SUBLARR_EMBEDDED_SDH_PENALTY", "15")
        s = Settings()
        assert s.embedded_sdh_penalty == 15

    def test_cleanup_default_env_override(self, monkeypatch):
        monkeypatch.setenv("SUBLARR_CLEANUP_FOREIGN_TRACKS_DEFAULT", "true")
        s = Settings()
        assert s.cleanup_foreign_tracks_default is True


class TestScanningSettingsViewExposure:
    """The grouped view exposed via /api/v1/config must include the 7 keys."""

    def test_scanning_view_contains_all_automation_keys(self):
        from config_views import ScanningSettings

        expected = {
            "subtitle_automation_enabled",
            "subtitle_automation_queue_enabled",
            "subtitle_automation_drain_interval_minutes",
            "embedded_allow_sdh",
            "embedded_sdh_penalty",
            "cleanup_foreign_tracks_default",
            "cleanup_foreign_tracks_keep_und",
        }
        missing = expected - ScanningSettings._fields
        assert not missing, f"ScanningSettings view missing keys: {missing}"
