"""Dubtitle detection & selection (roadmap A4 / issue #146).

Anime releases routinely ship several English subtitle tracks in one
container — a fansub/source track (translates the Japanese), a
dubtitle/CC track (transcribes the spoken English **dub**), and
signs-&-songs/forced. They are all tagged ``eng`` with no standard flag,
so a viewer watching the English dub ends up reading fansub subs that do
not match the spoken dialogue.

Core principle: **measure, don't guess** — the dubtitle is the English
sub whose text best matches the spoken English dub.

Two tiers, cheapest first:

* **Tier 1 (no audio):** classify every English track from metadata +
  cue statistics — forced/signs disposition & title keywords (reusing
  :mod:`forced_detection`), SDH/CC markers, cue density, characters-per-
  second and overlapping-cue ratio. Resolves the unambiguous cases
  (single full-text track, or an obvious CC track) for free.
* **Tier 2 (audio-aligned, only when ≥2 full-text English tracks remain):**
  Whisper-sample the English dub audio at three windows, then score each
  candidate's in-window cues against the transcript with token-set
  containment (see :mod:`.text_similarity`). Highest score above the
  configured threshold is the dubtitle.

The same Tier-2 machinery powers :func:`validate_subtitle_against_audio`,
which lets the provider/download path *verify* a fetched English sub
really matches the dub before keeping it (addresses the Reddit request to
"fetch the dubtitle" — we fetch, then prove it).

Nothing here is silently applied: the orchestrator returns scored
candidates and a suggestion; acting on it (extract / strip / set-default)
is the caller's explicit choice.
"""

from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import dataclass, field

from config_language_data import _get_language_tags

logger = logging.getLogger(__name__)

# English language tags as they appear in the ffprobe ``language`` field.
_EN_TAGS = {t.lower() for t in _get_language_tags("en")} | {"en", "eng", "und"}

# --- Tier-1 thresholds --------------------------------------------------------
# A real dialogue track is dense; a signs/forced track is sparse.
_MIN_FULLTEXT_CUES = 40  # below this a track is almost never a full dialogue sub
_SIGNS_MAX_DENSITY = 3.0  # cues/minute at or below this looks like signs-only
# Dubtitles tend to run "hotter" (faster English to match flap-sync) than a
# literal Japanese translation; used only as a tie-break hint, never decisive.
_DUB_CPS_HINT = 15.0

# --- Tier-2 sampling ----------------------------------------------------------
_WINDOW_FRACTIONS = (0.12, 0.5, 0.85)  # of total duration, OP/ED-avoiding
_WINDOW_SECONDS = 45.0
_DEFAULT_MIN_SCORE = 0.55


@dataclass
class DubtitleCandidate:
    """One English subtitle track scored for "is this the dubtitle?"."""

    sub_index: int
    stream_index: int | None
    language: str
    title: str
    fmt: str  # "ass" | "srt"
    is_sdh: bool
    subtype: str  # "full" | "forced" | "signs"
    cue_count: int
    cue_density: float  # cues per minute
    avg_cps: float  # characters per second of displayed text
    overlap_ratio: float  # fraction of cues overlapping their predecessor
    tier1_label: str  # "likely_dubtitle" | "candidate" | "signs_forced" | "sparse"
    audio_score: float | None = None  # Tier-2 containment, None if not scored
    is_dubtitle: bool = False
    reason: str = ""


@dataclass
class DubtitleDetectionResult:
    """Outcome of a detection pass over one video file."""

    candidates: list[DubtitleCandidate] = field(default_factory=list)
    dubtitle_sub_index: int | None = None
    method: str = "none"  # "tier1" | "tier2" | "none"
    tier2_ran: bool = False
    min_score: float = _DEFAULT_MIN_SCORE
    margin: float | None = None  # best audio_score − runner-up (Tier-2 only)
    runner_up_score: float | None = None
    message: str = ""
    whisper_fallback_available: bool = False


