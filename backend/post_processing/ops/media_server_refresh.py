"""Media server refresh ops — Plex, Emby, Jellyfin library scan triggers (Plan B6)."""

from __future__ import annotations

import time

import requests

from post_processing.base_op import BaseOp, OpResult, register_op


def _elapsed_ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)


@register_op
class PlexRefreshOp(BaseOp):
    op_id = "plex_refresh"
    label = "Plex — Refresh Library"
    description = (
        "Trigger a Plex library section scan so new subtitles are picked up immediately."
    )

    base_url: str = ""
    token: str = ""
    section_id: str = ""  # optional: target a specific library section

    def execute(self, context: dict) -> OpResult:
        start = time.monotonic()
        if not self.base_url or not self.token:
            return OpResult(self.op_id, False, 0, "plex not configured")

        section = self.section_id or "all"
        url = f"{self.base_url.rstrip('/')}/library/sections/{section}/refresh"
        try:
            resp = requests.get(
                url, headers={"X-Plex-Token": self.token}, timeout=10
            )
            if resp.status_code >= 400:
                return OpResult(
                    self.op_id, False, _elapsed_ms(start), f"http {resp.status_code}"
                )
            return OpResult(
                self.op_id, True, _elapsed_ms(start), "plex refresh triggered"
            )
        except Exception as exc:
            return OpResult(self.op_id, False, _elapsed_ms(start), str(exc))


@register_op
class EmbyRefreshOp(BaseOp):
    op_id = "emby_refresh"
    label = "Emby — Refresh Library"
    description = "Trigger an Emby library scan."

    base_url: str = ""
    api_key: str = ""

    def execute(self, context: dict) -> OpResult:
        start = time.monotonic()
        if not self.base_url or not self.api_key:
            return OpResult(self.op_id, False, 0, "emby not configured")

        url = f"{self.base_url.rstrip('/')}/Library/Refresh"
        try:
            resp = requests.post(url, params={"api_key": self.api_key}, timeout=10)
            if resp.status_code >= 400:
                return OpResult(
                    self.op_id, False, _elapsed_ms(start), f"http {resp.status_code}"
                )
            return OpResult(
                self.op_id, True, _elapsed_ms(start), "emby refresh triggered"
            )
        except Exception as exc:
            return OpResult(self.op_id, False, _elapsed_ms(start), str(exc))


@register_op
class JellyfinRefreshOp(BaseOp):
    op_id = "jellyfin_refresh"
    label = "Jellyfin — Refresh Library"
    description = "Trigger a Jellyfin library scan."

    base_url: str = ""
    api_key: str = ""

    def execute(self, context: dict) -> OpResult:
        start = time.monotonic()
        if not self.base_url or not self.api_key:
            return OpResult(self.op_id, False, 0, "jellyfin not configured")

        url = f"{self.base_url.rstrip('/')}/Library/Refresh"
        try:
            resp = requests.post(
                url, headers={"X-MediaBrowser-Token": self.api_key}, timeout=10
            )
            if resp.status_code >= 400:
                return OpResult(
                    self.op_id, False, _elapsed_ms(start), f"http {resp.status_code}"
                )
            return OpResult(
                self.op_id, True, _elapsed_ms(start), "jellyfin refresh triggered"
            )
        except Exception as exc:
            return OpResult(self.op_id, False, _elapsed_ms(start), str(exc))
