"""Azure Translator backend — char-priced REST API.

Inherits TranslationBackend directly (NOT LLMBackend): no token usage,
no prompt assembly, no line-count retry. We still emit TranslationEvent
rows and acquire a concurrency slot manually so char-priced backends
show up uniformly in metrics + queue dashboards.
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

_API_URL = "https://api.cognitive.microsofttranslator.com/translate"


class AzureTranslatorBackend(TranslationBackend):
    """Azure Cognitive Services Translator — char-priced."""

    name = "azure_translator"
    display_name = "Azure Translator"
    default_model = ""
    timeout_s = 60
    supports_glossary = False  # Azure has a separate glossary API we don't use
    supports_batch = True
    max_batch_size = 100

    cost_per_1m_chars = Decimal("10.00")

    config_fields = [
        {
            "key": "api_key",
            "type": "password",
            "label": "Subscription Key",
            "required": True,
        },
        {
            "key": "region",
            "type": "text",
            "label": "Region",
            "required": False,
            "default": "westeurope",
        },
    ]

    def __init__(
        self,
        api_key: str = "",
        region: str | None = None,
        **_: Any,
    ) -> None:
        if not api_key:
            raise ValueError("AzureTranslatorBackend: api_key is required")
        super().__init__(api_key=api_key, region=region)
        self.api_key = api_key
        self.region = region or "westeurope"
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
        """Translate via Azure REST API. Char-priced, non-LLM.

        ``glossary_entries``, ``series_context``, ``lookback`` and
        ``lookahead`` are accepted for interface uniformity but ignored —
        Azure's REST contract has no system-prompt concept.
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

        try:
            with get_concurrency().slot(self.name, timeout_s=self.timeout_s):
                # Check cancel before spending API budget
                if job_id:
                    from translation.queue_state import get_queue_state

                    if get_queue_state().is_cancelled(job_id):
                        from translation.llm_base import JobCancelledError

                        raise JobCancelledError(f"Job {job_id} was cancelled")

                resp = requests.post(
                    f"{_API_URL}?api-version=3.0&to={target_lang}&from={source_lang}",
                    headers={
                        "Ocp-Apim-Subscription-Key": self.api_key,
                        "Ocp-Apim-Subscription-Region": self.region,
                        "Content-Type": "application/json",
                    },
                    json=[{"text": line} for line in lines],
                    timeout=self.timeout_s,
                )
                resp.raise_for_status()
                data = resp.json()

                translated_lines = [item["translations"][0]["text"] for item in data]
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
        """Ping Azure with a tiny translate request."""
        try:
            resp = requests.post(
                f"{_API_URL}?api-version=3.0&to=de&from=en",
                headers={
                    "Ocp-Apim-Subscription-Key": self.api_key,
                    "Ocp-Apim-Subscription-Region": self.region,
                    "Content-Type": "application/json",
                },
                json=[{"text": "ping"}],
                timeout=10,
            )
            resp.raise_for_status()
            return True, "OK"
        except Exception as exc:
            return False, str(exc)

    def get_config_fields(self) -> list[dict]:
        """Return config field definitions for the Settings UI."""
        return self.config_fields
