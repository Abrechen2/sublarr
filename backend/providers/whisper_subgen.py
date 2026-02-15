"""Whisper-Subgen subtitle provider -- external ASR service delegation.

Delegates speech-to-text transcription to an external Whisper/Subgen instance.
This is a last-resort provider that generates subtitles from audio when no
existing subtitles are found from other providers.

This is the external Subgen client (PROV-05). Phase 4 will build the full
local Whisper backend. Audio extraction requires ffmpeg to be installed
(included in the Docker image).

License: GPL-3.0
"""

import os
import logging
import shutil
import subprocess

from providers.base import (
    SubtitleProvider,
    SubtitleResult,
    SubtitleFormat,
    VideoQuery,
    ProviderError,
)
from providers import register_provider
from providers.http_session import create_session

logger = logging.getLogger(__name__)

# All Whisper-supported languages (ISO 639-1 codes)
WHISPER_LANGUAGES = {
    "en", "ja", "de", "fr", "es", "it", "pt", "ru", "zh", "ko",
    "ar", "nl", "pl", "sv", "cs", "hu", "tr", "th", "vi", "id",
    "hi", "uk", "ro", "el", "da", "fi", "no", "sk", "hr", "bg",
    "lt", "lv", "sl", "et", "ms", "he", "ca", "ta", "te", "bn",
    "ml", "ka", "sr", "mk", "is", "gl", "eu", "af", "cy", "be",
    "ur", "sw", "tl", "fa", "az", "kk", "hy", "my", "ne", "mn",
    "bs", "sq", "lb", "mt",
}


def _check_ffmpeg() -> bool:
    """Check if ffmpeg is available on the system."""
    return shutil.which("ffmpeg") is not None


