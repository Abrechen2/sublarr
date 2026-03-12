# backend/tests/test_op_ed_config.py
"""Config tests for op_window_sec setting."""


def test_op_window_sec_default_is_300(temp_db):
    from config import get_settings

    s = get_settings()
    assert getattr(s, "op_window_sec", None) == 300


def test_op_window_sec_env_override(monkeypatch, temp_db):
    monkeypatch.setenv("SUBLARR_OP_WINDOW_SEC", "120")
    from config import reload_settings

    reload_settings()
    try:
        from config import get_settings

        s = get_settings()
        assert getattr(s, "op_window_sec", None) == 120
    finally:
        # Restore singleton after monkeypatch restores env var
        monkeypatch.delenv("SUBLARR_OP_WINDOW_SEC", raising=False)
        reload_settings()
