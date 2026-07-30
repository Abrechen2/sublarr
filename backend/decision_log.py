"""Decision log — records WHY a subtitle was (or wasn't) chosen.

Collects the full selection pipeline of one ``process_wanted_item`` run:
which providers were searched (hits / skip reasons / latency), which
candidates each filter stage rejected, the upgrade decision, the download
attempts, and the final selection with its score breakdown.

The collector is held in a ``contextvars.ContextVar`` so the deep call
chain (process step -> ProviderManager -> search coordinator -> scoring ->
download manager) does not need signature changes: every instrumentation
point calls a module-level helper that no-ops when no log is active.
``process_wanted_item`` runs each item inside a single thread (its own
worker thread or the Flask request thread), and all instrumented code
runs on that same thread — the provider fan-out threads are drained by
``_collect_provider_results`` on the coordinating thread, which is where
per-provider facts are recorded.

Persistence:
- success  -> ``subtitle_downloads.decision_log_json`` (snapshot taken by
  ``db.providers.record_subtitle_download`` via :func:`snapshot_json`)
- failure  -> ``wanted_items.last_decision_log_json`` (written by
  ``process_wanted_item``)
"""

import json
import logging
from contextvars import ContextVar
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

# Schema version for the serialized payload — bump on breaking changes.
VERSION = 1

# Per-stage cap for rejected-candidate samples (expert mode detail).
MAX_REJECTED_SAMPLES = 25

# If the serialized log exceeds this, drop the per-candidate samples and
# keep only the aggregate counts. Keeps DB rows bounded.
MAX_JSON_BYTES = 200_000

_current: ContextVar["DecisionLog | None"] = ContextVar("sublarr_decision_log", default=None)


class DecisionLog:
    """Mutable collector for one wanted-item processing run."""

    def __init__(self, item: dict | None = None):
        self.started_at = datetime.now(UTC).isoformat()
        self.item: dict = {}
        if item:
            self.item = {
                "wanted_id": item.get("id"),
                "title": item.get("title") or "",
                "season_episode": item.get("season_episode") or "",
                "file_path": item.get("file_path") or "",
                "target_language": item.get("target_language") or "",
                "is_upgrade": bool(item.get("upgrade_candidate")),
            }
        self.steps: list[dict] = []  # skipped-step notes, in order
        self.searches: list[dict] = []
        self.upgrade: dict | None = None
        self.final: dict | None = None
        self._step: str = ""

    # ---- step / search lifecycle -------------------------------------------------

    def set_step(self, step: str) -> None:
        self._step = step

    def step_skipped(self, step: str, reason: str) -> None:
        self.steps.append({"step": step, "skipped": True, "reason": reason})

    def search_started(self, languages, format_filter, min_score: int) -> None:
        self.searches.append(
            {
                "step": self._step,
                "languages": list(languages or []),
                "format": getattr(format_filter, "value", format_filter) or "",
                "min_score": min_score,
                "cache_hit": False,
                "providers": [],
                "results_total": 0,
                "filters": [],
                "results_final": 0,
                "download_attempts": [],
            }
        )

    def _search(self) -> dict | None:
        return self.searches[-1] if self.searches else None

    def search_cache_hit(self, count: int) -> None:
        s = self._search()
        if s is not None:
            s["cache_hit"] = True
            s["results_total"] = count
            s["results_final"] = count

    def search_finished(self, total: int, final: int) -> None:
        s = self._search()
        if s is not None:
            s["results_total"] = total
            s["results_final"] = final

    # ---- provider facts ----------------------------------------------------------

    def provider_skipped(self, name: str, reason: str, detail: str = "") -> None:
        s = self._search()
        if s is not None:
            entry: dict = {"name": name, "status": "skipped", "reason": reason}
            if detail:
                entry["detail"] = detail
            s["providers"].append(entry)

    def provider_searched(self, name: str, hits: int, elapsed_ms: float) -> None:
        s = self._search()
        if s is not None:
            s["providers"].append(
                {"name": name, "status": "ok", "hits": hits, "elapsed_ms": round(elapsed_ms)}
            )

    def provider_failed(self, name: str, kind: str, detail: str = "") -> None:
        """kind: 'timeout' | 'rate_limited' | 'error'."""
        s = self._search()
        if s is not None:
            entry: dict = {"name": name, "status": kind}
            if detail:
                entry["detail"] = detail[:300]
            s["providers"].append(entry)

    def providers_unfinished(self, names: list[str]) -> None:
        s = self._search()
        if s is not None:
            s["unfinished_providers"] = list(names)

    def early_exit(self, provider: str, score: int) -> None:
        s = self._search()
        if s is not None:
            s["early_exit"] = {"provider": provider, "score": score}

    # ---- filter stages -----------------------------------------------------------

    def filter_stage(self, stage: str, removed: int, remaining: int, rejected_samples=None, **info):
        """Record one filter gate. ``rejected_samples`` is a list of SubtitleResult."""
        if removed <= 0:
            return
        s = self._search()
        if s is None:
            return
        entry: dict = {"stage": stage, "removed": removed, "remaining": remaining}
        entry.update({k: v for k, v in info.items() if v is not None})
        if rejected_samples:
            entry["rejected"] = [_result_brief(r) for r in rejected_samples[:MAX_REJECTED_SAMPLES]]
        s["filters"].append(entry)

    # ---- download / selection ----------------------------------------------------

    def download_attempt(self, provider: str, subtitle_id: str, status: str, detail: str = ""):
        """status: 'selected' | 'download_failed' | 'hash_blacklisted' | 'error'."""
        s = self._search()
        if s is not None:
            entry: dict = {"provider": provider, "subtitle_id": str(subtitle_id), "status": status}
            if detail:
                entry["detail"] = detail[:300]
            s["download_attempts"].append(entry)

    def selected(self, result) -> None:
        self.final = dict(self.final or {})
        # Provisional status — process_wanted_item's outcome may refine it
        # (e.g. "found", "duplicate_skipped") via set_outcome() later.
        self.final.setdefault("status", "found")
        self.final.update(
            {
                "provider": result.provider_name,
                "subtitle_id": str(result.subtitle_id),
                "language": result.language,
                "format": getattr(result.format, "value", str(result.format)),
                "score": result.score,
                "score_breakdown": dict(getattr(result, "score_breakdown", None) or {}),
                "filename": getattr(result, "filename", "") or "",
                "release_info": getattr(result, "release_info", "") or "",
                "step": self._step,
            }
        )

    def upgrade_decision(self, approved: bool, reason: str, old_score: int, new_score: int):
        self.upgrade = {
            "approved": bool(approved),
            "reason": reason,
            "old_score": old_score,
            "new_score": new_score,
        }

    def set_outcome(self, status: str, **info) -> None:
        self.final = dict(self.final or {})
        self.final["status"] = status
        self.final.update({k: v for k, v in info.items() if v is not None})

    # ---- serialization -----------------------------------------------------------

    def to_dict(self) -> dict:
        d = {
            "version": VERSION,
            "started_at": self.started_at,
            "finished_at": datetime.now(UTC).isoformat(),
            "item": self.item,
            "steps": self.steps,
            "searches": self.searches,
        }
        if self.upgrade is not None:
            d["upgrade"] = self.upgrade
        if self.final is not None:
            d["final"] = self.final
        return d

    def to_json(self) -> str:
        payload = self.to_dict()
        try:
            out = json.dumps(payload, default=str)
        except (TypeError, ValueError):
            logger.debug("Decision log serialization failed", exc_info=True)
            return "{}"
        if len(out) > MAX_JSON_BYTES:
            # Drop the per-candidate expert detail, keep the aggregates.
            # Deep-copy first: to_dict() shares the nested search/filter dicts
            # with the live collector, and truncation must not mutate them.
            import copy

            payload = copy.deepcopy(payload)
            for search in payload.get("searches", []):
                for f in search.get("filters", []):
                    f.pop("rejected", None)
            payload["truncated"] = True
            out = json.dumps(payload, default=str)
        return out


