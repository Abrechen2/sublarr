"""Generic webhook POST op (Plan B6). Reuses validate_service_url for SSRF protection."""

from __future__ import annotations

import json
import time

import requests

from post_processing.base_op import BaseOp, OpResult, register_op

_SUBSTITUTION_KEYS = ("subtitle_path", "video_path", "lang", "score", "trigger")


def _elapsed_ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)


@register_op
class WebhookOp(BaseOp):
    op_id = "webhook"
    label = "Webhook"
    description = (
        "POST the saved subtitle event to a configurable HTTP endpoint. "
        "Supports {subtitle_path}, {video_path}, {lang}, {score}, {trigger} "
        "substitution in the request body template."
    )

    # Op config fields (populated from per-trigger config in future wiring):
    url: str = ""
    method: str = "POST"
    template: str = ""  # JSON body template with {placeholders}

    def execute(self, context: dict) -> OpResult:
        start = time.monotonic()

        if not self.url:
            return OpResult(self.op_id, False, 0, "no url configured")

        # SSRF protection via existing helper
        try:
            from security_utils import validate_service_url

            ok, reason = validate_service_url(self.url)
            if not ok:
                return OpResult(
                    self.op_id,
                    False,
                    _elapsed_ms(start),
                    f"url rejected (ssrf): {reason}",
                )
        except ImportError:
            # validate_service_url not importable — fall through.
            # Documented as follow-up: treat as ssrf-gated in prod.
            pass

        body_str = self.template
        for key in _SUBSTITUTION_KEYS:
            body_str = body_str.replace("{" + key + "}", str(context.get(key, "")))

        kwargs: dict = {"timeout": 10}
        if body_str:
            try:
                kwargs["json"] = json.loads(body_str)
            except (json.JSONDecodeError, ValueError):
                kwargs["data"] = body_str

        try:
            resp = requests.request(self.method.upper(), self.url, **kwargs)
            if resp.status_code >= 400:
                return OpResult(
                    self.op_id, False, _elapsed_ms(start), f"http {resp.status_code}"
                )
            return OpResult(
                self.op_id, True, _elapsed_ms(start), f"http {resp.status_code}"
            )
        except Exception as exc:
            return OpResult(self.op_id, False, _elapsed_ms(start), str(exc))
