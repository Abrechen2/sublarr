"""Shoko Server media-server backend.

Shoko is an AniDB-backed anime collection manager. As a *media server* in
Sublarr's sense it plays the same role as Jellyfin/Plex/Kodi: after Sublarr
writes a subtitle next to a video, we tell Shoko to rescan that file so it
picks up the new external subtitle.

The heavy lifting lives in ``metadata.shoko_client.ShokoClient`` — this class
is a thin MediaServer ABC adapter over it, so the same config powers both the
rescan role here and the authoritative AniDB lookups in the wanted-search
enricher chain.
"""

import logging

from mediaserver.base import MediaServer, RefreshResult

logger = logging.getLogger(__name__)


class ShokoServer(MediaServer):
    """Shoko Server v3 backend (rescan-after-download)."""

    name = "shoko"
    display_name = "Shoko Server"
    config_fields = [
        {
            "key": "url",
            "label": "Server URL",
            "type": "text",
            "required": True,
            "default": "http://localhost:8111",
            "help": "Shoko Server URL (e.g. http://192.168.1.100:8111)",
        },
        {
            "key": "api_key",
            "label": "API Key",
            "type": "password",
            "required": False,
            "default": "",
            "help": "Persistent Shoko API key. Leave blank to use username/password instead.",
        },
        {
            "key": "username",
            "label": "Username",
            "type": "text",
            "required": False,
            "default": "",
            "help": "Shoko username (only needed when no API key is set)",
        },
        {
            "key": "password",
            "label": "Password",
            "type": "password",
            "required": False,
            "default": "",
            "help": "Shoko password (only needed when no API key is set)",
        },
        {
            "key": "path_mapping",
            "label": "Path Mapping",
            "type": "text",
            "required": False,
            "default": "",
            "help": "from_path:to_path if Sublarr and Shoko see the media under "
            "different roots (e.g. /media:/data). Leave blank if the paths match.",
        },
    ]

    def __init__(self, **config):
        super().__init__(**config)
        self.url = str(config.get("url", "http://localhost:8111")).rstrip("/")
        self.api_key = config.get("api_key", "")
        self.username = config.get("username", "")
        self.password = config.get("password", "")

    def _client(self):
        from metadata.shoko_client import ShokoClient

        return ShokoClient(
            url=self.url,
            api_key=self.api_key,
            username=self.username,
            password=self.password,
        )

    def health_check(self) -> tuple[bool, str]:
        return self._client().health_check()

    def refresh_item(self, file_path: str, item_type: str = "") -> RefreshResult:
        """Rescan the Shoko file matching ``file_path``.

        Falls back to a full import-folder scan when the file is unknown to
        Shoko (e.g. path-mapping mismatch or not yet imported).
        """
        mapped_path = self.apply_path_mapping(file_path)
        server_name = self.config.get("name", self.display_name)
        try:
            client = self._client()
            if client.rescan_file_by_path(mapped_path):
                type_str = f" ({item_type})" if item_type else ""
                logger.info("Triggered Shoko rescan for %s%s", mapped_path, type_str)
                return RefreshResult(
                    success=True,
                    message=f"Rescanned {mapped_path}{type_str}",
                    server_name=server_name,
                )
            logger.info("File not found in Shoko, falling back to library scan: %s", mapped_path)
            return self.refresh_library()
        except Exception as e:  # noqa: BLE001 — refresh is best-effort
            return RefreshResult(
                success=False,
                message=f"Shoko rescan failed: {e}",
                server_name=server_name,
            )

    def refresh_library(self) -> RefreshResult:
        server_name = self.config.get("name", self.display_name)
        try:
            if self._client().refresh_library():
                logger.info("Triggered Shoko import-folder scan")
                return RefreshResult(
                    success=True,
                    message="Import-folder scan triggered on Shoko",
                    server_name=server_name,
                )
        except Exception as e:  # noqa: BLE001
            return RefreshResult(
                success=False,
                message=f"Shoko library scan failed: {e}",
                server_name=server_name,
            )
        return RefreshResult(
            success=False,
            message="Failed to trigger import-folder scan on Shoko",
            server_name=server_name,
        )
