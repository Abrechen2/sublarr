"""Plex media server backend -- placeholder for Task 2."""

from mediaserver.base import MediaServer, RefreshResult


class PlexServer(MediaServer):
    """Plex media server backend (stub -- implemented in Task 2)."""

    name = "plex"
    display_name = "Plex"
    config_fields = []

    def health_check(self):
        return False, "Not implemented"

    def refresh_item(self, file_path, item_type=""):
        return RefreshResult(success=False, message="Not implemented")

    def refresh_library(self):
        return RefreshResult(success=False, message="Not implemented")
