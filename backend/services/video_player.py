"""Video player service for browser-based video streaming and subtitle preview.

Uses FFmpeg to transcode videos to HLS format for browser compatibility.
Provides screenshot generation and subtitle embedding capabilities.
"""

import os
import subprocess
import logging
import tempfile
from typing import Optional, Dict

logger = logging.getLogger(__name__)


def generate_hls_playlist(
    video_path: str,
    output_dir: str,
    segment_duration: int = 10,
    quality: str = "medium",
) -> Dict:
    """Generate HLS playlist and segments from video file.

    Args:
        video_path: Path to video file
        output_dir: Directory to store HLS segments and playlist
        segment_duration: Duration of each segment in seconds
        quality: Quality preset (low, medium, high)

    Returns:
        Dict with playlist_path and segment_count

    Raises:
        RuntimeError: If FFmpeg fails
    """
    if not os.path.exists(video_path):
        raise RuntimeError(f"Video file not found: {video_path}")

    os.makedirs(output_dir, exist_ok=True)

    # Quality presets
    quality_settings = {
        "low": {"scale": "1280:720", "bitrate": "1000k"},
        "medium": {"scale": "1920:1080", "bitrate": "2500k"},
        "high": {"scale": "-2:1080", "bitrate": "5000k"},
    }

    settings = quality_settings.get(quality, quality_settings["medium"])

    playlist_path = os.path.join(output_dir, "playlist.m3u8")
    segment_pattern = os.path.join(output_dir, "segment_%03d.ts")

    # FFmpeg command for HLS generation
    cmd = [
        "ffmpeg",
        "-y",
        "-i", video_path,
        "-c:v", "libx264",
        "-c:a", "aac",
        "-b:v", settings["bitrate"],
        "-vf", f"scale={settings['scale']}",
        "-hls_time", str(segment_duration),
        "-hls_playlist_type", "vod",
        "-hls_segment_filename", segment_pattern,
        "-start_number", "0",
        playlist_path,
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,  # 10 minutes max
        )
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg HLS generation failed: {result.stderr}")

        # Count segments
        segment_count = len([f for f in os.listdir(output_dir) if f.endswith(".ts")])

        return {
            "playlist_path": playlist_path,
            "segment_count": segment_count,
            "output_dir": output_dir,
        }
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"FFmpeg HLS generation timed out: {video_path}")
    except FileNotFoundError:
        raise RuntimeError("ffmpeg not found. Install ffmpeg to enable video streaming.")


def generate_screenshot(
    video_path: str,
    timestamp: float,
    output_path: Optional[str] = None,
    width: int = 1920,
) -> str:
    """Generate screenshot from video at specific timestamp.

    Args:
        video_path: Path to video file
        timestamp: Timestamp in seconds
        output_path: Optional output path. If None, creates temporary file.
        width: Screenshot width (height scales proportionally)

    Returns:
        Path to screenshot image

    Raises:
        RuntimeError: If FFmpeg fails
    """
    if not os.path.exists(video_path):
        raise RuntimeError(f"Video file not found: {video_path}")

    if output_path is None:
        temp_fd, output_path = tempfile.mkstemp(suffix=".jpg")
        os.close(temp_fd)

    cmd = [
        "ffmpeg",
        "-y",
        "-ss", str(timestamp),
        "-i", video_path,
        "-vframes", "1",
        "-vf", f"scale={width}:-1",
        "-q:v", "2",  # High quality
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
            raise RuntimeError(f"FFmpeg screenshot failed: {result.stderr}")
        if not os.path.exists(output_path):
            raise RuntimeError(f"FFmpeg did not produce screenshot: {output_path}")
        return output_path
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"FFmpeg screenshot timed out: {video_path}")
    except FileNotFoundError:
        raise RuntimeError("ffmpeg not found. Install ffmpeg to enable screenshots.")


def convert_subtitle_to_webvtt(
    subtitle_path: str,
    output_path: Optional[str] = None,
) -> str:
    """Convert subtitle file (ASS/SRT) to WebVTT format for browser playback.

    Args:
        subtitle_path: Path to subtitle file
        output_path: Optional output path. If None, creates temporary file.

    Returns:
        Path to WebVTT file

    Raises:
        RuntimeError: If conversion fails
    """
    if not os.path.exists(subtitle_path):
        raise RuntimeError(f"Subtitle file not found: {subtitle_path}")

    if output_path is None:
        temp_fd, output_path = tempfile.mkstemp(suffix=".vtt")
        os.close(temp_fd)

    # Use FFmpeg to convert subtitle to WebVTT
    cmd = [
        "ffmpeg",
        "-y",
        "-i", subtitle_path,
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
            raise RuntimeError(f"FFmpeg subtitle conversion failed: {result.stderr}")
        if not os.path.exists(output_path):
            raise RuntimeError(f"FFmpeg did not produce WebVTT file: {output_path}")
        return output_path
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"FFmpeg subtitle conversion timed out: {subtitle_path}")
    except FileNotFoundError:
        raise RuntimeError("ffmpeg not found. Install ffmpeg to enable subtitle conversion.")


def embed_subtitle_in_video(
    video_path: str,
    subtitle_path: str,
    output_path: str,
    language: str = "eng",
) -> str:
    """Embed subtitle track into video file.

    Args:
        video_path: Path to video file
        subtitle_path: Path to subtitle file
        output_path: Output video path
        language: Subtitle language code

    Returns:
        Path to output video

    Raises:
        RuntimeError: If embedding fails
    """
    if not os.path.exists(video_path):
        raise RuntimeError(f"Video file not found: {video_path}")
    if not os.path.exists(subtitle_path):
        raise RuntimeError(f"Subtitle file not found: {subtitle_path}")

    # Determine subtitle format
    ext = os.path.splitext(subtitle_path)[1].lower()
    if ext == ".ass":
        codec = "ass"
    elif ext == ".srt":
        codec = "subrip"
    else:
        raise RuntimeError(f"Unsupported subtitle format: {ext}")

    cmd = [
        "ffmpeg",
        "-y",
        "-i", video_path,
        "-i", subtitle_path,
        "-c:v", "copy",  # Copy video stream
        "-c:a", "copy",  # Copy audio stream
        "-c:s", codec,   # Subtitle codec
        "-map", "0:v",
        "-map", "0:a",
        "-map", "1:s",
        "-metadata:s:s:0", f"language={language}",
        output_path,
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg subtitle embedding failed: {result.stderr}")
        if not os.path.exists(output_path):
            raise RuntimeError(f"FFmpeg did not produce output video: {output_path}")
        return output_path
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"FFmpeg subtitle embedding timed out: {video_path}")
    except FileNotFoundError:
        raise RuntimeError("ffmpeg not found. Install ffmpeg to enable subtitle embedding.")
