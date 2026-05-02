"""Scene-boundary detection via PySceneDetect (BSD-3-Clause, lazy import).

Plan B8 Task 2 — scene markers on the WaveformEditor timeline. PySceneDetect
is an optional dependency; if absent, ``detect_scenes`` returns an empty list
and the UI gracefully omits the markers.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _import_scenedetect():
    """Lazy import of PySceneDetect.

    Returns ``(detect_callable, ContentDetector_class)`` or raises ``ImportError``.
    Split out so tests can patch it to simulate the dep being missing without
    touching ``sys.modules``.
    """
    from scenedetect import ContentDetector, detect  # type: ignore[import-not-found]

    return detect, ContentDetector


def detect_scenes(video_path: str, threshold: float = 27.0) -> list[float]:
    """Return scene-cut timestamps (seconds) of `video_path`.

    Uses PySceneDetect's content-aware detector. Returns ``[]`` if the lib
    is not installed (graceful degradation) or if the video has no detected
    cuts. The first scene's start (== 0.0, file start) is dropped from the
    result because it's not a meaningful cut.

    Args:
        video_path: Path to a readable video file.
        threshold: Content detector threshold (default 27.0 — PySceneDetect
            recommended starting point).

    Returns:
        Sorted list of scene-boundary timestamps in seconds.
    """
    try:
        detect, ContentDetector = _import_scenedetect()
    except ImportError:
        logger.debug("PySceneDetect not installed; returning empty scene list")
        return []

    try:
        scenes = detect(video_path, ContentDetector(threshold=threshold))
    except Exception as exc:  # pragma: no cover — pyscenedetect raises various
        logger.warning("PySceneDetect failed for %s: %s", video_path, exc)
        return []

    boundaries: list[float] = []
    for scene in scenes:
        # scene = (start_timecode, end_timecode); we want internal cuts only,
        # so we record each scene's *start* but skip the first (always 0.0).
        try:
            start = scene[0].get_seconds()
        except (AttributeError, IndexError, TypeError):
            continue
        boundaries.append(float(start))

    if boundaries and boundaries[0] == 0.0:
        boundaries = boundaries[1:]
    return boundaries