@dataclass
class ValidationResult:
    """Outcome of scoring a single sidecar against the dub audio."""

    score: float
    passed: bool
    min_score: float
    message: str = ""


# ---------------------------------------------------------------------------
# Cue loading
# ---------------------------------------------------------------------------


@dataclass
class _Cue:
    start_ms: int
    end_ms: int
    text: str


def _load_cues_from_file(path: str) -> list[_Cue]:
    """Parse a subtitle file into plaintext cues via pysubs2 (encoding-safe)."""
    import pysubs2

    try:
        subs = pysubs2.load(path)
    except Exception:
        # pysubs2 occasionally trips on exotic encodings; retry via chardet.
        try:
            import chardet

            with open(path, "rb") as fh:
                raw = fh.read()
            enc = (chardet.detect(raw).get("encoding") or "utf-8").lower()
            subs = pysubs2.SSAFile.from_string(raw.decode(enc, errors="replace"))
        except Exception as exc:
            logger.debug("dubtitle: could not parse %s: %s", path, exc)
            return []

    cues: list[_Cue] = []
    for ev in subs:
        if ev.is_comment:
            continue
        text = ev.plaintext or ev.text or ""
        if not text.strip():
            continue
        cues.append(_Cue(start_ms=int(ev.start), end_ms=int(ev.end), text=text))
    return cues


def _extract_and_load_cues(video_path: str, sub_index: int, fmt: str) -> list[_Cue]:
    """Extract one embedded subtitle stream to a tempfile and parse its cues."""
    from ass_utils import extract_subtitle_stream

    suffix = ".ass" if fmt == "ass" else ".srt"
    fd, tmp = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    try:
        extract_subtitle_stream(video_path, {"sub_index": sub_index, "format": fmt}, tmp)
        return _load_cues_from_file(tmp)
    except Exception as exc:
        logger.debug("dubtitle: extract+parse failed for stream %d: %s", sub_index, exc)
        return []
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Tier 1 — cheap heuristics
# ---------------------------------------------------------------------------


def _cue_statistics(cues: list[_Cue]) -> tuple[float, float, float]:
    """Return (cue_density_per_min, avg_cps, overlap_ratio) for a cue list."""
    if not cues:
        return 0.0, 0.0, 0.0

    span_ms = max(c.end_ms for c in cues) - min(c.start_ms for c in cues)
    span_min = max(span_ms / 60_000.0, 1e-6)
    density = len(cues) / span_min

    cps_values: list[float] = []
    for c in cues:
        dur_s = max((c.end_ms - c.start_ms) / 1000.0, 1e-3)
        chars = len(c.text.replace("\\N", " ").strip())
        if chars:
            cps_values.append(chars / dur_s)
    avg_cps = sum(cps_values) / len(cps_values) if cps_values else 0.0

    ordered = sorted(cues, key=lambda c: c.start_ms)
    overlaps = sum(1 for a, b in zip(ordered, ordered[1:]) if b.start_ms < a.end_ms)
    overlap_ratio = overlaps / max(len(ordered) - 1, 1)

    return density, avg_cps, overlap_ratio


