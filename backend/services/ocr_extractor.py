"""OCR service for extracting text from embedded image subtitles (DVD, Blu-ray).

Uses Tesseract OCR to extract text from video frames containing subtitle images.
Inspired by SubtitleEdit's OCR functionality.
"""

import contextlib
import logging
import os
import subprocess
import tempfile

logger = logging.getLogger(__name__)

# Try to import pytesseract, but make it optional
try:
    import pytesseract
    from PIL import Image

    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False
    logger.warning("pytesseract/PIL not available. OCR will be disabled.")

# Export TESSERACT_AVAILABLE for use in routes
__all__ = [
    "batch_ocr_track",
    "extract_frame",
    "extract_frames_sequence",
    "ocr_image",
    "ocr_subtitle_stream",
    "preview_frame",
    "TESSERACT_AVAILABLE",
]


def extract_frame(
    video_path: str,
    timestamp: float,
    output_path: str | None = None,
) -> str:
    """Extract a single frame from video at specific timestamp using FFmpeg.

    Args:
        video_path: Path to video file
        timestamp: Timestamp in seconds
        output_path: Optional output path. If None, creates temporary file.

    Returns:
        Path to extracted frame image (PNG format)

    Raises:
        RuntimeError: If FFmpeg fails or file not found
    """
    if not os.path.exists(video_path):
        raise RuntimeError(f"Video file not found: {video_path}")

    if output_path is None:
        # Create temporary PNG file
        temp_fd, output_path = tempfile.mkstemp(suffix=".png")
        os.close(temp_fd)

    # Build FFmpeg command
    cmd = [
        "ffmpeg",
        "-y",  # Overwrite output file
        "-ss",
        str(timestamp),
        "-i",
        video_path,
        "-vframes",
        "1",  # Extract only one frame
        "-vf",
        "scale=1920:-1",  # Scale to reasonable size for OCR
        output_path,
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg frame extraction failed: {result.stderr}")
        if not os.path.exists(output_path):
            raise RuntimeError(f"FFmpeg did not produce output file: {output_path}")
        return output_path
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"FFmpeg frame extraction timed out: {video_path}")
    except FileNotFoundError:
        raise RuntimeError("ffmpeg not found. Install ffmpeg to enable frame extraction.")


def extract_frames_sequence(
    video_path: str,
    start_time: float,
    end_time: float,
    interval: float = 1.0,
    output_dir: str | None = None,
) -> list[str]:
    """Extract multiple frames from video at regular intervals.

    Args:
        video_path: Path to video file
        start_time: Start timestamp in seconds
        end_time: End timestamp in seconds
        interval: Interval between frames in seconds
        output_dir: Optional output directory. If None, creates temporary directory.

    Returns:
        List of paths to extracted frame images
    """
    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="sublarr_ocr_")

    os.makedirs(output_dir, exist_ok=True)
    frame_paths = []

    current_time = start_time
    frame_index = 0

    while current_time <= end_time:
        frame_path = os.path.join(output_dir, f"frame_{frame_index:04d}.png")
        try:
            extract_frame(video_path, current_time, frame_path)
            frame_paths.append(frame_path)
        except Exception as e:
            logger.warning("Failed to extract frame at %s: %s", current_time, e)

        current_time += interval
        frame_index += 1

    return frame_paths


def ocr_image(
    image_path: str,
    language: str = "eng",
    psm: int = 6,
) -> str:
    """Extract text from image using Tesseract OCR.

    Args:
        image_path: Path to image file
        language: Tesseract language code (e.g., "eng", "deu", "eng+deu")
        psm: Page segmentation mode (6 = uniform block of text)

    Returns:
        Extracted text

    Raises:
        RuntimeError: If Tesseract fails or not available
    """
    if not TESSERACT_AVAILABLE:
        raise RuntimeError("pytesseract not available. Install it to enable OCR.")

    if not os.path.exists(image_path):
        raise RuntimeError(f"Image file not found: {image_path}")

    try:
        # Load image
        image = Image.open(image_path)

        # Preprocess image for better OCR (optional)
        # Convert to grayscale if needed
        if image.mode != "L":
            image = image.convert("L")

        # Run OCR
        text = pytesseract.image_to_string(
            image,
            lang=language,
            config=f"--psm {psm}",
        )

        return text.strip()
    except Exception as e:
        raise RuntimeError(f"OCR failed: {e}")


