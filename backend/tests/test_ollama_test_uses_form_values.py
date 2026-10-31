"""The Ollama test checks the values in the form and reports failure as failure.

Audit #61 A10: the setup wizard ignored the URL and model it showed, read the
health text as "fine unless it contains 'error'", and so showed "Cannot
connect to Ollama" or a missing model in green.
"""

from unittest.mock import MagicMock, patch

import requests


def _tags(*models):
    return MagicMock(status_code=200, json=lambda: {"models": [{"name": m} for m in models]})


def test_the_form_url_and_model_are_tested(client):
    with patch("ollama_client.requests.get", return_value=_tags("llama3:8b")) as get:
        body = client.post(
            "/api/v1/backends/test/ollama",
            json={"url": "http://192.168.10.9:11434", "model": "llama3"},
        ).get_json()

    assert body["healthy"] is True
    assert get.call_args.args[0] == "http://192.168.10.9:11434/api/tags"


def test_an_unreachable_ollama_is_unhealthy(client):
    with patch("ollama_client.requests.get", side_effect=requests.ConnectionError()):
        body = client.post(
            "/api/v1/backends/test/ollama", json={"url": "http://192.168.10.9:11434"}
        ).get_json()

    assert body["healthy"] is False
    assert "Cannot connect" in body["message"]


def test_a_missing_model_is_unhealthy(client):
    with patch("ollama_client.requests.get", return_value=_tags("mistral:7b")):
        body = client.post(
            "/api/v1/backends/test/ollama",
            json={"url": "http://192.168.10.9:11434", "model": "qwen2.5:14b"},
        ).get_json()

    assert body["healthy"] is False


def test_a_metadata_url_is_refused_without_a_request(client):
    with patch("ollama_client.requests.get") as get:
        body = client.post(
            "/api/v1/backends/test/ollama", json={"url": "http://169.254.169.254/"}
        ).get_json()

    assert body["healthy"] is False
    get.assert_not_called()
