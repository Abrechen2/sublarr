"""Tests for the CaptchaSolver anti-captcha integration."""

from unittest.mock import MagicMock, patch

import pytest

from providers.captcha_solver import (
    BACKEND_ANTICAPTCHA,
    BACKEND_CAPMONSTER,
    CaptchaSolver,
    CaptchaSolverError,
    build_solver_from_settings,
)

# ---------------------------------------------------------------------------
# Constructor validation
# ---------------------------------------------------------------------------


def test_invalid_backend_raises():
    with pytest.raises(ValueError, match="Unknown captcha backend"):
        CaptchaSolver(backend="unknown_backend", api_key="key123")


def test_empty_api_key_raises():
    with pytest.raises(ValueError, match="api_key must not be empty"):
        CaptchaSolver(backend=BACKEND_ANTICAPTCHA, api_key="")


def test_valid_anticaptcha_init():
    solver = CaptchaSolver(backend=BACKEND_ANTICAPTCHA, api_key="key")
    assert solver.backend == BACKEND_ANTICAPTCHA
    assert "anti-captcha.com" in solver.base_url


def test_valid_capmonster_init():
    solver = CaptchaSolver(backend=BACKEND_CAPMONSTER, api_key="key")
    assert solver.backend == BACKEND_CAPMONSTER
    assert "capmonster.cloud" in solver.base_url


# ---------------------------------------------------------------------------
# _create_task
# ---------------------------------------------------------------------------


def _make_solver():
    return CaptchaSolver(
        backend=BACKEND_ANTICAPTCHA, api_key="testkey", poll_interval=0.01, max_wait=5.0
    )


def test_create_task_success():
    solver = _make_solver()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"errorId": 0, "taskId": 42}
    with patch("requests.post", return_value=mock_resp) as mock_post:
        task_id = solver._create_task({"type": "ImageToTextTask", "body": "abc"})
    assert task_id == 42
    call_args = mock_post.call_args
    assert "createTask" in call_args[0][0]
    assert call_args[1]["json"]["clientKey"] == "testkey"


def test_create_task_api_error():
    solver = _make_solver()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"errorId": 1, "errorDescription": "Invalid key"}
    with (
        patch("requests.post", return_value=mock_resp),
        pytest.raises(CaptchaSolverError, match="Invalid key"),
    ):
        solver._create_task({"type": "ImageToTextTask", "body": "abc"})


def test_create_task_network_error():
    import requests as req_lib

    solver = _make_solver()
    with (
        patch("requests.post", side_effect=req_lib.RequestException("timeout")),
        pytest.raises(CaptchaSolverError, match="createTask request failed"),
    ):
        solver._create_task({"type": "ImageToTextTask", "body": "abc"})


# ---------------------------------------------------------------------------
# _get_task_result
# ---------------------------------------------------------------------------


def test_get_task_result_immediate_ready():
    solver = _make_solver()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "errorId": 0,
        "status": "ready",
        "solution": {"gRecaptchaResponse": "token_abc"},
    }
    with patch("requests.post", return_value=mock_resp):
        solution = solver._get_task_result(99)
    assert solution == {"gRecaptchaResponse": "token_abc"}


def test_get_task_result_polls_until_ready():
    solver = _make_solver()
    processing = MagicMock()
    processing.json.return_value = {"errorId": 0, "status": "processing"}
    ready = MagicMock()
    ready.json.return_value = {
        "errorId": 0,
        "status": "ready",
        "solution": {"text": "SOLVED"},
    }
    with patch("requests.post", side_effect=[processing, processing, ready]):
        solution = solver._get_task_result(1)
    assert solution["text"] == "SOLVED"


def test_get_task_result_timeout():
    solver = CaptchaSolver(
        backend=BACKEND_ANTICAPTCHA, api_key="key", poll_interval=0.01, max_wait=0.01
    )
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"errorId": 0, "status": "processing"}
    with (
        patch("requests.post", return_value=mock_resp),
        pytest.raises(CaptchaSolverError, match="not solved within"),
    ):
        solver._get_task_result(1)


