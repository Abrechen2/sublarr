"""Post-strip verification before the sweep may delete a backup.

With ``delete_original_after_verify`` on, the sweep deletes the original right
after a rewrite instead of leaving it in the trash for the retention period.
That is only safe when the rewritten file is exactly what the policy asked
for, so the check compares it with the original (the backup):

- the rewrite is non-empty, probes, and has a video stream;
- it keeps every audio stream of the original;
- its subtitle tracks are precisely the ones the policy keeps from the
  original — not one more (nothing strippable left) and not one less
  (nothing the policy keeps was lost).

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


def _by_type(streams: list[dict], codec_type: str) -> list[dict]:
    return [s for s in streams if s.get("codec_type") == codec_type]


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
    import remux
    from remux.event_count import make_event_counter
    from services.foreign_tracks.select import select_tracks

    try:
        if os.path.getsize(video_path) <= 0:
            return False, "rewritten file is empty"
        after = remux.get_media_streams(video_path, use_cache=False).get("streams", [])
        before = remux.get_media_streams(backup_path, use_cache=False).get("streams", [])
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

    expected = Counter(v.language for v in decide(before, backup_path) if v.keep)
    got_verdicts = decide(after, video_path)
    leftover = [v for v in got_verdicts if not v.keep]
    if leftover:
        return False, "still strippable: " + ", ".join(f"{v.language}:{v.reason}" for v in leftover)
    got = Counter(v.language for v in got_verdicts)
    if got != expected:
        missing = expected - got
        extra = got - expected
        return False, f"subtitle tracks differ (missing {dict(missing)}, extra {dict(extra)})"
    return True, "ok"
