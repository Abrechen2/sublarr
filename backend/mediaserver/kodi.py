"""Kodi media server backend using raw JSON-RPC 2.0 over HTTP.

Sends JSON-RPC requests to Kodi's web interface for health checks,
directory-scoped library scans, and full library scans. No external
dependencies beyond the standard requests library.
"""

import logging
import os

import requests

from mediaserver.base import MediaServer, RefreshResult

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 15


class KodiServer(MediaServer):
    """Kodi media server backend via JSON-RPC 2.0."""

    name = "kodi"
    display_name = "Kodi"
    config_fields = [
        {
            "key": "url",
            "label": "Server URL",
            "type": "text",
            "required": True,
            "default": "http://localhost:8080",
            "help": "Kodi web interface URL (enable 'Allow remote control via HTTP' in Kodi settings)",
        },
        {
            "key": "username",
            "label": "Username",
            "type": "text",
            "required": False,
            "default": "",
            "help": "HTTP Basic Auth username (if enabled in Kodi web server settings)",
        },
        {
            "key": "password",
            "label": "Password",
            "type": "password",
            "required": False,
            "default": "",
            "help": "HTTP Basic Auth password",
        },
        {
            "key": "path_mapping",
            "label": "Path Mapping",
            "type": "text",
            "required": False,
            "default": "",
            "help": "from_path:to_path for Docker volume mapping (e.g. /media:/data)",
        },
    ]

    def __init__(self, **config):
        super().__init__(**config)
        self.url = config.get("url", "http://localhost:8080").rstrip("/")
        self.username = config.get("username", "")
        self.password = config.get("password", "")

    def _rpc(self, method: str, params=None):
        """Send a JSON-RPC 2.0 POST request to Kodi.

        Args:
            method: JSON-RPC method name (e.g. "JSONRPC.Ping")
            params: Optional dict of method parameters

        Returns:
            The "result" field from the JSON-RPC response

        Raises:
            Exception: On connection error, auth failure, or RPC error
        """
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "id": 1,
        }
        if params is not None:
            payload["params"] = params

        auth = (self.username, self.password) if self.username else None

        resp = requests.post(
            f"{self.url}/jsonrpc",
            json=payload,
            headers={"Content-Type": "application/json"},
            auth=auth,
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        result = resp.json()

        if "error" in result:
            error = result["error"]
            msg = error.get("message", str(error)) if isinstance(error, dict) else str(error)
            raise Exception(f"Kodi RPC error: {msg}")

        return result.get("result")

    def health_check(self) -> tuple[bool, str]:
        """Check if Kodi is reachable via JSON-RPC.

        Sends JSONRPC.Ping (expects "pong") and Application.GetProperties
        for version info.

        Returns:
            (is_healthy, message) tuple
        """
        try:
            ping = self._rpc("JSONRPC.Ping")
            if ping != "pong":
                return False, f"Kodi ping returned unexpected result: {ping}"
        except requests.ConnectionError:
            return False, (
                f"Cannot connect to Kodi at {self.url}. "
                "Ensure 'Allow remote control via HTTP' is enabled in Kodi settings."
            )
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 401:
                return False, "Kodi authentication failed (check username/password)"
            return False, f"Kodi HTTP error: {e}"
        except Exception as e:
            return False, f"Kodi health check failed: {e}"

        # Get version info for display
        try:
            props = self._rpc(
                "Application.GetProperties",
                {"properties": ["name", "version"]},
            )
            if props:
                name = props.get("name", "Kodi")
                version = props.get("version", {})
                major = version.get("major", "?")
                minor = version.get("minor", "?")
                return True, f"{name} v{major}.{minor}"
        except Exception:
            pass

        return True, "Kodi (version unknown)"

    def refresh_item(self, file_path: str, item_type: str = "") -> RefreshResult:
        """Refresh a specific item by scanning its parent directory.

        Kodi's VideoLibrary.Scan with a directory parameter scans just
        that directory, which is more targeted than a full library scan.

        Args:
            file_path: Path to the media file
            item_type: "episode" or "movie" hint (not used for Kodi)

        Returns:
            RefreshResult with success status
        """
        mapped_path = self.apply_path_mapping(file_path)
        parent_dir = os.path.dirname(mapped_path)
        # Kodi expects trailing slash on directory paths
        if not parent_dir.endswith("/"):
            parent_dir += "/"

        try:
            self._rpc("VideoLibrary.Scan", {"directory": parent_dir})
            logger.info("Triggered Kodi directory scan: %s", parent_dir)
            return RefreshResult(
                success=True,
                message=f"Directory scan triggered: {parent_dir}",
                server_name=self.config.get("name", self.display_name),
            )
        except requests.ConnectionError:
            return RefreshResult(
                success=False,
                message=f"Cannot connect to Kodi at {self.url}",
                server_name=self.config.get("name", self.display_name),
            )
        except Exception as e:
            logger.warning("Kodi directory scan failed: %s", e)
            return RefreshResult(
                success=False,
                message=f"Kodi directory scan failed: {e}",
                server_name=self.config.get("name", self.display_name),
            )

    def refresh_library(self) -> RefreshResult:
        """Trigger a full video library scan.

        Returns:
            RefreshResult with success status
        """
        try:
            self._rpc("VideoLibrary.Scan")
            logger.info("Triggered Kodi full video library scan")
            return RefreshResult(
                success=True,
                message="Full video library scan triggered",
                server_name=self.config.get("name", self.display_name),
            )
        except Exception as e:
            return RefreshResult(
                success=False,
                message=f"Kodi full library scan failed: {e}",
                server_name=self.config.get("name", self.display_name),
            )
