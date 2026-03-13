from unittest.mock import MagicMock, patch

import pytest

from cli.client import SublarrAPIError, SublarrClient


class TestSublarrClient:
    def setup_method(self):
        self.client = SublarrClient("http://localhost:5765")

    def test_get_success(self):
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {"jobs": [], "total": 0}
        with patch("cli.client.requests.Session.get", return_value=mock_resp):
            result = self.client.get("/jobs")
        assert result == {"jobs": [], "total": 0}

    def test_get_with_api_key_sets_header(self):
        client = SublarrClient("http://localhost:5765", api_key="secret")
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {}
        with patch("cli.client.requests.Session.get", return_value=mock_resp) as mock_get:
            client.get("/health")
        assert mock_get.call_args.kwargs["headers"]["X-Api-Key"] == "secret"

    def test_post_success(self):
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {"status": "started"}
        with patch("cli.client.requests.Session.post", return_value=mock_resp):
            result = self.client.post("/wanted/batch-search", json={"item_ids": [1, 2]})
        assert result == {"status": "started"}

    def test_api_error_raises(self):
        mock_resp = MagicMock()
        mock_resp.ok = False
        mock_resp.status_code = 404
        mock_resp.json.return_value = {"error": "Not found"}
        with (
            patch("cli.client.requests.Session.get", return_value=mock_resp),
            pytest.raises(SublarrAPIError) as exc_info,
        ):
            self.client.get("/wanted/99/search")
        assert "Not found" in str(exc_info.value)

    def test_connection_error_raises(self):
        import requests as req

        with (
            patch("cli.client.requests.Session.get", side_effect=req.ConnectionError("refused")),
            pytest.raises(SublarrAPIError) as exc_info,
        ):
            self.client.get("/health")
        assert "Cannot connect" in str(exc_info.value)