@register_provider
class WhisperSubgenProvider(SubtitleProvider):
    """Whisper-Subgen provider -- delegates transcription to an external Subgen instance."""

    name = "whisper_subgen"
    languages = WHISPER_LANGUAGES

    # Plugin system attributes
    config_fields = [
        {
            "key": "endpoint",
            "label": "Subgen URL",
            "type": "text",
            "required": True,
            "default": "http://subgen:9000",
        },
        {
            "key": "timeout",
            "label": "Timeout (seconds)",
            "type": "number",
            "required": False,
            "default": "600",
        },
    ]
    rate_limit = (2, 60)  # very conservative: transcription is slow
    timeout = 600  # 10 minutes for long files
    max_retries = 1  # don't retry expensive operations

    def __init__(self, endpoint: str = "http://subgen:9000", timeout: str = "600", **kwargs):
        super().__init__(**kwargs)
        self.endpoint = endpoint.rstrip("/") if endpoint else "http://subgen:9000"
        try:
            self.config_timeout = int(timeout) if timeout else 600
        except (ValueError, TypeError):
            self.config_timeout = 600
        self.session = None
        self._ffmpeg_available = None  # Lazy check

    def initialize(self):
        logger.debug("WhisperSubgen: initializing (endpoint: %s, timeout: %ds)",
                     self.endpoint, self.config_timeout)
        self.session = create_session(
            max_retries=1,
            backoff_factor=2.0,
            timeout=self.config_timeout,
            user_agent="Sublarr/1.0",
        )
        # Check ffmpeg availability
        self._ffmpeg_available = _check_ffmpeg()
        if not self._ffmpeg_available:
            logger.warning(
                "WhisperSubgen: ffmpeg not found -- audio extraction will fail. "
                "Install ffmpeg or ensure it's in PATH."
            )

    def terminate(self):
        if self.session:
            self.session.close()
            self.session = None

    def health_check(self) -> tuple[bool, str]:
        if not self.session:
            return False, "Not initialized"
        try:
            # Try /health endpoint first, then fall back to root
            for path in ["/health", "/"]:
                try:
                    resp = self.session.get(f"{self.endpoint}{path}", timeout=10)
                    if resp.status_code == 200:
                        return True, "OK"
                except Exception:
                    continue
            return False, f"Subgen endpoint not reachable at {self.endpoint}"
        except Exception as e:
            return False, str(e)

    def search(self, query: VideoQuery) -> list[SubtitleResult]:
        if not self.session:
            logger.warning("WhisperSubgen: cannot search -- session is None")
            return []

        # Requires file_path to extract audio from
        if not query.file_path:
            logger.debug("WhisperSubgen: no file_path provided, skipping")
            return []

        if not os.path.exists(query.file_path):
            logger.debug("WhisperSubgen: file not found: %s", query.file_path)
            return []

        # Determine target language
        language = query.languages[0] if query.languages else "en"

        # Do NOT actually transcribe during search.
        # Return a single low-score "generatable" result as a placeholder.
        # This ensures Whisper is only used when no other provider has results.
        result = SubtitleResult(
            provider_name=self.name,
            subtitle_id=f"whisper:{os.path.basename(query.file_path)}",
            language=language,
            format=SubtitleFormat.SRT,
            filename=f"{os.path.splitext(os.path.basename(query.file_path))[0]}.{language}.srt",
            score=10,  # Very low score -- last resort
            matches=set(),  # No matches = lowest priority in scoring
            provider_data={
                "file_path": query.file_path,
                "language": language,
            },
        )

        logger.info(
            "WhisperSubgen: returning placeholder result for '%s' (language: %s, score: 10)",
            query.display_name, language,
        )
        return [result]

    def download(self, result: SubtitleResult) -> bytes:
        """Download (transcribe) by extracting audio and sending to Subgen.

        This is the expensive operation -- actual transcription happens here.
        """
        if not self.session:
            raise ProviderError("WhisperSubgen not initialized")

        file_path = result.provider_data.get("file_path", "")
        if not file_path or not os.path.exists(file_path):
            raise ProviderError(f"WhisperSubgen: media file not found: {file_path}")

        language = result.provider_data.get("language", result.language or "en")

        # Check ffmpeg availability
        if self._ffmpeg_available is None:
            self._ffmpeg_available = _check_ffmpeg()

        if not self._ffmpeg_available:
            raise ProviderError(
                "WhisperSubgen: ffmpeg not found. Install ffmpeg to enable audio extraction. "
                "In Docker, ffmpeg is included by default."
            )

        # Step 1: Extract audio from media file using ffmpeg
        logger.info("WhisperSubgen: extracting audio from %s", os.path.basename(file_path))
        try:
            cmd = [
                "ffmpeg",
                "-i", file_path,
                "-vn",  # No video
                "-acodec", "pcm_s16le",  # PCM 16-bit
                "-ar", "16000",  # 16kHz sample rate (Whisper optimal)
                "-ac", "1",  # Mono
                "-f", "wav",  # WAV format
                "pipe:1",  # Output to stdout
            ]
            proc = subprocess.run(
                cmd,
                capture_output=True,
                timeout=120,  # 2 minutes for audio extraction
            )
            if proc.returncode != 0:
                stderr = proc.stderr.decode("utf-8", errors="replace")[:500]
                raise ProviderError(f"WhisperSubgen: ffmpeg failed (code {proc.returncode}): {stderr}")

            audio_data = proc.stdout
            if not audio_data:
                raise ProviderError("WhisperSubgen: ffmpeg produced no audio output")

            logger.info(
                "WhisperSubgen: extracted audio (%d bytes) from %s",
                len(audio_data), os.path.basename(file_path),
            )
        except subprocess.TimeoutExpired:
            raise ProviderError("WhisperSubgen: ffmpeg audio extraction timed out (120s)")
        except ProviderError:
            raise
        except Exception as e:
            raise ProviderError(f"WhisperSubgen: audio extraction failed: {e}") from e

        # Step 2: POST audio to Subgen /asr endpoint
        logger.info(
            "WhisperSubgen: sending audio to Subgen (%s) for transcription (language: %s)",
            self.endpoint, language,
        )
        try:
            resp = self.session.post(
                f"{self.endpoint}/asr",
                params={
                    "task": "transcribe",
                    "language": language,
                    "output": "srt",
                },
                files={
                    "audio_file": ("audio.wav", audio_data, "audio/wav"),
                },
                timeout=self.config_timeout,
            )

            if resp.status_code != 200:
                raise ProviderError(
                    f"WhisperSubgen: Subgen API returned HTTP {resp.status_code}: "
                    f"{resp.text[:200]}"
                )

            content = resp.content
            if not content:
                raise ProviderError("WhisperSubgen: Subgen returned empty transcription")

            result.content = content
            result.format = SubtitleFormat.SRT
            logger.info(
                "WhisperSubgen: transcription complete (%d bytes SRT)",
                len(content),
            )
            return content

        except ProviderError:
            raise
        except Exception as e:
            raise ProviderError(f"WhisperSubgen: transcription failed: {e}") from e
