"""Tests for db.storage_probe — the slow-storage startup warning.

The probe measures per-commit SQLite latency and warns self-hosters whose
/config volume sits on a microSD card or network share (the dominant cause of
"Sublarr is painfully slow" reports). These tests pin the two behaviours that
matter: it returns a real number for a working engine, and it only warns above
the threshold.
"""

import logging

from sqlalchemy import create_engine

from db.storage_probe import (
    SLOW_STORAGE_THRESHOLD_MS,
    measure_commit_latency_ms,
    warn_if_slow_storage,
)


def test_measure_returns_nonnegative_float_for_working_engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'probe.db'}")
    latency = measure_commit_latency_ms(engine, samples=3)
    assert latency is not None
    assert latency >= 0.0


def test_measure_returns_none_on_broken_engine():
    # A bogus URL yields an engine whose connect() raises — probe must swallow
    # it and return None, never propagate (startup must not break).
    engine = create_engine("sqlite:////nonexistent_dir_xyz/definitely/missing.db")
    assert measure_commit_latency_ms(engine, samples=2) is None


def test_probe_leaves_no_residual_table(tmp_path):
    from sqlalchemy import inspect

    engine = create_engine(f"sqlite:///{tmp_path / 'probe.db'}")
    measure_commit_latency_ms(engine, samples=2)
    assert "_sublarr_storage_probe" not in inspect(engine).get_table_names()


def test_warn_fires_above_threshold(monkeypatch, caplog):
    monkeypatch.setattr(
        "db.storage_probe.measure_commit_latency_ms",
        lambda engine, samples=5: SLOW_STORAGE_THRESHOLD_MS + 50.0,
    )
    with caplog.at_level(logging.WARNING, logger="db.storage_probe"):
        latency = warn_if_slow_storage(object())
    assert latency == SLOW_STORAGE_THRESHOLD_MS + 50.0
    assert any("storage is slow" in r.message for r in caplog.records)


def test_warn_silent_below_threshold(monkeypatch, caplog):
    monkeypatch.setattr(
        "db.storage_probe.measure_commit_latency_ms",
        lambda engine, samples=5: 2.0,
    )
    with caplog.at_level(logging.WARNING, logger="db.storage_probe"):
        warn_if_slow_storage(object())
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_warn_handles_probe_failure(monkeypatch):
    monkeypatch.setattr(
        "db.storage_probe.measure_commit_latency_ms",
        lambda engine, samples=5: None,
    )
    assert warn_if_slow_storage(object()) is None