def _classify_tier1(stream: dict, cues: list[_Cue]) -> DubtitleCandidate:
    """Build a scored candidate for one English subtitle stream."""
    from ass_probe import is_sdh_stream
    from forced_detection import detect_subtitle_type

    sub_index = stream["sub_index"]
    fmt = stream["format"]
    tags = stream.get("_tags") or {}
    title = (tags.get("title") or "").strip()
    raw_stream = stream.get("_raw") or {}

    is_sdh = is_sdh_stream(raw_stream)
    subtype, _conf = detect_subtitle_type(stream_info=raw_stream)
    density, avg_cps, overlap_ratio = _cue_statistics(cues)
    cue_count = len(cues)

    # Label resolution, cheapest-confidence first.
    if subtype in ("signs", "forced"):
        label = "signs_forced"
        reason = f"classified as {subtype} (disposition/title)"
    elif cue_count < _MIN_FULLTEXT_CUES or density <= _SIGNS_MAX_DENSITY:
        label = "sparse"
        reason = f"sparse track ({cue_count} cues, {density:.1f}/min) — not full dialogue"
    elif is_sdh:
        # CC/SDH transcribes the audio track itself — strongest no-audio signal
        # that this is the dub caption.
        label = "likely_dubtitle"
        reason = "SDH/CC track — transcribes spoken audio"
    else:
        label = "candidate"
        reason = f"full-text track ({cue_count} cues, {density:.1f}/min)"

    return DubtitleCandidate(
        sub_index=sub_index,
        stream_index=raw_stream.get("index"),
        language=stream["language"],
        title=title,
        fmt=fmt,
        is_sdh=is_sdh,
        subtype=subtype,
        cue_count=cue_count,
        cue_density=round(density, 2),
        avg_cps=round(avg_cps, 2),
        overlap_ratio=round(overlap_ratio, 3),
        tier1_label=label,
        reason=reason,
    )


def _english_subtitle_streams(probe_data: dict) -> list[dict]:
    """Return text-based English subtitle streams with raw metadata attached."""
    streams: list[dict] = []
    sub_index = 0
    for st in probe_data.get("streams", []):
        if st.get("codec_type") != "subtitle":
            continue
        codec = (st.get("codec_name") or "").lower()
        if codec in ("ass", "ssa"):
            fmt = "ass"
        elif codec in ("subrip", "srt", "mov_text", "webvtt", "text", "microdvd"):
            fmt = "srt"
        else:
            sub_index += 1
            continue  # image-based — cannot text-match
        lang = (st.get("tags", {}).get("language", "und") or "und").lower()
        if lang in _EN_TAGS:
            streams.append(
                {
                    "sub_index": sub_index,
                    "format": fmt,
                    "language": lang,
                    "_tags": st.get("tags") or {},
                    "_raw": st,
                }
            )
        sub_index += 1
    return streams


# ---------------------------------------------------------------------------
# Tier 2 — audio-aligned scoring
# ---------------------------------------------------------------------------


@dataclass
class _TranscriptWindow:
    start_ms: int
    end_ms: int
    tokens: set[str]


def _compute_windows(duration_ms: int) -> list[tuple[int, int]]:
    """Return [(start_ms, end_ms)] sampling windows, avoiding OP/ED edges."""
    if duration_ms <= 0:
        return []
    win_ms = int(_WINDOW_SECONDS * 1000)
    windows: list[tuple[int, int]] = []
    for frac in _WINDOW_FRACTIONS:
        start = int(duration_ms * frac)
        start = max(0, min(start, duration_ms - win_ms))
        windows.append((start, min(start + win_ms, duration_ms)))
    # Deduplicate (very short files collapse the fractions onto each other).
    return sorted(set(windows))


