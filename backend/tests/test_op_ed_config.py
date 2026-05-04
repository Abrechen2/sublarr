# backend/tests/test_op_ed_config.py
"""Config tests for op_window_sec setting."""


def test_op_window_sec_default_is_300(temp_db):
    from config import get_settings

    s = get_settings()
    assert getattr(s, "op_window_sec", None) == 300


def test_op_window_sec_db_override(temp_db):
    """``op_window_sec`` is a UI field — set via DB override, not env.

    Since v0.88.0-beta the env-loadable surface is BootSettings only;
    op_window_sec lives on UISettings and accepts only DB-driven overrides.
    """
    from config import reload_settings

    try:
        s = reload_settings(overrides={"op_window_sec": "120"})
        assert getattr(s, "op_window_sec", None) == 120
    finally:
        reload_settings()
