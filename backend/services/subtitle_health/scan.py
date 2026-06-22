"""Orchestrate checkers over an episode's subtitle targets (read-only)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from services.subtitle_health.models import Issue, ScanResult, TargetKind
from services.subtitle_health.raw_io import (
    extract_track_raw,
    is_text_codec,
    list_subtitle_streams,
    md5_bytes,
)

logger = logging.getLogger(__name__)

SCANNER_VERSION = 1

# 3-letter → 2-letter language normalization so an embedded "ger" track and a
# "de" sidecar are recognized as the same language for shadowing.
_LANG3_TO_2 = {"ger": "de", "deu": "de", "eng": "en", "jpn": "ja"}


def _norm_lang(lang: str) -> str:
    n = (lang or "").strip().lower()
    return _LANG3_TO_2.get(n, n)


def apply_shadowing(issues: list[Issue], sidecar_langs: set[str]) -> None:
    """Mark embedded-track findings as shadowed when a CLEAN sidecar of the same
    language exists.

    A language has a clean sidecar when a sidecar file is present for it
    (``sidecar_langs``) AND no sidecar finding was raised for that language.
    Players prefer external sidecars, so the embedded defect no longer affects
    playback — we suppress it from the actionable list instead of re-surfacing
    it on every rescan. Mutates ``issues`` in place; sidecar findings are never
    shadowed.
    """
    sidecar_langs_with_issues = {
        _norm_lang(i.lang) for i in issues if i.target_kind == TargetKind.SIDECAR
    }
    clean = {_norm_lang(lang) for lang in sidecar_langs} - sidecar_langs_with_issues
    for issue in issues:
        if issue.target_kind == TargetKind.EMBEDDED and _norm_lang(issue.lang) in clean:
            issue.shadowed = True


@dataclass
class Target:
    kind: TargetKind
    path: str
    stream_index: int | None
    lang: str
    codec: str
    raw: bytes
    forced: bool = False
    default: bool = False
    title: str = ""


@dataclass
class ScanContext:
    episode_id: int | None
    video_path: str
    targets: list[Target] = field(default_factory=list)
    target_languages: list[str] = field(default_factory=list)


def _list_embedded_targets(video_path: str) -> list[Target]:
    """Extract each text subtitle stream's raw bytes as a Target."""
    targets: list[Target] = []
    try:
        streams = list_subtitle_streams(video_path)
    except Exception:
        logger.exception("subtitle_health: stream probe failed for %s", video_path)
        return targets
    for s in streams:
        if not is_text_codec(s["codec"]):
            continue  # bitmap codecs reported elsewhere (Plan 2)
        try:
            raw = extract_track_raw(video_path, s["sub_index"], s["codec"])
        except Exception:
            logger.warning(
                "subtitle_health: raw extract failed for %s s:%s",
                video_path,
                s["sub_index"],
            )
            continue
        targets.append(
            Target(
                kind=TargetKind.EMBEDDED,
                path=video_path,
                stream_index=s["sub_index"],
                lang=s["lang"],
                codec=s["codec"],
                raw=raw,
                forced=bool(s.get("forced")),
                default=bool(s.get("default")),
                title=s.get("title", ""),
            )
        )
    return targets


def scan_episode(
    episode_id: int | None,
    video_path: str,
    sidecars: list[dict] | None = None,
    target_languages: list[str] | None = None,
) -> ScanResult:
    """Run all registered checkers over the episode's embedded + sidecar subs.

    ``sidecars`` is a list of dicts with keys ``path``, ``lang`` and optionally
    ``raw`` (bytes); if ``raw`` is absent it is read from disk.
    """
    from services.subtitle_health.raw_io import read_sidecar
    from services.subtitle_health.registry import CHECKERS

    targets: list[Target] = list(_list_embedded_targets(video_path))
    for sc in sidecars or []:
        raw = sc.get("raw")
        if raw is None:
            try:
                raw = read_sidecar(sc["path"])
            except OSError:
                continue
        codec = "srt"
        if sc["path"].lower().endswith(".ass") or sc["path"].lower().endswith(".ssa"):
            codec = "ass"
        elif sc["path"].lower().endswith(".vtt"):
            codec = "webvtt"
        targets.append(
            Target(
                kind=TargetKind.SIDECAR,
                path=sc["path"],
                stream_index=None,
                lang=sc.get("lang", "und"),
                codec=codec,
                raw=raw,
            )
        )

    ctx = ScanContext(
        episode_id=episode_id,
        video_path=video_path,
        targets=targets,
        target_languages=target_languages or [],
    )
    raw_by_path_stream = {(t.path, t.stream_index): md5_bytes(t.raw) for t in targets if t.raw}

    issues = []
    for checker in CHECKERS:
        try:
            issues.extend(checker(ctx))
        except Exception:
            logger.exception(
                "subtitle_health: checker %s failed",
                getattr(checker, "__module__", checker),
            )

    # Backfill raw_hash where a checker left it empty.
    for issue in issues:
        if not issue.raw_hash:
            issue.raw_hash = raw_by_path_stream.get((issue.target_path, issue.stream_index), "")

    # Shadow embedded findings whose language already has a clean sidecar.
    sidecar_langs = {t.lang for t in targets if t.kind == TargetKind.SIDECAR}
    apply_shadowing(issues, sidecar_langs)

    result = ScanResult(episode_id=episode_id, video_path=video_path, issues=issues)
    try:
        from services.subtitle_health.store import persist_scan_result

        persist_scan_result(result, scanner_version=SCANNER_VERSION)
    except Exception:
        logger.debug("subtitle_health: persist skipped", exc_info=True)
    return result
