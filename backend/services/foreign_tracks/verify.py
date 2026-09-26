"""Post-strip verification before the sweep may delete a backup.

With ``delete_original_after_verify`` on, the sweep deletes the original right
after a rewrite instead of leaving it in the trash for the retention period.
That is only safe when the rewritten file is exactly what the policy asked
for, so the check compares it with the original (the backup):

- the rewrite is non-empty, probes, and has a video stream;
- it keeps every audio stream of the original;
- its subtitle tracks are precisely the ones the policy keeps from the
  original — not one more (nothing strippable left), not one less (nothing
  the policy keeps was lost), and not a different track of the same language
  (an ENG PGS kept instead of the ENG ASS, a forced track kept instead of the
  full one). Tracks are compared by a signature built only from stream data a
  mkvmerge/ffmpeg stream copy carries over unchanged: normalized language,
  codec, title, the forced/hearing-impaired flags and the derived
  kind and format. Stream indices and mkvmerge's statistics tags
  (``NUMBER_OF_FRAMES`` & co.) are rewritten by the remux and left out.

Both files are probed with ffprobe itself, uncached: the configurable metadata
engine may be MediaInfo, whose normalized output carries no video stream, and
a cached probe may describe the file before the rewrite.

Duration and total stream counts are already checked by the remux itself
before it replaces the file. Anything unexpected answers False: a false
negative costs disk for the retention period, a false positive costs the
original.
"""

from __future__ import annotations

import logging
import os
from collections import Counter

logger = logging.getLogger(__name__)


# "default" is deliberately left out: ffmpeg (the MP4 path) sets it on the first
# track of each type when none is set, so it changes on a correct remux and would
# only keep backups for no reason — and it does not tell two tracks apart the way
# language, codec, title, forced and hearing-impaired do.
_SIGNATURE_FLAGS = ("forced", "hearing_impaired")


def _by_type(streams: list[dict], codec_type: str) -> list[dict]:
    return [s for s in streams if s.get("codec_type") == codec_type]


def _probe(path: str) -> list[dict]:
    """ffprobe ``path`` — never the configurable engine, never the cache."""
    import ass_probe

    return ass_probe.run_ffprobe(path, use_cache=False).get("streams", [])


def _signature(stream: dict) -> tuple:
    """What identifies a subtitle track across a stream-copy remux."""
    from config_language_data import normalize_language_code
    from services.foreign_tracks.select import _format, classify_track

    tags = stream.get("tags") or {}
    raw = str(tags.get("language") or "und").lower()
    disposition = stream.get("disposition") or {}
    return (
        normalize_language_code(raw) or raw,
        str(stream.get("codec_name") or "").lower(),
        str(tags.get("title") or tags.get("TITLE") or ""),
        *(bool(disposition.get(flag)) for flag in _SIGNATURE_FLAGS),
        classify_track(stream),
        _format(stream),
    )


def _describe(signatures: Counter) -> str:
    return ", ".join(f"{sig[0]}/{sig[1]}/{sig[2] or '-'}/{sig[6]}" for sig in signatures)


def verify_strip(
    video_path: str,
    backup_path: str,
    policy,
    keep_tags: set[str],
    keep_und: bool,
    real_sidecar_langs: set[str],
) -> tuple[bool, str]:
    """``(ok, reason)`` — whether the rewrite at ``video_path`` may replace
    ``backup_path`` for good."""
    from remux.event_count import make_event_counter
    from services.foreign_tracks.select import select_tracks

    try:
        if os.path.getsize(video_path) <= 0:
            return False, "rewritten file is empty"
        after = _probe(video_path)
        before = _probe(backup_path)
    except Exception as exc:  # noqa: BLE001 — an unprobeable file must never lose its backup
        return False, f"probe failed: {exc}"

    if not _by_type(after, "video"):
        return False, "no video stream after the rewrite"
    if len(_by_type(after, "audio")) != len(_by_type(before, "audio")):
        return False, (
            f"audio streams changed ({len(_by_type(before, 'audio'))} -> "
            f"{len(_by_type(after, 'audio'))})"
        )

    def decide(streams, path):
        return select_tracks(
            streams,
            policy,
            keep_tags,
            keep_und,
            real_sidecar_langs,
            count_events=make_event_counter(path, streams=streams),
        )

    by_index = {s.get("index"): s for s in _by_type(before, "subtitle")}
    expected = Counter(_signature(by_index[v.index]) for v in decide(before, backup_path) if v.keep)
    leftover = [v for v in decide(after, video_path) if not v.keep]
    if leftover:
        return False, "still strippable: " + ", ".join(f"{v.language}:{v.reason}" for v in leftover)
    # Every subtitle stream of the rewrite, including one without an index
    # (select_tracks gives it no verdict, but it is still in the file).
    got = Counter(_signature(s) for s in _by_type(after, "subtitle"))
    if got != expected:
        return False, (
            f"subtitle tracks differ (missing [{_describe(expected - got)}], "
            f"extra [{_describe(got - expected)}])"
        )
    return True, "ok"
