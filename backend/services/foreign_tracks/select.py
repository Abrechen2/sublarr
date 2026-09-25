"""Which embedded subtitle tracks survive the foreign-track cleanup.

The one keep/strip decision, shared by the post-download cleanup, the
scheduled sweep and both previews (spec 2026-09-25). Pure: it reads the
ffprobe ``streams`` list and returns a verdict per subtitle stream — no
ffmpeg, no database. The only I/O it may trigger is the optional
``count_events`` callback, and only to break a tie.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass

from config_language_data import normalize_language_code

MODE_ALL = "all"
MODE_ONE = "one_per_language"
SIDECAR_KEEP = "keep_embedded"
SIDECAR_DROP = "drop_if_real_sidecar"

_IMAGE_CODECS = {"hdmv_pgs_subtitle", "pgssub", "dvd_subtitle", "dvdsub", "dvb_subtitle", "xsub"}
_ASS_CODECS = {"ass", "ssa"}
_FORMAT_RANK = {"ass": 0, "text": 1, "image": 2}


@dataclass(frozen=True)
class TrackPolicy:
    mode: str = MODE_ALL
    keep_forced: bool = True
    keep_sdh: bool = False
    sidecar_policy: str = SIDECAR_KEEP


LEGACY = TrackPolicy()


@dataclass(frozen=True)
class TrackVerdict:
    index: int  # global ffprobe index (ffmpeg -map)
    sub_index: int  # 0-based subtitle-only index (mkvmerge)
    language: str  # normalized code, "und" when untagged
    fmt: str  # "ass" | "text" | "image"
    kind: str  # "full" | "forced" | "sdh"
    keep: bool
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


def _format(stream: dict) -> str:
    codec = (stream.get("codec_name") or "").lower()
    if codec in _ASS_CODECS:
        return "ass"
    if codec in _IMAGE_CODECS:
        return "image"
    return "text"


def classify_track(stream: dict) -> str:
    """full | forced | sdh. Signs and songs count as forced; unknown as full."""
    from ass_probe import is_sdh_stream
    from services.subtitle_signs import classify_stream

    try:
        subtype = classify_stream(stream)
    except Exception:  # noqa: BLE001 — an unreadable stream is treated as full (kept)
        subtype = "full"
    if subtype in ("forced", "signs", "songs"):
        return "forced"
    if is_sdh_stream(stream):
        return "sdh"
    return "full"


def _is_default(stream: dict) -> bool:
    return bool((stream.get("disposition") or {}).get("default"))


def _rank_key(track: dict) -> tuple:
    return (_FORMAT_RANK[track["fmt"]], 0 if track["default"] else 1)


def _best(candidates: list[dict], count_events: Callable[[int], int] | None) -> dict:
    ordered = sorted(candidates, key=lambda t: (_rank_key(t), t["index"]))
    top = [t for t in ordered if _rank_key(t) == _rank_key(ordered[0])]
    if len(top) > 1 and count_events is not None:
        return max(top, key=lambda t: (count_events(t["index"]), -t["index"]))
    return ordered[0]


def select_tracks(
    streams: list[dict],
    policy: TrackPolicy,
    keep_tags: set[str],
    keep_und: bool,
    real_sidecar_langs: set[str],
    count_events: Callable[[int], int] | None = None,
) -> list[TrackVerdict]:
    keep_tags = {str(t).lower() for t in keep_tags if t}
    keep_codes = {normalize_language_code(t) for t in keep_tags} - {""}
    sidecar_codes = {normalize_language_code(str(c).lower()) for c in real_sidecar_langs} - {""}

    tracks: list[dict] = []
    sub_index = 0
    for stream in streams:
        if stream.get("codec_type") != "subtitle" or stream.get("index") is None:
            continue
        raw = ((stream.get("tags") or {}).get("language") or "und").lower()
        code = normalize_language_code(raw) or raw
        tracks.append(
            {
                "index": stream["index"],
                "sub_index": sub_index,
                "raw": raw,
                "language": code,
                "fmt": _format(stream),
                "kind": classify_track(stream),
                "default": _is_default(stream),
            }
        )
        sub_index += 1

    decided: dict[int, tuple[bool, str]] = {}
    if not keep_tags:
        # Defensive, as remux has always been: an empty keep-set never strips.
        decided = {t["index"]: (True, "kept_language") for t in tracks}

    by_language: dict[str, list[dict]] = {}
    for t in tracks:
        if t["index"] in decided:
            continue
        if t["raw"] == "und":
            decided[t["index"]] = (
                (True, "kept_language") if keep_und else (False, "stripped_language")
            )
            continue
        if t["raw"] not in keep_tags and t["language"] not in keep_codes:
            decided[t["index"]] = (False, "stripped_language")
            continue
        by_language.setdefault(t["language"], []).append(t)

    for language, group in by_language.items():
        covered = policy.sidecar_policy == SIDECAR_DROP and language in sidecar_codes
        if policy.mode != MODE_ONE:
            for t in group:
                decided[t["index"]] = (True, "kept_language")
            if covered:
                for t in group:
                    if t["kind"] != "forced":
                        decided[t["index"]] = (False, "stripped_sidecar")
            continue

        full = [t for t in group if t["kind"] == "full"]
        sdh = [t for t in group if t["kind"] == "sdh"]
        forced = [t for t in group if t["kind"] == "forced"]
        main_pool = full or sdh
        main = _best(main_pool, count_events) if main_pool else None
        keep: dict[int, str] = {}
        if main is not None:
            keep[main["index"]] = "stripped_sidecar" if covered else "kept_main"
        if policy.keep_forced and forced:
            keep[_best(forced, None)["index"]] = "kept_forced"
        if policy.keep_sdh:
            rest = [t for t in sdh if main is None or t["index"] != main["index"]]
            if rest:
                keep[_best(rest, None)["index"]] = "kept_sdh"
        for t in group:
            reason = keep.get(t["index"])
            if reason is None:
                decided[t["index"]] = (False, "stripped_variant")
            elif reason == "stripped_sidecar":
                decided[t["index"]] = (False, "stripped_sidecar")
            else:
                decided[t["index"]] = (True, reason)
        if not covered and not any(decided[t["index"]][0] for t in group):
            # Guard: a kept language never loses its last track uncovered.
            last = _best(group, None)
            decided[last["index"]] = (True, "kept_last_track")

    return [
        TrackVerdict(
            index=t["index"],
            sub_index=t["sub_index"],
            language=t["language"],
            fmt=t["fmt"],
            kind=t["kind"],
            keep=decided[t["index"]][0],
            reason=decided[t["index"]][1],
        )
        for t in tracks
    ]
