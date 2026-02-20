# Phase 4: Whisper Speech-to-Text - Research

**Researched:** 2026-02-15
**Domain:** Speech-to-text transcription (Whisper), audio extraction (ffmpeg), queue management
**Confidence:** HIGH

## Summary

Phase 4 adds Whisper speech-to-text as the ultimate fallback when no subtitle providers can find subtitles for a media file. This extends the existing translation pipeline from Cases A-C (skip/upgrade/full) with a new Case D: transcribe audio to SRT using Whisper, then optionally translate. Two Whisper backends are needed: **faster-whisper** (local, GPU/CPU via CTranslate2) and **Subgen API** (external HTTP service). The architecture follows the ABC + Manager + circuit breaker + config_fields pattern already established in Phases 2 (TranslationBackend) and 3 (MediaServer).

The primary technical challenges are: (1) audio track selection from MKV files using ffmpeg/ffprobe (preferring Japanese or configured source language), (2) a dedicated queue system for long-running Whisper jobs with progress tracking via WebSocket, (3) correct integration into the translation pipeline at the right fallback point, and (4) the existing `WhisperSubgenProvider` (from Phase 1, PROV-05) needs to be refactored from a SubtitleProvider into the new WhisperBackend ABC system, since transcription is fundamentally different from subtitle file download.

**Primary recommendation:** Create a `whisper/` package following the exact same pattern as `translation/` and `mediaserver/`: ABC base class, Manager singleton with circuit breakers, two backends (faster-whisper local + Subgen HTTP), config stored as JSON array in config_entries. Add Case D to translator.py after Case C4 fails. Use a dedicated `whisper_jobs` DB table and threading.Semaphore for concurrency control with WebSocket progress events.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| faster-whisper | 1.2.1 | Local Whisper transcription via CTranslate2 | 4x faster than openai/whisper, less memory, GPU+CPU, Silero VAD built-in |
| ffmpeg (system) | 6.x+ | Audio track extraction from MKV files | Already in Docker image and used throughout codebase |
| pysubs2 | 1.7.3 | Parse Whisper SRT output into subtitle objects | Already a dependency, handles SRT/ASS parsing |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| requests | 2.32.3 | HTTP client for Subgen API backend | Already a dependency |
| flask-socketio | 5.4.1 | WebSocket progress events for Whisper jobs | Already a dependency |
| threading.Semaphore | stdlib | Concurrency limiter for Whisper jobs | Max-concurrent control |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| faster-whisper | openai/whisper | 4x slower, more memory, PyTorch required |
| faster-whisper | whisper.cpp | C++ binary, harder to integrate with Python |
| threading.Semaphore | asyncio.Semaphore | Flask is sync; threading fits the existing pattern |
| SRT output from Whisper | VTT output | SRT is already the standard fallback format in translator.py |

**Installation (backend/requirements.txt addition):**
```bash
# faster-whisper is optional -- only needed for local Whisper backend
# Install with: pip install faster-whisper
# GPU requires: CUDA 12 + cuDNN 9 (or downgrade ctranslate2 for CUDA 11)
faster-whisper>=1.2.0
```

**Docker consideration:** faster-whisper should be an optional dependency (like `deepl`, `openai`, `PlexAPI`). The base Docker image stays slim (CPU-only). Users who want local Whisper add faster-whisper to their requirements or use a GPU-enabled image variant. Subgen API backend needs zero additional dependencies.

## Architecture Patterns

### Recommended Project Structure
```
backend/
  whisper/                     # New package (mirrors translation/, mediaserver/)
    __init__.py                # WhisperManager singleton, register_backends(), get_whisper_manager()
    base.py                    # WhisperBackend ABC, TranscriptionResult dataclass
    faster_whisper_backend.py  # Local faster-whisper backend (CTranslate2, GPU/CPU)
    subgen_backend.py          # External Subgen API backend (HTTP)
    audio.py                   # Audio extraction: ffprobe audio track selection, ffmpeg extraction
    queue.py                   # WhisperQueue: Semaphore-based concurrency, progress tracking
  db/
    whisper.py                 # New: whisper_jobs table CRUD, whisper_stats
  routes/
    whisper.py                 # New: Whisper API blueprint (POST /transcribe, GET /queue, etc.)
  translator.py                # Modified: add Case D after C4
```

