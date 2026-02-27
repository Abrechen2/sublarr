"""Subgen backend -- external ASR API for speech-to-text.

Delegates transcription to an external Subgen instance running Whisper.
This is the simpler backend: just POST audio to /asr and get SRT back.
No local GPU/model management required.
"""

import logging
import re
import time
from collections.abc import Callable

import requests

from whisper.base import TranscriptionResult, WhisperBackend

logger = logging.getLogger(__name__)


def _parse_srt_duration(srt_content: str) -> float:
    """Estimate duration from the last timestamp in SRT content.

    Args:
        srt_content: SRT-formatted string

    Returns:
        Estimated duration in seconds (from last end timestamp)
    """
    # Match SRT timestamps: HH:MM:SS,mmm
    timestamps = re.findall(r"(\d{2}):(\d{2}):(\d{2}),(\d{3})", srt_content)
    if not timestamps:
        return 0.0

    # Use the last timestamp (end of last subtitle)
    last = timestamps[-1]
    hours, minutes, seconds, millis = int(last[0]), int(last[1]), int(last[2]), int(last[3])
    return hours * 3600 + minutes * 60 + seconds + millis / 1000


class SubgenBackend(WhisperBackend):
    """External Subgen API transcription backend.

    Sends audio to an external Subgen instance (Whisper ASR server)
    via HTTP POST. The Subgen instance handles model loading, GPU
    management, and transcription internally.
    """

    name = "subgen"
    display_name = "Subgen (External API)"
    supports_gpu = False  # Remote -- we don't know
    supports_language_detection = True
    config_fields = [
        {
            "key": "endpoint",
            "label": "Subgen URL",
            "type": "text",
            "required": True,
            "default": "http://subgen:9000",
            "help": "URL of Subgen instance",
        },
        {
            "key": "timeout",
            "label": "Timeout (seconds)",
            "type": "number",
            "required": False,
            "default": "600",
            "help": "Request timeout for transcription",
        },
    ]

    def __init__(self, **config):
        super().__init__(**config)
        endpoint = config.get("endpoint", "http://subgen:9000")
        self.endpoint = endpoint.rstrip("/") if endpoint else "http://subgen:9000"
        try:
            self.timeout = int(config.get("timeout", "600"))
        except (ValueError, TypeError):
            self.timeout = 600

    def transcribe(
        self,
        audio_path: str,
        language: str = "",
        task: str = "transcribe",
        progress_callback: Callable[[float], None] | None = None,
    ) -> TranscriptionResult:
        """Transcribe audio by sending it to the Subgen /asr endpoint.

        Args:
            audio_path: Path to the audio file (WAV, 16kHz mono)
            language: ISO 639-1 language code
            task: "transcribe" or "translate"
            progress_callback: Optional callback (limited: 10% on start, 90% on response)

        Returns:
            TranscriptionResult with SRT content
        """
        start_time = time.time()

        try:
            # Read audio file
            with open(audio_path, "rb") as f:
                audio_bytes = f.read()

            if progress_callback:
                progress_callback(0.1)  # 10% for upload start

            # POST to /asr endpoint
            resp = requests.post(
                f"{self.endpoint}/asr",
                params={
                    "task": task,
                    "language": language,
                    "output": "srt",
                },
                files={
                    "audio_file": ("audio.wav", audio_bytes, "audio/wav"),
                },
                timeout=self.timeout,
            )

            if progress_callback:
                progress_callback(0.9)  # 90% after response received

            if resp.status_code != 200:
                return TranscriptionResult(
                    success=False,
                    error=f"Subgen API returned HTTP {resp.status_code}: {resp.text[:200]}",
                    backend_name=self.name,
                )

            srt_content = resp.text
            if not srt_content or not srt_content.strip():
                return TranscriptionResult(
                    success=False,
                    error="Subgen returned empty transcription",
                    backend_name=self.name,
                )

            # Parse segment count (double newline separates SRT blocks)
            segment_count = len([b for b in srt_content.strip().split("\n\n") if b.strip()])
            duration = _parse_srt_duration(srt_content)
            elapsed_ms = (time.time() - start_time) * 1000

            logger.info(
                "Subgen transcription complete: %d segments, ~%.1fs duration, %.0fms",
                segment_count,
                duration,
                elapsed_ms,
            )

            return TranscriptionResult(
                srt_content=srt_content,
                detected_language=language,  # Subgen doesn't return this separately
                language_probability=0.0,
                duration_seconds=duration,
                segment_count=segment_count,
                backend_name=self.name,
                processing_time_ms=elapsed_ms,
            )

        except requests.exceptions.Timeout:
            elapsed_ms = (time.time() - start_time) * 1000
            return TranscriptionResult(
                success=False,
                error=f"Subgen request timed out after {self.timeout}s",
                backend_name=self.name,
                processing_time_ms=elapsed_ms,
            )
        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            logger.error("Subgen transcription failed: %s", e)
            return TranscriptionResult(
                success=False,
                error=str(e),
                backend_name=self.name,
                processing_time_ms=elapsed_ms,
            )

    def health_check(self) -> tuple[bool, str]:
        """Check if Subgen is reachable.

        Tries /health first, then falls back to root /.

        Returns:
            (is_healthy, message) tuple
        """
        for path in ["/health", "/"]:
            try:
                resp = requests.get(
                    f"{self.endpoint}{path}",
                    timeout=10,
                )
                if resp.status_code == 200:
                    return True, "OK"
            except Exception:
                continue

        return False, f"Subgen not reachable at {self.endpoint}"

    def get_available_models(self) -> list[dict]:
        """Return empty list (models configured on Subgen side).

        Returns:
            Empty list -- Subgen manages its own models
        """
        return []