def _build_dub_transcript_windows(video_path: str, duration_ms: int) -> list[_TranscriptWindow]:
    """Whisper-transcribe English dub audio at the sampling windows.

    Returns one :class:`_TranscriptWindow` per window that produced text.
    Empty list when no English audio, Whisper disabled/unavailable, or
    every window failed — the caller treats that as "Tier-2 unavailable".
    """
    from translator._helpers import _is_whisper_enabled
    from whisper import get_whisper_manager
    from whisper.audio import extract_audio_window_to_wav, select_audio_track

    if not _is_whisper_enabled():
        logger.info("dubtitle: Whisper disabled — Tier-2 unavailable")
        return []

    try:
        audio = select_audio_track(video_path, preferred_language="en")
    except RuntimeError as exc:
        logger.info("dubtitle: no audio track for Tier-2 (%s)", exc)
        return []

    windows = _compute_windows(duration_ms)
    if not windows:
        return []

    manager = get_whisper_manager()
    results: list[_TranscriptWindow] = []
    for start_ms, end_ms in windows:
        fd, wav = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        try:
            extract_audio_window_to_wav(
                video_path,
                audio["stream_index"],
                wav,
                start_s=start_ms / 1000.0,
                duration_s=(end_ms - start_ms) / 1000.0,
            )
            tr = manager.transcribe(wav, language="en")
            if not tr.success or not tr.srt_content:
                logger.debug("dubtitle: window %d transcription empty/failed", start_ms)
                continue
            tokens = _transcript_tokens(tr.srt_content)
            if tokens:
                results.append(_TranscriptWindow(start_ms, end_ms, tokens))
        except Exception as exc:
            logger.debug("dubtitle: window %d sampling failed: %s", start_ms, exc)
        finally:
            try:
                os.unlink(wav)
            except OSError:
                pass
    return results


def _transcript_tokens(srt_content: str) -> set[str]:
    """Parse Whisper SRT output into a flat content-token set."""
    import pysubs2

    from services.dubtitle.text_similarity import normalize_to_tokens

    try:
        subs = pysubs2.SSAFile.from_string(srt_content, format_="srt")
    except Exception:
        return set()
    tokens: set[str] = set()
    for ev in subs:
        tokens.update(normalize_to_tokens(ev.plaintext or ev.text or "", strip_bracketed=False))
    return tokens


def _score_cues_against_windows(cues: list[_Cue], windows: list[_TranscriptWindow]) -> float | None:
    """Mean token-set containment of a track's in-window cues vs transcript.

    Returns None when the track has no cues overlapping any window (cannot
    be scored), else the average per-window containment over windows where
    the track actually had dialogue.
    """
    from services.dubtitle.text_similarity import containment_score, normalize_to_tokens

    per_window: list[float] = []
    for win in windows:
        sub_tokens: set[str] = set()
        for c in cues:
            if win.start_ms <= c.start_ms < win.end_ms:
                sub_tokens.update(normalize_to_tokens(c.text, strip_bracketed=True))
        if sub_tokens:
            per_window.append(containment_score(sub_tokens, win.tokens))
    if not per_window:
        return None
    return sum(per_window) / len(per_window)


# ---------------------------------------------------------------------------
# Public orchestrators
# ---------------------------------------------------------------------------


def _resolve_min_score(min_score: float | None) -> float:
    if min_score is not None:
        return min_score
    try:
        from config import get_settings

        return float(getattr(get_settings(), "dubtitle_min_score", _DEFAULT_MIN_SCORE))
    except Exception:
        return _DEFAULT_MIN_SCORE


def _resolve_auto_guards() -> tuple[float, int]:
    """Return (min_margin, auto_min_cues) for unattended detection from config."""
    try:
        from config import get_settings

        s = get_settings()
        return (
            float(getattr(s, "dubtitle_min_margin", 0.15)),
            int(getattr(s, "dubtitle_auto_min_cues", 70)),
        )
    except Exception:
        return 0.15, 70


