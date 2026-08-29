"""LLMBackend — base class for LLM-based translation backends.

Subclasses override three hooks (_build_request / _call_api / _parse_response).
Base class handles: concurrency acquisition, prompt assembly, retry-on-line-
count-mismatch, cost tracking, event logging.

Non-LLM backends (DeepL, Google, LibreTranslate) continue to inherit
TranslationBackend directly — the LLM-specific concerns don't apply.
"""

from __future__ import annotations

import logging
import time
from abc import abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from translation.base import TranslationBackend, TranslationContentError, TranslationResult
from translation.concurrency import ConcurrencyTimeoutError, get_concurrency
from translation.cost_tracker import calculate_llm_cost_micro_usd
from translation.llm_utils import find_line_shift, repair_line_mapping, strip_invented_hard_breaks
from translation.prompt_safety import enforce_batch_size, escape_for_prompt
from translator.events import write_translation_event

logger = logging.getLogger(__name__)


class LineCountMismatchError(TranslationContentError, ValueError):
    """LLM returned wrong number of lines for the batch after retry."""


class LineMisalignmentError(TranslationContentError, ValueError):
    """LLM returned the right number of lines, but against the wrong sources."""


class ContentFilterError(TranslationContentError, RuntimeError):
    """LLM refused the request (finish_reason == 'content_filter')."""


class JobCancelledError(RuntimeError):
    """Raised when a batch is skipped due to a cancel request on its job."""


@dataclass
class LLMResponse:
    """Parsed response from an LLM backend's _parse_response hook.

    ``cache_read_tokens`` and ``cache_write_tokens`` (default 0) are used by
    prompt-caching backends like Anthropic Claude:
      - cache_read: billed at ~0.1× the fresh-input rate
      - cache_write: billed at ~1.25× the fresh-input rate
    Non-caching backends leave them at 0 and the cost math reduces to the
    usual ``tokens_in * price_in``.
    """

    translations: list[str]
    tokens_in: int
    tokens_out: int
    model: str
    finish_reason: str | None
    raw_latency_ms: int
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