def ocr_subtitle_stream(
    video_path: str,
    stream_index: int,
    language: str = "eng",
    start_time: float | None = None,
    end_time: float | None = None,
    interval: float = 1.0,
) -> dict:
    """Extract text from embedded image subtitle stream using OCR.

    This is the main entry point for OCR functionality.

    Args:
        video_path: Path to video file
        stream_index: Subtitle stream index (0-based)
        language: Tesseract language code
        start_time: Optional start timestamp (default: 0)
        end_time: Optional end timestamp (default: video duration)
        interval: Frame extraction interval in seconds

    Returns:
        Dict with "text" (extracted text), "frames" (number of frames processed),
        and "quality" (estimated quality score 0-100)
    """
    if not TESSERACT_AVAILABLE:
        raise RuntimeError("pytesseract not available. Install it to enable OCR.")

    # Get video duration
    from services.audio_visualizer import get_audio_duration

    try:
        duration = get_audio_duration(video_path)
    except Exception:
        # Fallback: use ffprobe
        from ass_utils import run_ffprobe

        probe_data = run_ffprobe(video_path)
        duration = float(probe_data.get("format", {}).get("duration", 0))

    if duration <= 0:
        raise RuntimeError("Invalid video duration")

    start = start_time or 0.0
    end = end_time or duration

    # Extract frames
    frame_paths = extract_frames_sequence(video_path, start, end, interval)

    if not frame_paths:
        raise RuntimeError("No frames extracted")

    # OCR each frame
    extracted_texts = []
    successful_frames = 0

    for frame_path in frame_paths:
        try:
            text = ocr_image(frame_path, language)
            if text.strip():
                extracted_texts.append(text)
                successful_frames += 1
        except Exception as e:
            logger.warning("OCR failed for frame %s: %s", frame_path, e)

    # Clean up temporary frames
    for frame_path in frame_paths:
        with contextlib.suppress(OSError):
            os.unlink(frame_path)

    # Calculate quality score
    quality = int((successful_frames / len(frame_paths)) * 100) if frame_paths else 0

    # Combine extracted texts
    combined_text = "\n".join(extracted_texts)

    return {
        "text": combined_text,
        "frames": len(frame_paths),
        "successful_frames": successful_frames,
        "quality": quality,
    }


def batch_ocr_track(
    video_path: str,
    stream_index: int,
    language: str = "eng",
) -> list[dict]:
    """Extract and OCR an entire image subtitle track from an MKV in one pass.

    Args:
        video_path: Path to video file
        stream_index: Subtitle stream index (from ffprobe)
        language: Tesseract language code (eng, deu, jpn)

    Returns:
        List of dicts: [{"text": str}, ...] — deduplicated consecutive lines.

    Raises:
        RuntimeError: If pytesseract is unavailable, ffmpeg fails, or no frames found.
    """
    if not TESSERACT_AVAILABLE:
        raise RuntimeError("pytesseract is not available")

    import glob as _glob
    from concurrent.futures import ThreadPoolExecutor as TPE

    with tempfile.TemporaryDirectory() as tmp_dir:
        out_pattern = os.path.join(tmp_dir, "frame%08d.png")
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            video_path,
            "-map",
            f"0:{stream_index}",
            "-vsync",
            "vfr",
            out_pattern,
        ]
        r = subprocess.run(cmd, capture_output=True, timeout=300)
        if r.returncode != 0:
            raise RuntimeError(
                f"ffmpeg subtitle extraction failed: {r.stderr.decode(errors='replace')[:500]}"
            )

        frames = sorted(_glob.glob(os.path.join(tmp_dir, "frame*.png")))
        if not frames:
            return []

        def _ocr_frame(frame_path: str) -> str:
            img = Image.open(frame_path).convert("L")  # grayscale for better OCR
            return pytesseract.image_to_string(img, lang=language).strip()  # type: ignore[union-attr]

        with TPE(max_workers=4) as pool:
            texts = list(pool.map(_ocr_frame, frames))

    # Deduplicate consecutive identical lines
    cues: list[dict] = []
    prev: str | None = None
    for text in texts:
        if text and text != prev:
            cues.append({"text": text})
        prev = text

    logger.info(
        "batch_ocr_track: extracted %d cues from stream %d of %s",
        len(cues),
        stream_index,
        video_path,
    )
    return cues


def preview_frame(
    video_path: str,
    timestamp: float,
    stream_index: int | None = None,
) -> dict:
    """Preview a single frame for OCR (returns frame path and estimated text).

    Args:
        video_path: Path to video file
        timestamp: Timestamp in seconds
        stream_index: Optional subtitle stream index

    Returns:
        Dict with "frame_path" and "preview_text"
    """
    frame_path = extract_frame(video_path, timestamp)

    preview_text = ""
    if TESSERACT_AVAILABLE:
        with contextlib.suppress(Exception):
            preview_text = ocr_image(frame_path, language="eng")

    return {
        "frame_path": frame_path,
        "preview_text": preview_text,
    }