def detect_dubtitle(
    video_path: str,
    *,
    probe_data: dict | None = None,
    min_score: float | None = None,
    run_tier2: bool = True,
    automated: bool = False,
) -> DubtitleDetectionResult:
    """Identify the dubtitle among a file's embedded English subtitle tracks.

    Args:
        video_path: Absolute path to the video container.
        probe_data: Pre-computed ffprobe output; probed on demand if None.
        min_score: Tier-2 acceptance threshold; falls back to config /
            :data:`_DEFAULT_MIN_SCORE`.
        run_tier2: When False, only the no-audio heuristics run (used by the
            UI's "quick scan" and by tests).
        automated: Unattended mode (scheduled sweep). Applies the stricter
            Gemini-recommended guardrails — a higher cue floor and a
            confidence-margin gate on the Tier-2 winner — so an automatic
            flag is only set when the call is genuinely high-confidence. The
            on-demand UI path leaves this False and still suggests the best
            candidate for a human to confirm.

    Returns:
        :class:`DubtitleDetectionResult` — scored candidates plus the
        suggested ``dubtitle_sub_index`` (None if undetermined). Never
        mutates the file.
    """
    from ass_utils import get_media_streams

    threshold = _resolve_min_score(min_score)
    min_margin, auto_min_cues = _resolve_auto_guards()
    result = DubtitleDetectionResult(min_score=threshold)

    if probe_data is None:
        try:
            probe_data = get_media_streams(video_path)
        except Exception as exc:
            result.message = f"Could not probe file: {exc}"
            return result

    en_streams = _english_subtitle_streams(probe_data)
    if not en_streams:
        result.message = "No English subtitle tracks found."
        return result

    # Tier 1 — classify every English track.
    cues_by_index: dict[int, list[_Cue]] = {}
    for st in en_streams:
        cues = _extract_and_load_cues(video_path, st["sub_index"], st["format"])
        cues_by_index[st["sub_index"]] = cues
        result.candidates.append(_classify_tier1(st, cues))

    full_text = [c for c in result.candidates if c.tier1_label in ("candidate", "likely_dubtitle")]
    # Unattended mode demands a denser dialogue track so a borderline-sparse
    # track can't be auto-flagged on a lucky single-window match.
    if automated:
        full_text = [c for c in full_text if c.cue_count >= auto_min_cues]

    if not full_text:
        result.method = "tier1"
        result.message = "No full-text English track present — only signs/forced/sparse."
        result.whisper_fallback_available = True
        return result

    if len(full_text) == 1:
        chosen = full_text[0]
        chosen.is_dubtitle = True
        chosen.reason = "only full-text English track — unambiguous"
        result.dubtitle_sub_index = chosen.sub_index
        result.method = "tier1"
        result.message = "Single full-text English track — selected without audio analysis."
        return result

    # A lone SDH/CC track among otherwise-fansub candidates is a strong Tier-1
    # winner — CC transcribes the spoken audio by definition.
    sdh = [c for c in full_text if c.tier1_label == "likely_dubtitle"]
    if len(sdh) == 1:
        chosen = sdh[0]
        chosen.is_dubtitle = True
        result.dubtitle_sub_index = chosen.sub_index
        result.method = "tier1"
        result.message = "SDH/CC track identified as dubtitle without audio analysis."
        return result

    if not run_tier2:
        result.method = "tier1"
        result.message = f"{len(full_text)} full-text English tracks — Tier-2 audio scan needed."
        result.whisper_fallback_available = True
        return result

    # Tier 2 — audio-aligned scoring.
    duration_ms = max((c.end_ms for cues in cues_by_index.values() for c in cues), default=0)
    windows = _build_dub_transcript_windows(video_path, duration_ms)
    result.tier2_ran = bool(windows)
    if not windows:
        result.method = "tier1"
        result.message = (
            f"{len(full_text)} full-text English tracks — could not sample dub audio "
            "(Whisper disabled, no English audio, or sampling failed)."
        )
        result.whisper_fallback_available = True
        return result

    for cand in full_text:
        score = _score_cues_against_windows(cues_by_index[cand.sub_index], windows)
        cand.audio_score = round(score, 3) if score is not None else None
        if score is not None:
            cand.reason = f"audio match {score:.2f} over {len(windows)} window(s)"

    # Rank by audio score to derive winner + runner-up (for the margin gate).
    scored = sorted(
        (c for c in full_text if c.audio_score is not None),
        key=lambda c: c.audio_score or 0,
        reverse=True,
    )
    best = scored[0] if scored else None
    runner_up = scored[1].audio_score if len(scored) > 1 else None
    result.runner_up_score = runner_up
    result.margin = round((best.audio_score or 0) - runner_up, 3) if runner_up is not None else None

    result.method = "tier2"
    if best is None or (best.audio_score or 0) < threshold:
        top = max((c.audio_score or 0) for c in full_text)
        result.message = (
            f"No English track matched the dub above {threshold} (best {top:.2f}). "
            "Likely no dubtitle present — offer Whisper full-transcription."
        )
        result.whisper_fallback_available = True
        return result

    # Confidence-margin gate: only an unattended run insists on a clear gap to
    # the runner-up. The on-demand UI still surfaces the best guess for a human.
    if automated and result.margin is not None and result.margin < min_margin:
        result.message = (
            f"Top match {best.audio_score:.2f} too close to runner-up "
            f"{runner_up:.2f} (margin {result.margin:.2f} < {min_margin}); "
            "not auto-flagged — confirm manually."
        )
        return result

    best.is_dubtitle = True
    result.dubtitle_sub_index = best.sub_index
    margin_note = f", margin {result.margin:.2f}" if result.margin is not None else ""
    result.message = (
        f"Dubtitle selected by audio match ({best.audio_score:.2f} ≥ {threshold}{margin_note})."
    )
    return result


