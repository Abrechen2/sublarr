"""Scheduler integration tests for subtitle_automation (Phase 3c)."""

from unittest.mock import patch

from apscheduler.triggers.interval import IntervalTrigger

from services.scheduler import _build_default_jobs
from services.subtitle_automation_runner import subtitle_automation_tick


class TestJobSpecRegistration:
    def test_subtitle_automation_jobspec_present(self):
        specs = _build_default_jobs()
        ids = {s.id for s in specs}
        assert "subtitle_automation" in ids

    def test_jobspec_wires_to_runner_tick(self):
        specs = _build_default_jobs()
        spec = next(s for s in specs if s.id == "subtitle_automation")
        assert spec.func is subtitle_automation_tick

    def test_jobspec_interval_trigger_defaults_to_two_minutes(self):
        """When subtitle_automation_drain_interval_minutes is unset (or
        default=2), the JobSpec's trigger should fire every 2 minutes."""
        specs = _build_default_jobs()
        spec = next(s for s in specs if s.id == "subtitle_automation")
        assert isinstance(spec.default_trigger, IntervalTrigger)
        assert spec.default_trigger.interval.total_seconds() == 120

    def test_jobspec_reads_configurable_interval(self):
        """A custom interval from settings must propagate to the trigger."""
        from config_settings import Settings

        class FakeSettings(Settings):
            pass

        fake = FakeSettings(subtitle_automation_drain_interval_minutes=10)
        with patch("config.get_settings", return_value=fake):
            specs = _build_default_jobs()
        spec = next(s for s in specs if s.id == "subtitle_automation")
        assert spec.default_trigger.interval.total_seconds() == 600


class TestTickCallable:
    def test_tick_is_picklable(self):
        """SQLAlchemyJobStore pickles job callables — tick must be
        module-level, not a closure/lambda."""
        import pickle

        blob = pickle.dumps(subtitle_automation_tick)
        restored = pickle.loads(blob)
        assert restored is subtitle_automation_tick

    def test_tick_invokes_runner_drain(self):
        with patch(
            "services.subtitle_automation_runner.SubtitleAutomationRunner"
        ) as cls:
            instance = cls.return_value
            instance.drain.return_value = 0
            subtitle_automation_tick()
        cls.assert_called_once_with()
        instance.drain.assert_called_once()
        call = instance.drain.call_args
        assert call.kwargs.get("max_items", 0) > 0
