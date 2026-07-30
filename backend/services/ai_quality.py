"""AI subtitle-quality verdict — advisory LLM spot-check of downloaded sidecars.

Samples a handful of cues from a saved subtitle file, asks the configured
Ollama instance to rate machine-translation likelihood, OCR artifacts and
grammar, and stores a green/yellow/red verdict for display in History.

Guardrails (ROADMAP "AI direction" — non-negotiable):
- Read-only: the verdict never modifies files and never feeds into scoring,
  selection, or the upgrade system.
- Advisory: analysis failures are silent (logged at debug) — nothing in the
  download pipeline waits on or reacts to this module.
- Local-first: talks only to the configured Ollama URL.
"""

from __future__ import annotations

import json
import logging
import os
import re

import requests

logger = logging.getLogger(__name__)

# Higher is worse, 0-3 per axis. Encoding damage is measured in Python (it is
# deterministic); the LLM rates only the language-level axes.
_LLM_AXES = ("machine_translation", "ocr_artifacts", "grammar")
_ALL_AXES = (*_LLM_AXES, "encoding_damage")

_MAX_CUE_CHARS = 200
_MAX_CUES_HARD = 60
_MAX_REASONS = 5
_MAX_REASON_CHARS = 160

# Mojibake / replacement-character fingerprints for the encoding axis.
_ENCODING_DAMAGE_RE = re.compile(r"�|Ã[\x80-\xbf]|â€[\x9c\x9d\x98\x99\x93\x94\xa6]")

_SYSTEM_PROMPT = (
    "You are a subtitle quality inspector. You receive sampled subtitle lines "
    "in language '{language}'. Rate each axis from 0 (none) to 3 (severe):\n"
    "- machine_translation: does the text read like unedited machine "
    "translation (wrong idioms, literal word order, inconsistent pronouns)?\n"
    "- ocr_artifacts: OCR-typical damage (l/I and rn/m confusions, stray "
    "pipes, broken diacritics, merged words)?\n"
    "- grammar: grammar/spelling errors a native speaker would notice?\n"
    "Reply with ONLY a JSON object, no prose:\n"
    '{{"machine_translation": 0, "ocr_artifacts": 0, "grammar": 0, '
    '"reasons": ["short finding", "..."]}}\n'
    "reasons: at most 3 short findings quoting a problematic phrase; empty "
    "list if the text is clean. Never invent problems."
)


def sidecar_path_for(video_path: str, language: str, fmt: str) -> str:
    """Derive the subtitle sidecar path the way the rest of the app does."""
    base, _ = os.path.splitext(video_path)
    return f"{base}.{language}.{fmt}"


def sample_cues(subtitle_path: str, max_cues: int) -> list[str]:
    """Load a subtitle file and return up to max_cues evenly-spaced plaintext cues."""
    import pysubs2

    subs = pysubs2.load(subtitle_path)
    texts: list[str] = []
    seen: set[str] = set()
    for ev in subs.events:
        if getattr(ev, "is_comment", False):
            continue
        text = ev.plaintext.replace("\n", " ").strip()
        if len(text) < 3 or text in seen:
            continue
        seen.add(text)
        texts.append(text[:_MAX_CUE_CHARS])

    max_cues = max(1, min(int(max_cues), _MAX_CUES_HARD))
    if len(texts) <= max_cues:
        return texts
    step = len(texts) / max_cues
    return [texts[int(i * step)] for i in range(max_cues)]


def _measure_encoding_damage(cues: list[str]) -> int:
    """Deterministic 0-3 rating of mojibake/replacement-char density."""
    if not cues:
        return 0
    damaged = sum(1 for c in cues if _ENCODING_DAMAGE_RE.search(c))
    ratio = damaged / len(cues)
    if ratio >= 0.3:
        return 3
    if damaged >= 2 and ratio >= 0.1:
        return 2
    if damaged:
        return 1
    return 0


def _call_ollama(cues: list[str], language: str, settings) -> tuple[dict, str]:
    """Single Ollama /api/chat call. Returns (parsed_json, model_name).

    Raises on transport errors / unparseable output — the caller treats any
    exception as "no verdict".
    """
    from translation.prompt_safety import escape_for_prompt

    model = (getattr(settings, "ai_quality_model", "") or settings.ollama_model).strip()
    numbered = "\n".join(f"{i + 1}. {escape_for_prompt(c)}" for i, c in enumerate(cues))
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT.format(language=language or "unknown")},
            {"role": "user", "content": numbered},
        ],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0, "num_predict": 400},
    }
    resp = requests.post(
        f"{settings.ollama_url}/api/chat",
        json=payload,
        timeout=getattr(settings, "request_timeout", 90),
    )
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"Ollama error: {data['error']}")
    content = (data.get("message") or {}).get("content", "")
    return _parse_verdict_json(content), model


def _parse_verdict_json(content: str) -> dict:
    """Parse the model reply into a dict, tolerating prose around the JSON."""
    try:
        return json.loads(content)
    except ValueError:
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if not match:
            raise ValueError(f"no JSON object in model reply: {content[:120]!r}") from None
        return json.loads(match.group(0))


def _clamp_scores(raw: dict, encoding_damage: int) -> dict[str, int]:
    """Clamp LLM axis scores to 0-3 ints; missing/garbage values become 0."""
    scores: dict[str, int] = {}
    for axis in _LLM_AXES:
        try:
            scores[axis] = max(0, min(3, int(raw.get(axis, 0))))
        except (TypeError, ValueError):
            scores[axis] = 0
    scores["encoding_damage"] = max(0, min(3, int(encoding_damage)))
    return scores


