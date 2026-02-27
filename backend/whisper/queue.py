"""Whisper transcription queue with concurrency control.

Manages transcription jobs with a Semaphore-based concurrency limiter,
progress tracking via WebSocket, and persistent state in the whisper_jobs
DB table.
"""

import logging
import os
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from whisper.base import TranscriptionResult

if TYPE_CHECKING:
    from whisper import WhisperManager

logger = logging.getLogger(__name__)


@dataclass
class WhisperJob:
    """In-memory representation of a whisper transcription job."""

    job_id: str
    file_path: str
    language: str = ""
    status: str = "queued"  # queued/extracting/transcribing/saving/completed/failed/cancelled
    progress: float = 0.0
    phase: str = ""
    result: TranscriptionResult | None = None
    error: str | None = None
    created_at: str = ""
    started_at: str | None = None
    completed_at: str | None = None


class WhisperQueue:
    """Queue for managing Whisper transcription jobs with concurrency control.

    Uses a threading.Semaphore to limit concurrent transcriptions (typically 1
    for GPU workloads). Jobs are tracked in-memory and persisted to the DB.
    """

    def __init__(self, max_concurrent: int = 1):
        self._semaphore = threading.Semaphore(max_concurrent)
        self._jobs: dict[str, WhisperJob] = {}
        self._lock = threading.Lock()
        self._max_concurrent = max_concurrent

    def submit(
        self,
        job_id: str,
        file_path: str,
        language: str,
        source_language: str,
        whisper_manager: "WhisperManager",
        socketio=None,
    ) -> str:
        """Submit a new transcription job.

        Creates the job in-memory and in the DB, then starts a daemon thread
        for execution.

        Args:
            job_id: Unique job identifier
            file_path: Path to the media file
            language: Target language for transcription
            source_language: Source audio language for track selection
            whisper_manager: WhisperManager instance for transcription
            socketio: Optional Socket.IO instance for progress events

        Returns:
            The job_id
        """
        now = datetime.utcnow().isoformat()
        job = WhisperJob(
            job_id=job_id,
            file_path=file_path,
            language=language,
            status="queued",
            created_at=now,
        )

        with self._lock:
            self._jobs[job_id] = job

        # Persist to DB
        try:
            from db.whisper import create_whisper_job

            create_whisper_job(job_id, file_path, language)
        except Exception as e:
            logger.error("Failed to persist whisper job %s to DB: %s", job_id, e)

        # Start worker thread
        thread = threading.Thread(
            target=self._run_job,
            args=(job_id, file_path, language, source_language, whisper_manager, socketio),
            daemon=True,
            name=f"whisper-job-{job_id}",
        )
        thread.start()

        logger.info("Submitted whisper job %s for %s (language: %s)", job_id, file_path, language)
        return job_id

    def get_job(self, job_id: str) -> WhisperJob | None:
        """Get a job by ID."""
        with self._lock:
            return self._jobs.get(job_id)

    def get_all_jobs(self) -> list[WhisperJob]:
        """Get all jobs."""
        with self._lock:
            return list(self._jobs.values())

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a job (best-effort, cannot interrupt active transcription).

        Args:
            job_id: Job to cancel

        Returns:
            True if the job was found and marked as cancelled
        """
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return False
            if job.status in ("completed", "failed", "cancelled"):
                return False
            job.status = "cancelled"

        # Update DB
        try:
            from db.whisper import update_whisper_job

            update_whisper_job(job_id, status="cancelled")
        except Exception as e:
            logger.error("Failed to update cancelled job %s in DB: %s", job_id, e)

        logger.info("Cancelled whisper job %s", job_id)
        return True

    def _run_job(
        self,
        job_id: str,
        file_path: str,
        language: str,
        source_language: str,
        whisper_manager: "WhisperManager",
        socketio,
    ):
        """Execute a transcription job within the semaphore.

        Phases:
        1. extracting (0-10%): Select audio track + extract to temp WAV
        2. transcribing (10-95%): Run Whisper transcription
        3. saving (95-100%): Store result
        4. completed (100%): Done
        """
        temp_audio_path = None

        try:
            # Acquire semaphore (blocks if max_concurrent jobs running)
            with self._semaphore:
                # Check if cancelled while waiting
                with self._lock:
                    job = self._jobs.get(job_id)
                    if not job or job.status == "cancelled":
                        return

                now = datetime.utcnow().isoformat()
                self._update_job(
                    job_id, status="extracting", progress=0.0, phase="extracting", started_at=now
                )
                self._emit_progress(socketio, job_id, "extracting", 0.0, "Selecting audio track...")

                # Phase 1: Audio extraction (0-10%)
                from whisper.audio import extract_audio_to_wav, select_audio_track

                track = select_audio_track(
                    file_path, preferred_language=source_language or language or "ja"
                )
                self._update_job(job_id, progress=0.05)
                self._emit_progress(
                    socketio,
                    job_id,
                    "extracting",
                    0.05,
                    f"Extracting audio track {track['stream_index']}...",
                )

                # Create temp file for extracted audio
                temp_fd, temp_audio_path = tempfile.mkstemp(suffix=".wav", prefix="whisper_")
                os.close(temp_fd)

                extract_audio_to_wav(file_path, track["stream_index"], temp_audio_path)
                self._update_job(job_id, progress=0.10)
                self._emit_progress(socketio, job_id, "extracting", 0.10, "Audio extracted")

                # Phase 2: Transcription (10-95%)
                self._update_job(job_id, status="transcribing", phase="transcribing")
                self._emit_progress(
                    socketio, job_id, "transcribing", 0.10, "Starting transcription..."
                )

                def progress_callback(ratio: float):
                    """Map Whisper progress (0-1) to our 10-95% range."""
                    mapped = 0.10 + (ratio * 0.85)
                    self._update_job(job_id, progress=mapped)
                    self._emit_progress(socketio, job_id, "transcribing", mapped, "Transcribing...")

                start_time = time.time()
                result = whisper_manager.transcribe(temp_audio_path, language, progress_callback)
                elapsed_ms = (time.time() - start_time) * 1000

                if not result.success:
                    raise RuntimeError(result.error or "Transcription failed")

                # Phase 3: Saving (95-100%)
                self._update_job(job_id, status="saving", progress=0.95, phase="saving")
                self._emit_progress(socketio, job_id, "saving", 0.95, "Saving result...")

                # Store result
                with self._lock:
                    job = self._jobs.get(job_id)
                    if job:
                        job.result = result

                # Persist to DB
                try:
                    from db.whisper import update_whisper_job

                    update_whisper_job(
                        job_id,
                        status="completed",
                        progress=1.0,
                        phase="completed",
                        backend_name=result.backend_name,
                        detected_language=result.detected_language,
                        language_probability=result.language_probability,
                        srt_content=result.srt_content,
                        segment_count=result.segment_count,
                        duration_seconds=result.duration_seconds,
                        processing_time_ms=elapsed_ms,
                        completed_at=datetime.utcnow().isoformat(),
                    )
                except Exception as e:
                    logger.error("Failed to persist completed job %s: %s", job_id, e)

                # Record Whisper-generated subtitle in download history
                if result.srt_content:
                    try:
                        import os as _os

                        from db.providers import record_subtitle_download

                        srt_path = _os.path.splitext(file_path)[0] + "." + language + ".srt"
                        record_subtitle_download(
                            provider_name="whisper",
                            subtitle_id=job_id,
                            language=language,
                            fmt="srt",
                            file_path=srt_path,
                            score=0,
                            source="whisper",
                        )
                        logger.debug("Whisper job %s: recorded download for %s", job_id, srt_path)
                    except Exception as rec_err:
                        logger.warning(
                            "Whisper job %s: failed to record download: %s", job_id, rec_err
                        )

                # Phase 4: Complete
                self._update_job(
                    job_id,
                    status="completed",
                    progress=1.0,
                    phase="completed",
                    completed_at=datetime.utcnow().isoformat(),
                )
                self._emit_progress(socketio, job_id, "completed", 1.0, "Transcription complete")

                try:
                    from events import emit_event

                    emit_event(
                        "whisper_complete",
                        {
                            "job_id": job_id,
                            "segment_count": result.segment_count,
                            "detected_language": result.detected_language,
                            "duration_seconds": result.duration_seconds,
                            "processing_time_ms": elapsed_ms,
                        },
                    )
                except Exception:
                    pass

                logger.info(
                    "Whisper job %s completed: %d segments, %.1fs duration, %.0fms processing",
                    job_id,
                    result.segment_count,
                    result.duration_seconds,
                    elapsed_ms,
                )

        except Exception as e:
            error_msg = str(e)
            logger.error("Whisper job %s failed: %s", job_id, error_msg)

            self._update_job(
                job_id,
                status="failed",
                error=error_msg,
                completed_at=datetime.utcnow().isoformat(),
            )

            # Persist failure to DB
            try:
                from db.whisper import update_whisper_job

                update_whisper_job(
                    job_id,
                    status="failed",
                    error=error_msg[:500],
                    completed_at=datetime.utcnow().isoformat(),
                )
            except Exception as db_err:
                logger.error("Failed to persist failed job %s: %s", job_id, db_err)

            try:
                from events import emit_event

                emit_event(
                    "whisper_failed",
                    {
                        "job_id": job_id,
                        "error": error_msg[:500],
                    },
                )
            except Exception:
                pass

        finally:
            # Clean up temp audio file
            if temp_audio_path and os.path.exists(temp_audio_path):
                try:
                    os.remove(temp_audio_path)
                    logger.debug("Cleaned up temp audio: %s", temp_audio_path)
                except OSError as e:
                    logger.warning("Failed to clean up temp audio %s: %s", temp_audio_path, e)

    def _update_job(self, job_id: str, **kwargs):
        """Update in-memory job state."""
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            for key, value in kwargs.items():
                if hasattr(job, key):
                    setattr(job, key, value)

    def _emit_progress(self, socketio, job_id: str, phase: str, progress: float, message: str):
        """Emit WebSocket progress event if socketio is available."""
        if socketio is None:
            return
        try:
            socketio.emit(
                "whisper_progress",
                {
                    "job_id": job_id,
                    "phase": phase,
                    "progress": round(progress, 3),
                    "message": message,
                },
            )
        except Exception:
            pass  # Non-critical -- don't let WebSocket errors break the job
