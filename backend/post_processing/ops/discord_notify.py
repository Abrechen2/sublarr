"""Discord webhook notification op (Plan B6)."""

from __future__ import annotations

import time
from pathlib import Path

import requests

from post_processing.base_op import BaseOp, OpResult, register_op

_DISCORD_PREFIX = "https://discord.com/api/webhooks/"


def _elapsed_ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)


@register_op
class DiscordNotifyOp(BaseOp):
    op_id = "discord_notify"
    label = "Discord Notification"
    description = (
        "Send a Discord notification when a subtitle is processed. "
        "Requires a Discord webhook URL."
    )

    webhook_url: str = ""

    def execute(self, context: dict) -> OpResult:
        start = time.monotonic()

        if not self.webhook_url:
            return OpResult(self.op_id, False, 0, "no webhook_url")

        if not self.webhook_url.startswith(_DISCORD_PREFIX):
            return OpResult(self.op_id, False, 0, "invalid discord webhook url")

        subtitle_name = Path(context.get("subtitle_path", "")).name or "subtitle"
        video_name = Path(context.get("video_path", "")).name or "video"
        lang = context.get("lang", "?")
        score = context.get("score", "?")
        trigger = context.get("trigger", "after_download")

        payload = {
            "content": (
                f"Sublarr `{trigger}`: `{subtitle_name}` for `{video_name}` "
                f"({lang}, score={score})"
            )
        }

        try:
            resp = requests.post(self.webhook_url, json=payload, timeout=10)
            if resp.status_code >= 400:
                return OpResult(
                    self.op_id, False, _elapsed_ms(start), f"http {resp.status_code}"
                )
            return OpResult(self.op_id, True, _elapsed_ms(start), "notified")
        except Exception as exc:
            return OpResult(self.op_id, False, _elapsed_ms(start), str(exc))