### Pattern 1: WhisperBackend ABC (mirrors TranslationBackend and MediaServer)
**What:** Abstract base class defining the contract for all Whisper backends
**When to use:** Every Whisper backend implements this interface
**Example:**
```python
# Source: Modeled after translation/base.py and mediaserver/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Callable

@dataclass
class TranscriptionResult:
    """Result from a Whisper transcription."""
    srt_content: str = ""             # Raw SRT output
    detected_language: str = ""       # ISO 639-1 code
    language_probability: float = 0.0 # Confidence 0-1
    duration_seconds: float = 0.0     # Audio duration
    segment_count: int = 0            # Number of subtitle segments
    backend_name: str = ""
    processing_time_ms: float = 0.0
    error: Optional[str] = None
    success: bool = True

class WhisperBackend(ABC):
    """Abstract base class for Whisper transcription backends."""

    name: str = "unknown"
    display_name: str = "Unknown"
    config_fields: list[dict] = []
    supports_gpu: bool = False
    supports_language_detection: bool = True

    def __init__(self, **config):
        self.config = config

    @abstractmethod
    def transcribe(
        self,
        audio_path: str,
        language: str = "",
        task: str = "transcribe",
        progress_callback: Optional[Callable[[float], None]] = None,
    ) -> TranscriptionResult:
        """Transcribe audio file to SRT subtitle content."""
        ...

    @abstractmethod
    def health_check(self) -> tuple[bool, str]:
        """Check if the backend is available."""
        ...

    @abstractmethod
    def get_available_models(self) -> list[dict]:
        """Return available models with size/description."""
        ...
```

### Pattern 2: WhisperManager Singleton (mirrors TranslationManager)
**What:** Manages backend instances, config loading, circuit breakers
**When to use:** Single entry point for all Whisper operations
**Key difference from TranslationManager:** Whisper is not a fallback chain like translation. It uses ONE configured backend (local OR external), not a chain. More like MediaServerManager in terms of config (JSON array for multiple instances is NOT needed -- single backend selection is sufficient since you either run local Whisper or delegate to Subgen, not both simultaneously).
**Example:**
```python
# Source: Modeled after translation/__init__.py
class WhisperManager:
    def __init__(self):
        self._backend_classes: dict[str, type[WhisperBackend]] = {}
        self._backend: Optional[WhisperBackend] = None
        self._circuit_breaker: Optional[CircuitBreaker] = None

    def transcribe(
        self,
        audio_path: str,
        language: str = "",
        progress_callback=None,
    ) -> TranscriptionResult:
        """Transcribe using the configured backend."""
        backend = self._get_active_backend()
        if not backend:
            return TranscriptionResult(success=False, error="No Whisper backend configured")
        # ... circuit breaker check, call backend.transcribe(), record stats
```

### Pattern 3: Audio Track Selection (new utility)
**What:** Use ffprobe to find the source language audio track, extract with ffmpeg to WAV
**When to use:** Before any Whisper transcription
**Key insight:** The existing `run_ffprobe()` in ass_utils.py uses `-select_streams s` (subtitle only). Audio extraction needs a new ffprobe call with `-select_streams a` for audio streams, or a unified probe that gets all streams.
**Example:**
```python
# Source: Extends existing ass_utils.py ffprobe pattern
def select_audio_track(file_path: str, preferred_language: str = "ja") -> dict:
    """Select the best audio track for transcription.

    Priority:
    1. Audio track matching preferred_language (e.g., "ja", "jpn")
    2. First audio track if no language match
    3. Default audio track

    Returns: {"stream_index": int, "language": str, "codec": str, "channels": int}
    """
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        "-select_streams", "a",  # Audio streams only
        file_path,
    ]
    # ... parse JSON, match language tags, return best match

def extract_audio_to_wav(file_path: str, stream_index: int, output_path: str) -> str:
    """Extract audio track to 16kHz mono WAV (Whisper optimal format).

    Uses ffmpeg with:
      -map 0:a:{stream_index}  # Select specific audio track
      -acodec pcm_s16le        # 16-bit PCM
      -ar 16000                # 16kHz (Whisper native)
      -ac 1                    # Mono
    """
```