class LLMBackend(TranslationBackend):
    """Base class for LLM translation backends.

    Subclasses must override three hooks:
      * ``_build_request(messages, max_tokens) -> dict``
      * ``_call_api(payload, timeout_s) -> dict``
      * ``_parse_response(raw) -> LLMResponse``

    They must also declare the class-level pricing + default model:
      * ``cost_per_1m_tokens_in: Decimal``
      * ``cost_per_1m_tokens_out: Decimal``
      * ``default_model: str``

    Subclasses MUST NOT override :meth:`translate_batch` — the shared
    orchestration (concurrency slot, retry, cost, event write) lives here.
    """

    # Subclass must declare:
    cost_per_1m_tokens_in: Decimal = Decimal("0")
    cost_per_1m_tokens_out: Decimal = Decimal("0")
    default_model: str = ""
    timeout_s: int = 120

    @abstractmethod
    def _build_request(self, messages: list[dict], max_tokens: int) -> dict:
        """Build provider-specific HTTP request payload."""
        ...

    @abstractmethod
    def _call_api(self, payload: dict, timeout_s: int) -> dict:
        """Execute the HTTP call. Returns raw JSON. Raises on network/HTTP errors."""
        ...

    @abstractmethod
    def _parse_response(self, raw: dict) -> LLMResponse:
        """Extract translations + token counts from provider response."""
        ...

    # --- Base implementations ---

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
        """Orchestrate: concurrency + API call + cost tracking + event write.

        Raises on API errors — the caller's fallback chain is responsible for
        falling back to a different backend. The ``TranslationResult`` returned
        on success always has ``success=True``; partial failures surface as
        exceptions so the manager can route the batch to a fallback backend.

        The keyword-only ``lookback`` and ``lookahead`` arguments (Phase A4)
        attach surrounding subtitle lines as context for pronoun resolution
        and narrative coherence across batch boundaries. They are forwarded
        to :meth:`_attempt` → :meth:`_assemble_messages`.
        """
        started_at = datetime.now(UTC)
        started_mono = time.monotonic()
        status = "ok"
        error_type: str | None = None
        error_msg: str | None = None
        resp: LLMResponse | None = None
        chars_in = sum(len(line) for line in lines)

        # P3: cap batch size before any cost is incurred. A compromised
        # subtitle provider that emits 100k lines or a 10MB single line
        # is rejected here, surfaces as PromptBatchTooLargeError, and
        # never reaches the model.
        enforce_batch_size(lines)

        try:
            with get_concurrency().slot(self.name, timeout_s=self.timeout_s):
                # Check cancel flag before spending API budget
                if job_id:
                    from translation.queue_state import get_queue_state

                    if get_queue_state().is_cancelled(job_id):
                        raise JobCancelledError(f"Job {job_id} was cancelled")
                resp = self._attempt(
                    lines,
                    source_lang,
                    target_lang,
                    glossary_entries,
                    series_context,
                    lookback=lookback,
                    lookahead=lookahead,
                )
                resp = self._verify_line_count(
                    resp,
                    lines,
                    source_lang,
                    target_lang,
                    glossary_entries,
                    series_context,
                    lookback=lookback,
                    lookahead=lookahead,
                )
                resp = self._verify_line_alignment(
                    resp,
                    lines,
                    source_lang,
                    target_lang,
                    glossary_entries,
                    series_context,
                    lookback=lookback,
                    lookahead=lookahead,
                )
        except ConcurrencyTimeoutError as exc:
            status = "timeout"
            error_type = "ConcurrencyTimeout"
            error_msg = str(exc)
            raise
        except ContentFilterError as exc:
            status = "error"
            error_type = "ContentFilterError"
            error_msg = str(exc)
            raise
        except LineCountMismatchError as exc:
            status = "error"
            error_type = "LineCountMismatchError"
            error_msg = str(exc)
            raise
        except LineMisalignmentError as exc:
            status = "error"
            error_type = "LineMisalignmentError"
            error_msg = str(exc)
            raise
        except JobCancelledError as exc:
            status = "cancelled"
            error_type = "JobCancelledError"
            error_msg = str(exc)
            raise
        except Exception as exc:
            status = "error"
            error_type = type(exc).__name__
            error_msg = str(exc)
            raise
        finally:
            finished_at = datetime.now(UTC)
            # Monotonic clock gives ms-accurate latency on Windows (wall-clock
            # datetime has ~15 ms resolution). Stored on the result for callers
            # that still use ``response_time_ms``; event latency is computed
            # from started_at/finished_at inside write_translation_event.
            latency_ms_mono = int((time.monotonic() - started_mono) * 1000)

            cost = 0
            if resp is not None:
                cost = calculate_llm_cost_micro_usd(
                    tokens_in=resp.tokens_in,
                    tokens_out=resp.tokens_out,
                    price_in_per_1m=self.cost_per_1m_tokens_in,
                    price_out_per_1m=self.cost_per_1m_tokens_out,
                    cache_read_tokens=resp.cache_read_tokens,
                    cache_write_tokens=resp.cache_write_tokens,
                )

            chars_out_val: int | None = None
            if resp is not None:
                chars_out_val = sum(len(t) for t in resp.translations) or None

            write_translation_event(
                backend=self.name,
                source_lang=source_lang,
                target_lang=target_lang,
                lines_count=len(lines),
                chars_in=chars_in,
                chars_out=chars_out_val,
                tokens_in=resp.tokens_in if resp else None,
                tokens_out=resp.tokens_out if resp else None,
                cost_micro_usd=cost,
                cache_hit=False,
                started_at=started_at,
                finished_at=finished_at,
                status=status,
                error_type=error_type,
                error_msg=error_msg,
            )

            # Expose monotonic latency on the instance so tests/metrics can
            # inspect even when an exception short-circuited the return path.
            self._last_latency_ms = latency_ms_mono

        # resp is guaranteed non-None here — any exception path raised above
        assert resp is not None
        return TranslationResult(
            # Models like to append a hard line break the source never had.
            # The line count still matches, so nothing downstream would catch
            # it — but the subtitle renders differently from the original.
            translated_lines=strip_invented_hard_breaks(lines, list(resp.translations)),
            backend_name=self.name,
            response_time_ms=float(latency_ms_mono),
            characters_used=chars_in,
            success=True,
        )

    def _attempt(
        self,
        lines: list[str],
        source_lang: str,
        target_lang: str,
        glossary_entries: list[dict] | None,
        series_context: str | None = None,
        is_retry: bool = False,
        *,
        lookback: list[str] | None = None,
        lookahead: list[str] | None = None,
    ) -> LLMResponse:
        """Build + call + parse once. Used by :meth:`translate_batch`."""
        messages = self._assemble_messages(
            lines,
            source_lang,
            target_lang,
            glossary_entries,
            series_context=series_context,
            strict=is_retry,
            lookback=lookback,
            lookahead=lookahead,
        )
        payload = self._build_request(messages, max_tokens=self._estimate_max_tokens(lines))
        raw = self._call_api(payload, timeout_s=self.timeout_s)
        resp = self._parse_response(raw)
        # Every LLM backend passes through here, which is why the repair lives
        # at this level rather than in each ``_parse_response``: ChatGPT and
        # Claude never stripped output numbering at all, so a prompt that asks
        # for numbers would otherwise write digits into their subtitles.
        resp.translations = repair_line_mapping(resp.translations)
        if resp.finish_reason == "content_filter":
            raise ContentFilterError(f"{self.name} refused with finish_reason=content_filter")
        return resp

    def _verify_line_count(
        self,
        resp: LLMResponse,
        lines: list[str],
        source_lang: str,
        target_lang: str,
        glossary_entries: list[dict] | None,
        series_context: str | None = None,
        *,
        lookback: list[str] | None = None,
        lookahead: list[str] | None = None,
    ) -> LLMResponse:
        """Retry once on line-count mismatch; raise if still wrong.

        Returns the (possibly retried) response. On retry the token counts of
        the initial + retry attempts are summed so the event row reflects
        true spend.
        """
        if len(resp.translations) == len(lines):
            return resp

        logger.warning(
            "%s returned %d lines, expected %d — retrying with strict prompt",
            self.name,
            len(resp.translations),
            len(lines),
        )
        resp_retry = self._attempt(
            lines,
            source_lang,
            target_lang,
            glossary_entries,
            series_context=series_context,
            is_retry=True,
            lookback=lookback,
            lookahead=lookahead,
        )
        if len(resp_retry.translations) != len(lines):
            # Sum tokens so the error-case event captures full spend
            resp.tokens_in = resp.tokens_in + resp_retry.tokens_in
            resp.tokens_out = resp.tokens_out + resp_retry.tokens_out
            resp.cache_read_tokens = resp.cache_read_tokens + resp_retry.cache_read_tokens
            resp.cache_write_tokens = resp.cache_write_tokens + resp_retry.cache_write_tokens
            raise LineCountMismatchError(
                f"{self.name} returned {len(resp_retry.translations)} "
                f"lines after retry, expected {len(lines)}"
            )

        # Replace with retry response but sum tokens (we paid for both attempts)
        resp_retry.tokens_in = resp.tokens_in + resp_retry.tokens_in
        resp_retry.tokens_out = resp.tokens_out + resp_retry.tokens_out
        resp_retry.cache_read_tokens = resp.cache_read_tokens + resp_retry.cache_read_tokens
        resp_retry.cache_write_tokens = resp.cache_write_tokens + resp_retry.cache_write_tokens
        return resp_retry

    def _verify_line_alignment(
        self,
        resp: LLMResponse,
        lines: list[str],
        source_lang: str,
        target_lang: str,
        glossary_entries: list[dict] | None,
        series_context: str | None = None,
        *,
        lookback: list[str] | None = None,
        lookahead: list[str] | None = None,
    ) -> LLMResponse:
        """Retry once when the lines came back against the wrong sources.

        The count can be right while the mapping is not: the model splits one
        line in two and merges two others further down, so the total matches
        and every line in between belongs to a different subtitle event. It
        renders as dialogue running out of sync, and because an accepted batch
        is written to the translation memory it would be served again on every
        later hit.

        Treated exactly like a count mismatch — one strict retry, and a
        :class:`TranslationContentError` if that does not fix it. The backend
        answered, so this must not count against its circuit breaker, and the
        batching layer halves a batch it cannot deliver rather than ending the
        file, so a rejection here costs the batch a retry, not the episode.
        """
        shift = find_line_shift(lines, list(resp.translations))
        if shift is None:
            return resp

        logger.warning(
            "%s returned %d lines shifted by %+d against their sources — "
            "retrying with strict prompt",
            self.name,
            len(lines),
            shift,
        )
        resp_retry = self._attempt(
            lines,
            source_lang,
            target_lang,
            glossary_entries,
            series_context=series_context,
            is_retry=True,
            lookback=lookback,
            lookahead=lookahead,
        )
        # Sum onto the response the caller is still holding as well: when this
        # method raises, that is the one the event row is written from, and it
        # would otherwise report a single attempt's spend for two.
        resp.tokens_in += resp_retry.tokens_in
        resp.tokens_out += resp_retry.tokens_out
        resp.cache_read_tokens += resp_retry.cache_read_tokens
        resp.cache_write_tokens += resp_retry.cache_write_tokens
        resp_retry.tokens_in = resp.tokens_in
        resp_retry.tokens_out = resp.tokens_out
        resp_retry.cache_read_tokens = resp.cache_read_tokens
        resp_retry.cache_write_tokens = resp.cache_write_tokens

        if len(resp_retry.translations) != len(lines):
            raise LineCountMismatchError(
                f"{self.name} returned {len(resp_retry.translations)} lines after an "
                f"alignment retry, expected {len(lines)}"
            )
        retry_shift = find_line_shift(lines, list(resp_retry.translations))
        if retry_shift is not None:
            raise LineMisalignmentError(
                f"{self.name} returned lines shifted by {retry_shift:+d} against their "
                "sources after retry"
            )
        return resp_retry

    def _assemble_messages(
        self,
        lines: list[str],
        source_lang: str,
        target_lang: str,
        glossary_entries: list[dict] | None,
        series_context: str | None = None,
        strict: bool = False,
        *,
        lookback: list[str] | None = None,
        lookahead: list[str] | None = None,
    ) -> list[dict]:
        """Build OpenAI-style messages list.

        Subclasses may override for provider quirks (e.g. Anthropic's
        separate ``system`` parameter).

        The optional keyword-only ``lookback`` and ``lookahead`` arguments
        (Phase A4) attach surrounding context to the system prompt so LLMs
        can resolve pronouns and keep terminology consistent across batch
        boundaries. The lines are explicitly marked as context-only — the
        model must not translate or repeat them.
        """
        # P3: every untrusted field (subtitle lines, series_context,
        # glossary terms from DB, lookback/lookahead context) goes through
        # escape_for_prompt before reaching the model. Glossary terms get a
        # tighter cap because they are configured by the operator but stored
        # as DB rows, so we still treat them as untrusted at this boundary.
        safe_lines = [escape_for_prompt(line) for line in lines]

        system_parts = [
            f"You translate subtitles from {source_lang} to {target_lang}.",
            f"Translate exactly {len(safe_lines)} lines, one per line, in the same order.",
        ]
        if series_context:
            system_parts.append(f"Context: {escape_for_prompt(series_context)}")
        if strict:
            system_parts.append(
                "STRICT: your response MUST contain exactly "
                f"{len(safe_lines)} lines — no more, no fewer. "
                "Do NOT add commentary or numbering."
            )
        if glossary_entries:
            terms = ", ".join(
                f"{escape_for_prompt(e.get('source', e.get('source_term', '')), max_chars=100)}"
                f" -> "
                f"{escape_for_prompt(e.get('target', e.get('target_term', '')), max_chars=100)}"
                for e in glossary_entries
            )
            system_parts.append(f"Glossary: {terms}")

        # Add context window (Phase A4) for LLMs to see surrounding lines.
        # Lookback/lookahead carry the same trust level as the lines being
        # translated (same subtitle file, same provider) so they get the
        # same per-line escape treatment.
        context_parts = []
        if lookback:
            safe_lookback = [escape_for_prompt(line) for line in lookback]
            context_parts.append(
                "Previous lines (for context only, do NOT translate or repeat):\n"
                + "\n".join(safe_lookback)
            )
        if lookahead:
            safe_lookahead = [escape_for_prompt(line) for line in lookahead]
            context_parts.append(
                "Following lines (for context only, do NOT translate or repeat):\n"
                + "\n".join(safe_lookahead)
            )
        if context_parts:
            system_parts.append("\n\n".join(context_parts))

        user_text = "\n".join(safe_lines)

        return [
            {"role": "system", "content": "\n\n".join(system_parts)},
            {"role": "user", "content": user_text},
        ]

    def _estimate_max_tokens(self, lines: list[str]) -> int:
        """Rough heuristic: output ~1.5x input chars / 4 chars-per-token + 200 slack."""
        total_chars = sum(len(line) for line in lines)
        return max(200, int(total_chars * 1.5 / 4) + 200)