def _derive_verdict(scores: dict[str, int]) -> str:
    """Deterministic verdict from the clamped scores (worst axis wins)."""
    worst = max(scores.values(), default=0)
    total = sum(scores.values())
    if worst >= 3 or total >= 6:
        return "red"
    if worst >= 2 or total >= 3:
        return "yellow"
    return "green"


def _clean_reasons(raw) -> list[str]:
    """Sanitise the model's reasons list: strings only, capped count/length."""
    if not isinstance(raw, list):
        return []
    reasons = []
    for item in raw:
        if isinstance(item, str) and item.strip():
            reasons.append(item.strip()[:_MAX_REASON_CHARS])
        if len(reasons) >= _MAX_REASONS:
            break
    return reasons


def analyze_file(subtitle_path: str, language: str) -> dict | None:
    """Analyze one sidecar and return the verdict dict, or None on any failure.

    Does not persist anything — see analyze_and_store(). Never raises.
    """
    from config import get_settings

    settings = get_settings()
    try:
        cues = sample_cues(subtitle_path, getattr(settings, "ai_quality_max_cues", 30))
        if len(cues) < 5:
            logger.debug("[ai-quality] %s: too few cues (%d), skipping", subtitle_path, len(cues))
            return None
        encoding_damage = _measure_encoding_damage(cues)
        raw, model = _call_ollama(cues, language, settings)
        scores = _clamp_scores(raw, encoding_damage)
        return {
            "verdict": _derive_verdict(scores),
            "scores": scores,
            "reasons": _clean_reasons(raw.get("reasons")),
            "model": model,
            "sampled_cues": len(cues),
        }
    except Exception as e:
        logger.debug("[ai-quality] analysis failed for %s: %s", subtitle_path, e)
        return None


def analyze_and_store(subtitle_path: str, language: str) -> dict | None:
    """Analyze a sidecar and persist the verdict. Never raises."""
    result = analyze_file(subtitle_path, language)
    if result is None:
        return None
    try:
        from db.quality import save_ai_quality_result

        saved = save_ai_quality_result(
            file_path=subtitle_path,
            language=language,
            verdict=result["verdict"],
            scores_json=json.dumps(result["scores"]),
            reasons_json=json.dumps(result["reasons"], ensure_ascii=False),
            model=result["model"],
            sampled_cues=result["sampled_cues"],
        )
        logger.info(
            "[ai-quality] %s → %s (cues=%d, model=%s)",
            subtitle_path,
            result["verdict"],
            result["sampled_cues"],
            result["model"],
        )
        return saved
    except Exception:
        logger.debug("[ai-quality] could not persist verdict for %s", subtitle_path, exc_info=True)
        return None


def maybe_queue_analysis(video_path: str, language: str, fmt: str) -> None:
    """Fire-and-forget analysis of a freshly-downloaded sidecar.

    No-op unless ai_quality_enabled. Called from the download-recording path,
    so it must never raise and never block.
    """
    try:
        from config import get_settings

        if not getattr(get_settings(), "ai_quality_enabled", False):
            return
        if not (video_path and language and fmt):
            return
        sidecar = sidecar_path_for(video_path, language, fmt)
        if not os.path.isfile(sidecar):
            # Some sources save the bare "<base>.<fmt>" sidecar.
            base, _ = os.path.splitext(video_path)
            alt = f"{base}.{fmt}"
            if not os.path.isfile(alt):
                return
            sidecar = alt

        from flask import current_app

        app = current_app._get_current_object()

        def _run():
            with app.app_context():
                analyze_and_store(sidecar, language)

        from services.background_tasks import submit_background

        submit_background(_run)
    except Exception:
        logger.debug("[ai-quality] could not queue analysis", exc_info=True)


def attach_ai_quality(entries: list[dict]) -> None:
    """Attach ``ai_quality`` to history row dicts in place (batch lookup).

    Each entry needs file_path/language/format keys. Rows without a stored
    verdict get ai_quality = None.
    """
    paths: dict[int, str] = {}
    for i, entry in enumerate(entries):
        video = entry.get("file_path") or ""
        lang = entry.get("language") or ""
        fmt = entry.get("format") or ""
        if video and lang and fmt:
            paths[i] = sidecar_path_for(video, lang, fmt)

    results: dict[str, dict] = {}
    if paths:
        try:
            from db.quality import get_ai_quality_results_for_paths

            results = get_ai_quality_results_for_paths(list(set(paths.values())))
        except Exception:
            logger.debug("[ai-quality] batch lookup failed", exc_info=True)

    for i, entry in enumerate(entries):
        row = results.get(paths.get(i, ""))
        if not row:
            entry["ai_quality"] = None
            continue
        try:
            scores = json.loads(row.get("scores_json") or "{}")
            reasons = json.loads(row.get("reasons_json") or "[]")
        except ValueError:
            scores, reasons = {}, []
        entry["ai_quality"] = {
            "verdict": row.get("verdict"),
            "scores": scores,
            "reasons": reasons,
            "model": row.get("model") or "",
            "sampled_cues": row.get("sampled_cues") or 0,
            "created_at": row.get("created_at"),
        }
