"""A 0 ms scheduled sweep must say why it did not run."""

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from services.foreign_tracks import sweep


@pytest.mark.parametrize(
    "enabled,reason",
    [(False, "foreign_track_sweep_enabled=false"), (True, "no enabled foreign_tracks rule")],
)
def test_skipped_tick_explains_its_gate_without_touching_media(
    monkeypatch, caplog, enabled, reason
):
    monkeypatch.setattr(
        "config.get_settings", lambda: SimpleNamespace(foreign_track_sweep_enabled=enabled)
    )
    monkeypatch.setattr(sweep, "_find_rule", lambda _: None)
    run_slice = MagicMock()
    monkeypatch.setattr(sweep, "run_slice", run_slice)
    with caplog.at_level(logging.INFO, logger=sweep.__name__):
        sweep.foreign_track_sweep_tick()
    assert reason in caplog.text
    run_slice.assert_not_called()