### Pattern 4: Whisper Queue with Progress (new)
**What:** Dedicated queue for long-running Whisper jobs with concurrency control
**When to use:** Every Whisper transcription request goes through the queue
**Key design:** Use threading.Semaphore (NOT a full job queue library) since the existing codebase uses threading for all background work (see routes/translate.py _run_job pattern). Track progress via segments/duration ratio and emit WebSocket events.
**Example:**
```python
class WhisperQueue:
    def __init__(self, max_concurrent: int = 1):
        self._semaphore = threading.Semaphore(max_concurrent)
        self._jobs: dict[str, WhisperJob] = {}
        self._lock = threading.Lock()

    def submit(self, job_id: str, file_path: str, language: str, ...) -> str:
        """Submit a transcription job. Returns job_id."""
        thread = threading.Thread(target=self._run_job, args=(job_id,), daemon=True)
        thread.start()
        return job_id

    def _run_job(self, job_id: str):
        with self._semaphore:
            # ... extract audio, transcribe, emit progress via socketio
            socketio.emit("whisper_progress", {
                "job_id": job_id,
                "progress": 0.5,  # 50%
                "status": "transcribing",
            })
```

### Pattern 5: Case D Integration in translator.py
**What:** After Case C4 (no source subtitle found), try Whisper transcription
**When to use:** Only when whisper is enabled in config AND all provider searches failed
**Example:**
```python
# In translate_file() after Case C4:
# === CASE D: Whisper transcription as last resort ===
if _is_whisper_enabled():
    logger.info("Case D: No subtitle source found, attempting Whisper transcription")
    whisper_result = _transcribe_with_whisper(mkv_path, arr_context)
    if whisper_result and whisper_result["success"]:
        # Whisper produces SRT in source language
        # Now translate it using the normal translation pipeline
        src_srt_path = whisper_result["output_path"]
        result = translate_srt_from_file(
            mkv_path, src_srt_path, source="whisper",
            target_language=tgt_lang, arr_context=arr_context,
        )
        if result and result["success"]:
            result["stats"]["whisper_source"] = True
            _record_config_hash_for_result(result, mkv_path)
            _notify_integrations(arr_context, file_path=mkv_path)
        return result

    # Still nothing
    logger.warning("Case D: Whisper transcription also failed for %s", mkv_path)
```

### Anti-Patterns to Avoid
- **Running Whisper in the request thread:** Transcription takes minutes. ALWAYS use background thread + WebSocket progress. Never block an HTTP request.
- **Loading faster-whisper model on every transcription:** Model loading takes 10-30 seconds. Cache the WhisperModel instance in the backend. Only reload when model config changes.
- **Extracting audio to pipe:** The existing WhisperSubgenProvider pipes audio to stdout. For local faster-whisper, write to a temp file instead -- faster-whisper's `transcribe()` accepts a file path and handles memory-mapped reading efficiently.
- **Ignoring VAD (Voice Activity Detection):** Always enable `vad_filter=True` for anime content -- it dramatically improves accuracy by filtering silence, music intros, and non-speech audio.
- **Hardcoding Japanese:** The source language comes from config/profile. Use the configured source_language, not a hardcoded "ja".

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Speech-to-text | Custom ASR pipeline | faster-whisper | Months of ML work, 4x slower without CTranslate2 |
| Voice activity detection | Silence detection heuristics | Silero VAD (built into faster-whisper) | ML-based, handles music/noise, 1.8MB model |
| Audio format conversion | Manual PCM encoding | ffmpeg subprocess | Handles all codecs, battle-tested |
| SRT timestamp generation | Manual timestamp formatting | faster-whisper segment output + pysubs2 | Segment.start/end already in seconds, pysubs2 formats correctly |
| Language detection | Custom language classifier | faster-whisper language_probability | Whisper has built-in language detection with confidence scores |
| Concurrency control | Custom lock/queue library | threading.Semaphore | stdlib, matches existing codebase pattern |
| Progress tracking | Custom progress calculation | Segment count / total duration ratio | Whisper yields segments as generator, easy to track |

**Key insight:** faster-whisper provides everything needed: transcription, VAD, language detection, word timestamps, model management, GPU/CPU selection. The main work is integration plumbing, not ASR logic.

## Common Pitfalls

### Pitfall 1: Model Loading Time
**What goes wrong:** First transcription takes 30+ seconds just to load the model, user thinks it's broken
**Why it happens:** CTranslate2 models are 500MB-3GB, loaded into GPU/CPU memory on first use
**How to avoid:** Lazy-load the model on first transcribe() call, cache it in the backend instance. Add a "warm up" option in health_check that pre-loads the model. Show "Loading model..." status in the UI.
**Warning signs:** health_check passes but first transcription is extremely slow