def result_to_dict(result: DubtitleDetectionResult) -> dict:
    """Serialize a detection result to the JSON shape used by the API + cache.

    Shared by the on-demand POST endpoint and the cached GET endpoint so both
    return identical payloads (``video_path`` is added by the route).
    """
    return {
        "dubtitle_sub_index": result.dubtitle_sub_index,
        "method": result.method,
        "tier2_ran": result.tier2_ran,
        "min_score": result.min_score,
        "margin": result.margin,
        "runner_up_score": result.runner_up_score,
        "message": result.message,
        "whisper_fallback_available": result.whisper_fallback_available,
        "candidates": [
            {
                "sub_index": c.sub_index,
                "stream_index": c.stream_index,
                "language": c.language,
                "title": c.title,
                "format": c.fmt,
                "is_sdh": c.is_sdh,
                "subtype": c.subtype,
                "cue_count": c.cue_count,
                "cue_density": c.cue_density,
                "avg_cps": c.avg_cps,
                "overlap_ratio": c.overlap_ratio,
                "tier1_label": c.tier1_label,
                "audio_score": c.audio_score,
                "is_dubtitle": c.is_dubtitle,
                "reason": c.reason,
            }
            for c in result.candidates
        ],
    }


def validate_subtitle_against_audio(
    video_path: str,
    subtitle_path: str,
    *,
    min_score: float | None = None,
) -> ValidationResult:
    """Score a standalone English sidecar against the spoken dub audio.

    This is the "fetch, then prove it" path: after a provider/Whisper run
    delivers an English subtitle, call this to confirm it actually matches
    the English dub before keeping it. Returns ``passed=False`` (rather than
    raising) whenever the dub audio cannot be sampled, so callers can treat
    "unverifiable" as "do not block".
    """
    threshold = _resolve_min_score(min_score)
    cues = _load_cues_from_file(subtitle_path)
    if not cues:
        return ValidationResult(0.0, False, threshold, "Subtitle had no readable cues.")

    duration_ms = max((c.end_ms for c in cues), default=0)
    windows = _build_dub_transcript_windows(video_path, duration_ms)
    if not windows:
        return ValidationResult(
            0.0, False, threshold, "Could not sample dub audio — validation skipped."
        )

    score = _score_cues_against_windows(cues, windows)
    if score is None:
        return ValidationResult(0.0, False, threshold, "Subtitle had no cues in sampled windows.")

    passed = score >= threshold
    return ValidationResult(
        score=round(score, 3),
        passed=passed,
        min_score=threshold,
        message=(
            f"Audio match {score:.2f} {'≥' if passed else '<'} threshold {threshold}."
            + ("" if passed else " Subtitle may not match the English dub.")
        ),
    )
