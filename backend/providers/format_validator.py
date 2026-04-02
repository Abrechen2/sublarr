"""Subtitle format detection utilities."""

from providers.base import SubtitleFormat


def detect_format_from_content(content: bytes) -> SubtitleFormat:
    """Detect subtitle format by inspecting the first bytes of file content.

    Used when a provider doesn't include format metadata (e.g. OpenSubtitles
    returns filenames without extensions for some results).
    """
    if not content:
        return SubtitleFormat.SRT

    # Strip UTF-8 BOM if present
    text_start = content[:512].lstrip(b"\xef\xbb\xbf")
    try:
        preview = text_start.decode("utf-8", errors="replace").strip()
    except (UnicodeDecodeError, ValueError):
        return SubtitleFormat.SRT

    # ASS/SSA files always begin with [Script Info]
    if preview.startswith("[Script Info]") or preview.lower().startswith("[v4"):
        return SubtitleFormat.ASS

    return SubtitleFormat.SRT
