"""Voice-activity detection (speech segments) via WebRTC VAD.

Waveform Phase 2 — a speech-activity lane so the editor can see where the
dialogue actually is. Anime mixes bury speech under BGM/SFX, so raw waveform
peaks are misleading; a VAD lane separates spoken audio from music/effects and
can serve as a snap target for cue boundaries.

``webrtcvad`` is already available transitively (``ffsubsync`` depends on it),
so this adds no new dependency. If the import ever fails, detection degrades to
an empty list and the UI omits the lane — mirrors ``scene_detector.py``.

The per-frame → segment aggregation (`_frames_to_segments`) is a pure function,
split out from the ffmpeg/VAD I/O so the smoothing rules are unit-testable.
"""

from __future__ import annotations

import logging
import subprocess

logger = logging.getLogger(__name__)

# webrtcvad accepts 10/20/30 ms frames of 16-bit mono PCM at 8/16/32/48 kHz.
_SAMPLE_RATE = 16000
_FRAME_MS = 30
_BYTES_PER_SAMPLE = 2
_FRAME_BYTES = int(_SAMPLE_RATE * _FRAME_MS / 1000) * _BYTES_PER_SAMPLE  # 960


def _import_webrtcvad():
    """Lazy import of webrtcvad so tests can simulate the dep being absent."""
    import webrtcvad  # type: ignore[import-not-found]

    return webrtcvad


def _frames_to_segments(
    speech_flags: list[bool],
    frame_ms: int = _FRAME_MS,
    *,
    min_silence_ms: int = 200,
    min_speech_ms: int = 250,
    pad_ms: int = 120,
    total_ms: int | None = None,
) -> list[tuple[float, float]]:
    """Aggregate per-frame speech booleans into padded speech segments.

    Pure — no audio, no VAD — so the smoothing rules are testable in isolation:
      1. runs of consecutive speech frames become raw intervals,
      2. runs separated by a gap shorter than ``min_silence_ms`` are merged,
      3. intervals shorter than ``min_speech_ms`` are dropped,
      4. survivors are padded by ``pad_ms`` on both sides (clamped to
         ``[0, total_ms]``) and re-merged where padding caused an overlap.

    Returns a list of ``(start_sec, end_sec)`` tuples.
    """
    n = len(speech_flags)

    runs: list[list[int]] = []
    i = 0
    while i < n:
        if speech_flags[i]:
            j = i
            while j < n and speech_flags[j]:
                j += 1
            runs.append([i * frame_ms, j * frame_ms])
            i = j
        else:
            i += 1

    merged: list[list[int]] = []
    for start, end in runs:
        if merged and start - merged[-1][1] < min_silence_ms:
            merged[-1][1] = end
        else:
            merged.append([start, end])

    limit = total_ms if total_ms is not None else n * frame_ms
    padded: list[tuple[int, int]] = []
    for start, end in merged:
        if end - start < min_speech_ms:
            continue
        padded.append((max(0, start - pad_ms), min(limit, end + pad_ms)))

    out: list[tuple[int, int]] = []
    for seg in padded:
        if out and seg[0] <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], seg[1]))
        else:
            out.append(seg)

    return [(s / 1000.0, e / 1000.0) for s, e in out]


def _decode_pcm(video_path: str, track_index: int | None = None, timeout: int = 300) -> bytes:
    """Decode a video's audio to 16 kHz mono s16le PCM bytes via ffmpeg (stdout)."""
    from security_utils import safe_subprocess_arg

    cmd = ["ffmpeg", "-v", "error", "-i", safe_subprocess_arg(video_path), "-vn"]
    if track_index is not None:
        cmd += ["-map", f"0:a:{track_index}"]
    cmd += ["-acodec", "pcm_s16le", "-ac", "1", "-ar", str(_SAMPLE_RATE), "-f", "s16le", "-"]
    proc = subprocess.run(cmd, capture_output=True, timeout=timeout)
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace")[:200]
        raise RuntimeError(f"ffmpeg PCM decode failed: {detail}")
    return proc.stdout


def detect_speech_segments(
    video_path: str,
    track_index: int | None = None,
    aggressiveness: int = 2,
) -> list[dict[str, float]]:
    """Return speech segments ``[{"start", "end"}]`` (seconds) for a video.

    Graceful degradation: returns ``[]`` when webrtcvad is unavailable or ffmpeg
    fails, so the WaveformEditor simply omits the speech lane.
    """
    try:
        webrtcvad = _import_webrtcvad()
    except ImportError:
        logger.debug("webrtcvad not installed; returning empty speech segments")
        return []

    try:
        pcm = _decode_pcm(video_path, track_index)
    except (
        subprocess.TimeoutExpired,
        subprocess.SubprocessError,
        RuntimeError,
        FileNotFoundError,
    ) as exc:
        logger.warning("Speech-segment decode failed for %s: %s", video_path, exc)
        return []

    vad = webrtcvad.Vad(aggressiveness)
    n_frames = len(pcm) // _FRAME_BYTES
    flags: list[bool] = []
    for k in range(n_frames):
        frame = pcm[k * _FRAME_BYTES : (k + 1) * _FRAME_BYTES]
        try:
            flags.append(bool(vad.is_speech(frame, _SAMPLE_RATE)))
        except Exception:
            flags.append(False)

    segments = _frames_to_segments(flags, _FRAME_MS, total_ms=n_frames * _FRAME_MS)
    return [{"start": round(s, 3), "end": round(e, 3)} for s, e in segments]