### Pitfall 2: GPU Memory Exhaustion
**What goes wrong:** CUDA out-of-memory error during transcription, especially with large-v3 model
**Why it happens:** large-v3 needs ~6GB VRAM; concurrent transcriptions double the requirement
**How to avoid:** Default to `max_concurrent_whisper: 1` for GPU mode. Use `compute_type: "int8_float16"` for 50% memory reduction. Provide model size guidance in UI (tiny=~150MB, base=~300MB, small=~900MB, medium=~3GB, large=~6GB).
**Warning signs:** Transcription starts then crashes with CUDA OOM

### Pitfall 3: Audio Track Selection Fails
**What goes wrong:** Whisper transcribes the wrong language (e.g., English dub instead of Japanese)
**Why it happens:** MKV files have multiple audio tracks; first track may not be the source language
**How to avoid:** Use ffprobe to list all audio tracks, match against configured source_language using ISO 639 language tags. Fall back to first track only if no language match. Log which track was selected.
**Warning signs:** Whisper language detection returns unexpected language, translation quality is poor

### Pitfall 4: Existing WhisperSubgenProvider Confusion
**What goes wrong:** Two Whisper systems coexist: the old SubtitleProvider and the new WhisperBackend
**Why it happens:** Phase 1 created WhisperSubgenProvider as a subtitle provider. Phase 4 creates proper Whisper backends.
**How to avoid:** Deprecate and remove WhisperSubgenProvider from providers/. Migrate its Subgen HTTP logic to the new whisper/subgen_backend.py. The provider scoring approach (score=10) was a workaround; Case D in translator.py is the correct integration point.
**Warning signs:** Both systems try to transcribe the same file

### Pitfall 5: ffmpeg Audio Extraction Produces Huge WAV Files
**What goes wrong:** A 24-minute anime episode produces a 500MB+ WAV file
**Why it happens:** Uncompressed PCM at even 16kHz mono is ~1.9MB/minute, but anime episodes can be 24+ minutes = ~46MB. The real issue is if someone forgets `-ac 1` (mono) or uses a higher sample rate.
**How to avoid:** Always use `-ar 16000 -ac 1 -acodec pcm_s16le`. Consider streaming the audio via pipe for Subgen (already works in existing WhisperSubgenProvider), but use temp file for local faster-whisper. Clean up temp files in finally blocks.
**Warning signs:** Disk space warnings, slow extraction

### Pitfall 6: Language Detection Mismatch
**What goes wrong:** Whisper detects "zh" (Chinese) for Japanese audio, or "en" for German-dubbed content
**Why it happens:** Whisper's language detection is not 100% accurate, especially for related languages or mixed-language content
**How to avoid:** Compare detected language against expected source_language from config. If mismatch and confidence > 0.8, warn but proceed. If mismatch and confidence < 0.5, reject and log. Allow user override.
**Warning signs:** TranscriptionResult.detected_language differs from expected source_language

### Pitfall 7: Progress Tracking is Imprecise
**What goes wrong:** Progress bar jumps erratically or stays at 0% for a long time
**Why it happens:** faster-whisper's `transcribe()` returns a generator of segments. You only know progress once segments start yielding. No callback for internal beam search progress.
**How to avoid:** Multi-phase progress: (1) "Extracting audio" 0-10%, (2) "Loading model" 10-20%, (3) "Transcribing" 20-95% (based on segment.end / total_duration), (4) "Saving" 95-100%. Use TranscriptionInfo.duration to calculate total duration upfront.
**Warning signs:** Progress stays at 20% for minutes (model loading or slow initial segment)

## Code Examples

