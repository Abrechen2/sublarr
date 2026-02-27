"""Faster Whisper backend -- local GPU/CPU transcription.

Uses the faster-whisper library (CTranslate2) for efficient local
speech-to-text transcription. Supports GPU acceleration with CUDA,
VAD filtering for better accuracy, and various model sizes.

The faster-whisper package is optional. If not installed, this backend
simply won't be registered (ImportError caught in whisper/__init__.py).
"""

import logging
import time
from collections.abc import Callable

from whisper.base import TranscriptionResult, WhisperBackend

logger = logging.getLogger(__name__)

# Guard import: faster-whisper is optional
try:
    from faster_whisper import WhisperModel

    HAS_FASTER_WHISPER = True
except ImportError:
    HAS_FASTER_WHISPER = False


def _format_srt_timestamp(seconds: float) -> str:
    """Convert float seconds to SRT timestamp format HH:MM:SS,mmm."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


class FasterWhisperBackend(WhisperBackend):
    """Local faster-whisper transcription backend.

    Uses CTranslate2 for efficient inference with support for GPU (CUDA)
    and CPU modes. Lazy-loads the model on first transcription to avoid
    holding GPU memory when idle.
    """

    name = "faster_whisper"
    display_name = "Faster Whisper (Local)"
    supports_gpu = True
    supports_language_detection = True
    config_fields = [
        {
            "key": "model_size",
            "label": "Model Size",
            "type": "text",
            "required": True,
            "default": "medium",
            "help": "Model: tiny, base, small, medium, large-v2, large-v3, distil-large-v3",
        },
        {
            "key": "device",
            "label": "Device",
            "type": "text",
            "required": False,
            "default": "auto",
            "help": "auto, cuda, or cpu",
        },
        {
            "key": "compute_type",
            "label": "Compute Type",
            "type": "text",
            "required": False,
            "default": "auto",
            "help": "float16, int8_float16, int8, float32, or auto",
        },
        {
            "key": "cpu_threads",
            "label": "CPU Threads",
            "type": "number",
            "required": False,
            "default": "4",
            "help": "Number of CPU threads (CPU mode only)",
        },
        {
            "key": "beam_size",
            "label": "Beam Size",
            "type": "number",
            "required": False,
            "default": "5",
            "help": "Beam search size (higher = more accurate, slower)",
        },
        {
            "key": "vad_filter",
            "label": "VAD Filter",
            "type": "text",
            "required": False,
            "default": "true",
            "help": "Enable Silero VAD for better accuracy (recommended for anime)",
        },
        {
            "key": "model_path",
            "label": "Model Storage Path",
            "type": "text",
            "required": False,
            "default": "/config/whisper-models",
            "help": "Directory for downloaded models",
        },
    ]

    def __init__(self, **config):
        super().__init__(**config)
        self._model = None
        self._loaded_model_size = None
        self._loaded_device = None
        self._loaded_compute_type = None

    def _get_or_load_model(self):
        """Lazy-load the WhisperModel, caching until config changes.

        Only reloads if model_size, device, or compute_type changed since
        last load. Logs model loading time.
        """
        if not HAS_FASTER_WHISPER:
            raise RuntimeError("faster-whisper package not installed")

        model_size = self.config.get("model_size", "medium")
        device = self.config.get("device", "auto")
        compute_type = self.config.get("compute_type", "auto")
        cpu_threads = int(self.config.get("cpu_threads", "4"))
        model_path = self.config.get("model_path", "/config/whisper-models")

        # Check if we need to reload
        if (
            self._model is not None
            and self._loaded_model_size == model_size
            and self._loaded_device == device
            and self._loaded_compute_type == compute_type
        ):
            return self._model

        # Release old model
        if self._model is not None:
            del self._model
            self._model = None

        logger.info(
            "Loading Whisper model '%s' (device=%s, compute_type=%s, threads=%d)",
            model_size,
            device,
            compute_type,
            cpu_threads,
        )

        start = time.time()
        self._model = WhisperModel(
            model_size,
            device=device,
            compute_type=compute_type,
            cpu_threads=cpu_threads,
            download_root=model_path,
        )
        elapsed = time.time() - start

        self._loaded_model_size = model_size
        self._loaded_device = device
        self._loaded_compute_type = compute_type

        logger.info("Whisper model '%s' loaded in %.1fs", model_size, elapsed)
        return self._model

    def transcribe(
        self,
        audio_path: str,
        language: str = "",
        task: str = "transcribe",
        progress_callback: Callable[[float], None] | None = None,
    ) -> TranscriptionResult:
        """Transcribe audio using faster-whisper with VAD filtering.

        Args:
            audio_path: Path to the audio file (WAV, 16kHz mono)
            language: ISO 639-1 language code (empty = auto-detect)
            task: "transcribe" or "translate"
            progress_callback: Optional callback with progress ratio (0.0 - 1.0)

        Returns:
            TranscriptionResult with SRT content and metadata
        """
        try:
            model = self._get_or_load_model()
        except Exception as e:
            return TranscriptionResult(
                success=False,
                error=f"Failed to load model: {e}",
                backend_name=self.name,
            )

        beam_size = int(self.config.get("beam_size", "5"))
        vad_filter_str = self.config.get("vad_filter", "true")
        vad_filter = vad_filter_str.lower() in ("true", "1", "yes")

        start_time = time.time()

        try:
            segments_gen, info = model.transcribe(
                audio_path,
                language=language or None,
                task=task,
                beam_size=beam_size,
                vad_filter=vad_filter,
                vad_parameters={
                    "min_silence_duration_ms": 500,
                    "speech_pad_ms": 400,
                },
                word_timestamps=False,
            )

            # Build SRT content from segments
            srt_lines = []
            segment_count = 0
            duration = info.duration if info.duration else 0.0

            for segment in segments_gen:
                segment_count += 1
                start_ts = _format_srt_timestamp(segment.start)
                end_ts = _format_srt_timestamp(segment.end)
                text = segment.text.strip()

                srt_lines.append(str(segment_count))
                srt_lines.append(f"{start_ts} --> {end_ts}")
                srt_lines.append(text)
                srt_lines.append("")  # Blank line separator

                # Progress callback based on segment position vs total duration
                if progress_callback and duration > 0:
                    ratio = min(segment.end / duration, 1.0)
                    progress_callback(ratio)

            srt_content = "\n".join(srt_lines)
            elapsed_ms = (time.time() - start_time) * 1000

            logger.info(
                "Transcription complete: %d segments, %.1fs duration, detected=%s (%.1f%%), %.0fms",
                segment_count,
                duration,
                info.language,
                info.language_probability * 100,
                elapsed_ms,
            )

            return TranscriptionResult(
                srt_content=srt_content,
                detected_language=info.language,
                language_probability=info.language_probability,
                duration_seconds=duration,
                segment_count=segment_count,
                backend_name=self.name,
                processing_time_ms=elapsed_ms,
            )

        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            logger.error("Faster Whisper transcription failed: %s", e)
            return TranscriptionResult(
                success=False,
                error=str(e),
                backend_name=self.name,
                processing_time_ms=elapsed_ms,
            )

    def health_check(self) -> tuple[bool, str]:
        """Check if faster-whisper is installed and model can be loaded.

        Returns:
            (is_healthy, message) tuple
        """
        if not HAS_FASTER_WHISPER:
            return False, "faster-whisper not installed"

        try:
            self._get_or_load_model()
            model_size = self.config.get("model_size", "medium")
            device = self.config.get("device", "auto")
            return True, f"Model {model_size} loaded on {device}"
        except Exception as e:
            return False, str(e)

    def get_available_models(self) -> list[dict]:
        """Return list of available Whisper model sizes.

        Returns:
            Static list of model info dicts
        """
        return [
            {"name": "tiny", "size": "~150MB"},
            {"name": "base", "size": "~300MB"},
            {"name": "small", "size": "~900MB"},
            {"name": "medium", "size": "~3GB"},
            {"name": "large-v2", "size": "~6GB"},
            {"name": "large-v3", "size": "~6GB"},
            {"name": "distil-large-v3", "size": "~1.5GB"},
        ]
