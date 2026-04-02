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