### Faster-whisper Local Transcription
```python
# Source: https://github.com/SYSTRAN/faster-whisper (verified v1.2.1)
from faster_whisper import WhisperModel

model = WhisperModel(
    "medium",           # Model size: tiny, base, small, medium, large-v2, large-v3
    device="cuda",      # "cuda" or "cpu" or "auto"
    compute_type="float16",  # "float16", "int8_float16", "int8", "float32"
    cpu_threads=4,      # Only relevant for CPU mode
    num_workers=1,      # Parallel decoder workers
)

segments, info = model.transcribe(
    "audio.wav",
    language="ja",          # ISO 639-1; omit for auto-detection
    task="transcribe",      # "transcribe" or "translate" (translate=English output)
    beam_size=5,
    vad_filter=True,        # Enable Silero VAD for better accuracy
    vad_parameters={
        "min_silence_duration_ms": 500,    # Minimum silence to split
        "speech_pad_ms": 400,              # Padding around speech
    },
    word_timestamps=False,  # Not needed for subtitle generation
    log_progress=True,      # Print progress to stderr
)

# info.language = "ja", info.language_probability = 0.98
# info.duration = 1440.5 (seconds), info.duration_after_vad = 1200.3

srt_lines = []
for i, segment in enumerate(segments):
    # segment.start = 1.5, segment.end = 3.8, segment.text = "..."
    srt_lines.append(f"{i+1}")
    srt_lines.append(f"{_format_ts(segment.start)} --> {_format_ts(segment.end)}")
    srt_lines.append(segment.text.strip())
    srt_lines.append("")

srt_content = "\n".join(srt_lines)
```

### Subgen API /asr Endpoint Call
```python
# Source: https://github.com/McCloudS/subgen (verified 2026)
import requests

def transcribe_via_subgen(endpoint: str, audio_data: bytes, language: str = "ja") -> str:
    """Send audio to Subgen /asr endpoint, get SRT back."""
    resp = requests.post(
        f"{endpoint}/asr",
        params={
            "task": "transcribe",
            "language": language,
            "output": "srt",
        },
        files={
            "audio_file": ("audio.wav", audio_data, "audio/wav"),
        },
        timeout=600,  # Transcription can be slow
    )
    resp.raise_for_status()
    return resp.text  # SRT content as string
```

### Audio Track Selection with ffprobe
```python
# Source: Extends existing ass_utils.py run_ffprobe pattern
import subprocess
import json

def get_audio_streams(file_path: str) -> list[dict]:
    """Get all audio streams from a media file."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        "-select_streams", "a",
        file_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr}")
    data = json.loads(result.stdout)
    return data.get("streams", [])

def select_source_audio_track(streams: list[dict], source_language: str = "ja") -> int:
    """Select the audio track index matching the source language.

    Language matching uses ISO 639 tags from stream metadata.
    Japanese maps to both "ja" and "jpn".
    """
    # Build language tag mapping
    from config import _get_language_tags
    source_tags = _get_language_tags(source_language)

    # Priority 1: Match by language tag
    for stream in streams:
        lang = stream.get("tags", {}).get("language", "").lower()
        if lang in source_tags:
            return stream.get("index", 0)

    # Priority 2: First audio stream (default)
    if streams:
        return streams[0].get("index", 0)

    raise RuntimeError("No audio streams found in file")
```

