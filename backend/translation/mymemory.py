"""MyMemory translation backend — free tier, per-line GET calls.

Free, no auth required. Daily quota is ~1k words anonymously; passing an
email address via config raises the quota to ~10k words/day. Cost is
always zero on the price sheet, but we still emit TranslationEvent rows
for hit counting + dashboards.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import requests

from translation.base import TranslationBackend, TranslationResult
from translation.concurrency import get_concurrency
from translation.cost_tracker import calculate_char_cost_micro_usd
from translation.price_sheet import get_char_price
from translator.events import write_translation_event

logger = logging.getLogger(__name__)

_API_URL = "https://api.mymemory.translated.net/get"


class MyMemoryBackend(TranslationBackend):
    """MyMemory translation API — free tier with optional email for higher quota."""

    name = "mymemory"
    display_name = "MyMemory"
    default_model = ""
    timeout_s = 30
    supports_glossary = False
    supports_batch = True  # we emulate batch via per-line loop
    max_batch_size = 50  # keep small to avoid rate limit

    cost_per_1m_chars = Decimal("0")

    config_fields = [
        {
            "key": "email",
            "type": "text",
            "label": "Email (optional, raises daily quota)",
            "required": False,
        },
    ]

    def __init__(self, email: str | None = None, **_: Any) -> None:
        super().__init__(email=email)
        self.email = email or ""
        self.cost_per_1m_chars = get_char_price(self.name)

    def translate_batch(
        self,
        lines: list[str],
        source_lang: str,
        target_lang: str,
        glossary_entries: list[dict] | None = None,
        series_context: str | None = None,
        *,
        lookback: list[str] | None = None,
        lookahead: list[str] | None = None,
        job_id: str | None = None,
    ) -> TranslationResult:
        """Translate each line via GET request. Free tier has daily quota.

        ``glossary_entries``, ``series_context``, ``lookback`` and
        ``lookahead`` are accepted for interface uniformity but ignored —
        MyMemory's GET contract has no system-prompt concept.
        """
        del glossary_entries, series_context, lookback, lookahead

        started_at = datetime.now(UTC)
        started_mono = time.monotonic()
        status = "ok"
        error_type: str | None = None
        error_msg: str | None = None
        translated_lines: list[str] = []
        chars_in = sum(len(line) for line in lines)
        chars_out: int | None = None

        langpair = f"{source_lang}|{target_lang}"

        try:
            with get_concurrency().slot(self.name, timeout_s=self.timeout_s):
                if job_id:
                    from translation.queue_state import get_queue_state

                    if get_queue_state().is_cancelled(job_id):
                        from translation.llm_base import JobCancelledError

                        raise JobCancelledError(f"Job {job_id} was cancelled")

                for line in lines:
                    params: dict[str, str] = {"q": line, "langpair": langpair}
                    if self.email:
                        params["de"] = self.email
                    resp = requests.get(_API_URL, params=params, timeout=self.timeout_s)
                    resp.raise_for_status()
                    data = resp.json()
                    # Check quota-exceeded / error response
                    if data.get("responseStatus") != 200:
                        err_text = data.get("responseDetails", "MyMemory error")
                        raise RuntimeError(f"MyMemory: {err_text}")
                    translated_lines.append(data.get("responseData", {}).get("translatedText", ""))

                chars_out = sum(len(line) for line in translated_lines)
        except Exception as exc:
            status = "error"
            error_type = type(exc).__name__
            error_msg = str(exc)
            raise
        finally:
            finished_at = datetime.now(UTC)
            latency_ms = int((time.monotonic() - started_mono) * 1000)
            cost = calculate_char_cost_micro_usd(chars_in, self.cost_per_1m_chars)
            write_translation_event(
                backend=self.name,
                source_lang=source_lang,
                target_lang=target_lang,
                lines_count=len(lines),
                chars_in=chars_in,
                chars_out=chars_out,
                cost_micro_usd=cost,
                cache_hit=False,
                started_at=started_at,
                finished_at=finished_at,
                status=status,
                error_type=error_type,
                error_msg=error_msg,
                job_id=job_id,
            )
            self._last_latency_ms = latency_ms

        return TranslationResult(
            translated_lines=translated_lines,
            backend_name=self.name,
            response_time_ms=float(latency_ms),
            characters_used=chars_in,
            success=True,
        )

    def health_check(self) -> tuple[bool, str]:
        """Ping MyMemory with a tiny translate request."""
        try:
            params: dict[str, str] = {"q": "ping", "langpair": "en|de"}
            if self.email:
                params["de"] = self.email
            resp = requests.get(_API_URL, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            if data.get("responseStatus") != 200:
                return False, data.get("responseDetails", "MyMemory error")
            return True, "OK"
        except Exception as exc:
            return False, str(exc)

    def get_config_fields(self) -> list[dict]:
        """Return config field definitions for the Settings UI."""
        return self.config_fields