def _result_brief(r) -> dict:
    """Compact per-candidate record for rejected samples."""
    return {
        "provider": getattr(r, "provider_name", ""),
        "filename": (getattr(r, "filename", "") or "")[:160],
        "language": getattr(r, "language", ""),
        "format": getattr(getattr(r, "format", None), "value", "") or "",
        "score": getattr(r, "score", 0),
        "release_info": (getattr(r, "release_info", "") or "")[:120],
    }


# ---------------------------------------------------------------------------
# Module-level helpers — every instrumentation point goes through these so a
# missing/inactive log is always a cheap no-op and can never raise into the
# search pipeline.
# ---------------------------------------------------------------------------


def start(item: dict | None = None) -> DecisionLog:
    """Activate a new decision log for the current context and return it."""
    log = DecisionLog(item)
    _current.set(log)
    return log


def finish() -> None:
    """Deactivate the current decision log."""
    _current.set(None)


def active() -> DecisionLog | None:
    return _current.get()


def snapshot_json() -> str | None:
    """Serialize the currently active log (or None when inactive).

    Used by ``db.providers.record_subtitle_download`` to attach the log to
    the download row without a signature change at every call site.
    """
    log = _current.get()
    if log is None:
        return None
    try:
        return log.to_json()
    except Exception:  # noqa: BLE001 — never break a download over logging
        logger.debug("Decision log snapshot failed", exc_info=True)
        return None


def _call(method: str, *args, **kwargs) -> None:
    log = _current.get()
    if log is None:
        return
    try:
        getattr(log, method)(*args, **kwargs)
    except Exception:  # noqa: BLE001 — instrumentation must never break the pipeline
        logger.debug("Decision log call %s failed", method, exc_info=True)


def set_step(step: str) -> None:
    _call("set_step", step)


def step_skipped(step: str, reason: str) -> None:
    _call("step_skipped", step, reason)


def search_started(languages, format_filter, min_score: int = 0) -> None:
    _call("search_started", languages, format_filter, min_score)


def search_cache_hit(count: int) -> None:
    _call("search_cache_hit", count)


def search_finished(total: int, final: int) -> None:
    _call("search_finished", total, final)


def provider_skipped(name: str, reason: str, detail: str = "") -> None:
    _call("provider_skipped", name, reason, detail)


def provider_searched(name: str, hits: int, elapsed_ms: float) -> None:
    _call("provider_searched", name, hits, elapsed_ms)


def provider_failed(name: str, kind: str, detail: str = "") -> None:
    _call("provider_failed", name, kind, detail)


def providers_unfinished(names: list[str]) -> None:
    _call("providers_unfinished", names)


def early_exit(provider: str, score: int) -> None:
    _call("early_exit", provider, score)


def filter_stage(stage: str, removed: int, remaining: int, rejected_samples=None, **info) -> None:
    _call("filter_stage", stage, removed, remaining, rejected_samples, **info)


def download_attempt(provider: str, subtitle_id: str, status: str, detail: str = "") -> None:
    _call("download_attempt", provider, subtitle_id, status, detail)


def selected(result) -> None:
    _call("selected", result)


def upgrade_decision(approved: bool, reason: str, old_score: int, new_score: int) -> None:
    _call("upgrade_decision", approved, reason, old_score, new_score)


def set_outcome(status: str, **info) -> None:
    _call("set_outcome", status, **info)
