"""HTTP client wrapper for the Sublarr REST API."""
import requests


class SublarrAPIError(Exception):
    """Raised when the Sublarr API returns an error or is unreachable."""


class SublarrClient:
    def __init__(self, url: str, api_key: str = "") -> None:
        self.base = url.rstrip("/") + "/api/v1"
        self._api_key = api_key
        self._session = requests.Session()

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self._api_key:
            h["X-Api-Key"] = self._api_key
        return h

    def get(self, path: str, params: dict = None) -> dict:
        url = self.base + path
        try:
            resp = self._session.get(url, params=params, headers=self._headers(), timeout=30)
        except requests.ConnectionError:
            raise SublarrAPIError(f"Cannot connect to Sublarr at {self.base}. Is it running?")
        if not resp.ok:
            msg = resp.json().get("error", resp.text) if resp.content else resp.reason
            raise SublarrAPIError(f"API error {resp.status_code}: {msg}")
        return resp.json()

    def post(self, path: str, json: dict = None) -> dict:
        url = self.base + path
        try:
            resp = self._session.post(url, json=json or {}, headers=self._headers(), timeout=60)
        except requests.ConnectionError:
            raise SublarrAPIError(f"Cannot connect to Sublarr at {self.base}. Is it running?")
        if not resp.ok:
            msg = resp.json().get("error", resp.text) if resp.content else resp.reason
            raise SublarrAPIError(f"API error {resp.status_code}: {msg}")
        return resp.json()
