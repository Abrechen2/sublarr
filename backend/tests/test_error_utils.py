"""Tests for handle_api_error decorator."""

import pytest
from flask import Flask


def make_app():
    app = Flask(__name__)
    app.config["TESTING"] = True
    return app


def test_decorator_passes_through_on_success():
    from error_utils import handle_api_error

    app = make_app()

    @app.route("/ok")
    @handle_api_error("Should not appear")
    def ok_view():
        from flask import jsonify

        return jsonify({"result": "good"})

    with app.test_client() as c:
        resp = c.get("/ok")
        assert resp.status_code == 200
        assert resp.get_json()["result"] == "good"


def test_decorator_returns_500_json_on_exception():
    from error_utils import handle_api_error

    app = make_app()

    @app.route("/boom")
    @handle_api_error("Something went wrong")
    def boom_view():
        raise RuntimeError("kaboom")

    with app.test_client() as c:
        resp = c.get("/boom")
        assert resp.status_code == 500
        data = resp.get_json()
        assert "error" in data
        assert data["error"] == "Something went wrong"


def test_decorator_custom_status_code():
    from error_utils import handle_api_error

    app = make_app()

    @app.route("/bad")
    @handle_api_error("Custom error", status_code=503)
    def bad_view():
        raise ValueError("oops")

    with app.test_client() as c:
        resp = c.get("/bad")
        assert resp.status_code == 503
        assert resp.get_json()["error"] == "Custom error"


def test_decorator_preserves_function_name():
    from error_utils import handle_api_error

    @handle_api_error("msg")
    def my_special_view():
        pass

    assert my_special_view.__name__ == "my_special_view"


# ─── internal_error_response ─────────────────────────────────────────────────


def test_internal_error_response_never_returns_the_exception_text(caplog):
    from error_utils import internal_error_response

    app = make_app()

    @app.route("/fail")
    def fail_view():
        try:
            raise OSError("[Errno 13] Permission denied: '/config/x.db?apikey=abc123'")
        except OSError as exc:
            return internal_error_response("Restore failed", exc)

    with caplog.at_level("ERROR", logger="error_utils"), app.test_client() as c:
        resp = c.get("/fail")

    assert resp.status_code == 500
    assert resp.get_json() == {"error": "Restore failed"}
    assert "apikey" not in resp.get_data(as_text=True)
    # ...but the operator still gets the full exception in the log.
    record = next(r for r in caplog.records if r.name == "error_utils")
    assert record.exc_info and "Permission denied" in str(record.exc_info[1])


def test_internal_error_response_carries_status_and_request_id():
    from flask import g

    from error_utils import internal_error_response

    app = make_app()

    @app.route("/busy")
    def busy_view():
        g.request_id = "req-42"
        return internal_error_response("Ollama pull failed", status=502)

    with app.test_client() as c:
        resp = c.get("/busy")

    assert resp.status_code == 502
    assert resp.get_json() == {"error": "Ollama pull failed", "request_id": "req-42"}


def test_internal_error_response_without_exc_does_not_log(caplog):
    from error_utils import internal_error_response

    app = make_app()
    with caplog.at_level("DEBUG", logger="error_utils"), app.test_request_context():
        _body, status = internal_error_response("Preview failed")

    assert status == 500
    assert not [r for r in caplog.records if r.name == "error_utils"]


# ─── public_error_text ───────────────────────────────────────────────────────


def test_public_error_text_redacts_a_key_in_a_request_url():
    from error_utils import public_error_text

    exc = ConnectionError(
        "HTTPConnectionPool(host='jellyfin', port=8096): Max retries exceeded with url: "
        "/Items?api_key=0123456789abcdef (Caused by NewConnectionError('refused'))"
    )
    text = public_error_text(exc)

    assert "0123456789abcdef" not in text
    assert "Max retries exceeded" in text  # the reason survives


def test_public_error_text_is_one_bounded_line():
    from error_utils import public_error_text

    text = public_error_text(RuntimeError("line one\nline two " + "x" * 1000))

    assert "\n" not in text
    assert text.startswith("line one line two")
    assert len(text) == 300