### WebSocket Progress Events
```python
# Source: Follows existing routes/translate.py pattern
from extensions import socketio

def emit_whisper_progress(job_id: str, phase: str, progress: float, message: str = ""):
    """Emit a Whisper job progress event via WebSocket."""
    socketio.emit("whisper_progress", {
        "job_id": job_id,
        "phase": phase,       # "extracting", "loading", "transcribing", "saving"
        "progress": progress,  # 0.0 to 1.0
        "message": message,
    })

def emit_whisper_completed(job_id: str, result: dict):
    """Emit a Whisper job completion event."""
    socketio.emit("whisper_completed", {
        "job_id": job_id,
        "success": result.get("success", False),
        "detected_language": result.get("detected_language", ""),
        "segment_count": result.get("segment_count", 0),
        "duration_seconds": result.get("duration_seconds", 0),
    })
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| openai/whisper (PyTorch) | faster-whisper (CTranslate2) | 2023 | 4x faster, 50% less memory |
| Manual silence detection | Silero VAD v6 (built-in) | faster-whisper 1.2.1, Oct 2025 | Better segment boundaries |
| CUDA 11 + cuDNN 8 | CUDA 12 + cuDNN 9 | ctranslate2 >= 4.5.0 | Must match GPU driver version |
| Whisper large-v2 | Whisper large-v3 + distil-large-v3 | 2024 | Better accuracy, distilled = faster |
| WhisperSubgenProvider (Phase 1) | WhisperBackend ABC (Phase 4) | This phase | Proper integration, no provider hack |

**Deprecated/outdated:**
- `ctranslate2 < 4.5.0` for CUDA 12: Use 4.5.0+ for cuDNN 9 support
- `openai/whisper` package: Use faster-whisper instead (drop-in replacement with better performance)
- Piping audio via stdout to Subgen: Works but temp file is more reliable for local faster-whisper

## Open Questions

1. **Docker image strategy for GPU support**
   - What we know: Base Sublarr image is `python:3.11-slim` with ffmpeg. faster-whisper GPU needs CUDA 12 + cuDNN 9 runtime (~3GB+ image).
   - What's unclear: Ship two Docker images (CPU vs GPU)? Or make faster-whisper purely optional and document GPU setup?
   - Recommendation: Keep faster-whisper as an optional pip install. Document two Dockerfile variants. The default image stays slim. Users wanting local Whisper build a custom image or use the GPU variant. Subgen API backend works with zero extra dependencies.

2. **Should Case D be synchronous or always queued?**
   - What we know: Translation (Case A-C) runs synchronously in the job thread. Whisper takes 2-30 minutes.
   - What's unclear: If a wanted search triggers Case D, should it block the wanted search thread or submit to the Whisper queue?
   - Recommendation: When triggered from translate_file() (wanted search, webhook), submit to Whisper queue and return a "whisper_pending" status. The queue worker handles transcription and re-enters the translation pipeline. Manual "Transcribe" button submits directly to queue.

3. **Model storage location**
   - What we know: faster-whisper auto-downloads models from HuggingFace Hub to a default cache dir.
   - What's unclear: Should models go in /config (persistent Docker volume) or a separate /models volume?
   - Recommendation: Default `download_root` to `/config/whisper-models/` (inside the config volume). This survives container recreation. Make it configurable via `whisper_model_path` config entry.

## Sources

### Primary (HIGH confidence)
- faster-whisper GitHub (https://github.com/SYSTRAN/faster-whisper) -- API signatures, constructor params, VAD config, v1.2.1
- faster-whisper PyPI (https://pypi.org/project/faster-whisper/) -- Version 1.2.1, Python >=3.9, dependencies
- faster-whisper transcribe.py source (https://github.com/SYSTRAN/faster-whisper/blob/master/faster_whisper/transcribe.py) -- Full transcribe() signature, Segment/TranscriptionInfo fields
- Existing codebase: `backend/providers/whisper_subgen.py` -- Current Subgen integration, audio extraction pattern
- Existing codebase: `backend/translation/base.py`, `backend/translation/__init__.py` -- ABC + Manager pattern
- Existing codebase: `backend/mediaserver/base.py`, `backend/mediaserver/__init__.py` -- ABC + Manager pattern
- Existing codebase: `backend/translator.py` -- Full translation pipeline Cases A-C, integration points
- Existing codebase: `backend/ass_utils.py` -- run_ffprobe(), ffmpeg usage patterns

### Secondary (MEDIUM confidence)
- Subgen GitHub (https://github.com/McCloudS/subgen) -- /asr endpoint, Docker images, env vars
- Subgen README (https://github.com/McCloudS/subgen/blob/main/README.md) -- API documentation, configuration
- faster-whisper VAD documentation (https://github.com/SYSTRAN/faster-whisper/blob/master/faster_whisper/vad.py) -- Silero VAD v6 parameters
- faster-whisper releases (https://github.com/SYSTRAN/faster-whisper/releases) -- v1.2.1 changelog, Silero VAD v6 upgrade

### Tertiary (LOW confidence)
- Subgen /asr endpoint internals -- Could not read source code directly (404 on blob URL). API contract inferred from README, existing WhisperSubgenProvider, and Bazarr wiki. Need to verify exact query params and response format.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- faster-whisper is the de facto standard, well-documented, verified on PyPI
- Architecture: HIGH -- Follows patterns already proven in Phases 2+3 (ABC+Manager+circuit breaker)
- Audio extraction: HIGH -- ffprobe/ffmpeg patterns verified in existing codebase
- Subgen API: MEDIUM -- API inferred from multiple sources but /asr endpoint code not directly verified
- Pitfalls: HIGH -- Based on known Whisper deployment challenges and codebase analysis
- Queue design: MEDIUM -- Threading.Semaphore fits codebase pattern but hasn't been tested for long-running jobs

**Research date:** 2026-02-15
**Valid until:** 2026-03-15 (faster-whisper is stable, 30-day window appropriate)
