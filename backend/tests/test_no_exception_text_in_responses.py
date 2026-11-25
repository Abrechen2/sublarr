"""API error responses must not carry raw exception text (Forgejo #77 N-4).

Exception text leaks file system paths, SQL and URLs with API keys. These
tests make the handler fail with a message full of such details and assert
that the response carries only the public message.
"""

import os

import pytest

LEAK = "/srv/secret/path.db?apikey=TOPSECRET123 SELECT * FROM users"


def _assert_no_leak(payload) -> None:
    text = str(payload)
    assert "TOPSECRET123" not in text
    assert "/srv/secret" not in text
    assert "SELECT" not in text


@pytest.fixture
def client(temp_db, tmp_path):
    os.environ["SUBLARR_MEDIA_PATH"] = str(tmp_path)
    from config import reload_settings

    reload_settings()
    from app import create_app

    app = create_app(testing=True)
    with app.test_client() as c, app.app_context():
        yield c
    del os.environ["SUBLARR_MEDIA_PATH"]
    reload_settings()


def test_diff_parse_failure_hides_exception_text(client, monkeypatch):
    import pysubs2

    def boom(*_a, **_kw):
        raise ValueError(LEAK)

    monkeypatch.setattr(pysubs2.SSAFile, "from_string", boom)
    resp = client.post("/api/v1/tools/diff", json={"original": "x", "modified": "y"})
    assert resp.status_code == 400
    _assert_no_leak(resp.get_json())
    assert resp.get_json()["error"] == "Failed to parse subtitle content"


def test_automation_run_now_hides_exception_text(client, monkeypatch):
    import routes.wanted.automation as automation
    from services.subtitle_automation_runner import SubtitleAutomationRunner

    monkeypatch.setattr(automation, "_is_master_toggle_on", lambda: True)

    def boom(self, *a, **kw):
        raise RuntimeError(LEAK)

    monkeypatch.setattr(SubtitleAutomationRunner, "drain", boom)
    resp = client.post("/api/v1/wanted/automation/run-now")
    assert resp.status_code == 500
    body = resp.get_json()
    _assert_no_leak(body)
    assert body["status"] == "error"
    assert body["error"] == "Drain failed"


def test_apprise_connection_test_redacts_exception_text(monkeypatch):
    import notifier
    from routes.api_keys.testing import _test_apprise

    def boom():
        raise RuntimeError(f"connect failed: https://x.example/hook?apikey=TOPSECRET123 {LEAK}")

    monkeypatch.setattr(notifier, "test_notification", boom)
    result = _test_apprise()
    assert result["success"] is False
    assert "TOPSECRET123" not in result["message"]