def test_get_task_result_api_error():
    solver = _make_solver()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"errorId": 12, "errorDescription": "Task not found"}
    with (
        patch("requests.post", return_value=mock_resp),
        pytest.raises(CaptchaSolverError, match="Task not found"),
    ):
        solver._get_task_result(1)


# ---------------------------------------------------------------------------
# solve_recaptcha_v2 / solve_image (end-to-end with mocked HTTP)
# ---------------------------------------------------------------------------


def test_solve_recaptcha_v2():
    solver = _make_solver()
    create_resp = MagicMock()
    create_resp.json.return_value = {"errorId": 0, "taskId": 7}
    result_resp = MagicMock()
    result_resp.json.return_value = {
        "errorId": 0,
        "status": "ready",
        "solution": {"gRecaptchaResponse": "recaptcha_token_xyz"},
    }
    with patch("requests.post", side_effect=[create_resp, result_resp]):
        token = solver.solve_recaptcha_v2(site_key="site_key", page_url="https://example.com")
    assert token == "recaptcha_token_xyz"


def test_solve_image():
    solver = _make_solver()
    create_resp = MagicMock()
    create_resp.json.return_value = {"errorId": 0, "taskId": 8}
    result_resp = MagicMock()
    result_resp.json.return_value = {
        "errorId": 0,
        "status": "ready",
        "solution": {"text": "ABC123"},
    }
    with patch("requests.post", side_effect=[create_resp, result_resp]):
        text = solver.solve_image(image_base64="base64data")
    assert text == "ABC123"


def test_capmonster_backend_uses_correct_url():
    solver = CaptchaSolver(
        backend=BACKEND_CAPMONSTER, api_key="key", poll_interval=0.01, max_wait=5.0
    )
    create_resp = MagicMock()
    create_resp.json.return_value = {"errorId": 0, "taskId": 1}
    result_resp = MagicMock()
    result_resp.json.return_value = {
        "errorId": 0,
        "status": "ready",
        "solution": {"gRecaptchaResponse": "t"},
    }
    with patch("requests.post", side_effect=[create_resp, result_resp]) as mock_post:
        solver.solve_recaptcha_v2("key", "https://example.com")
    assert "capmonster.cloud" in mock_post.call_args_list[0][0][0]


# ---------------------------------------------------------------------------
# build_solver_from_settings
# ---------------------------------------------------------------------------


def test_build_solver_no_config():
    mock_settings = MagicMock()
    mock_settings.anti_captcha_provider = ""
    mock_settings.anti_captcha_api_key = ""
    with patch("config.get_settings", return_value=mock_settings):
        assert build_solver_from_settings() is None


def test_build_solver_with_config():
    mock_settings = MagicMock()
    mock_settings.anti_captcha_provider = BACKEND_ANTICAPTCHA
    mock_settings.anti_captcha_api_key = "mykey"
    with patch("config.get_settings", return_value=mock_settings):
        solver = build_solver_from_settings()
    assert solver is not None
    assert solver.backend == BACKEND_ANTICAPTCHA
    assert solver.api_key == "mykey"


def test_build_solver_invalid_backend_logs_warning():
    mock_settings = MagicMock()
    mock_settings.anti_captcha_provider = "invalid_backend"
    mock_settings.anti_captcha_api_key = "key"
    with patch("config.get_settings", return_value=mock_settings):
        result = build_solver_from_settings()
    assert result is None


def test_build_solver_uses_getattr_fallback():
    """build_solver_from_settings should use getattr so missing attrs don't crash."""
    mock_settings = MagicMock(spec=[])  # no attributes defined
    with patch("config.get_settings", return_value=mock_settings):
        result = build_solver_from_settings()
    assert result is None
