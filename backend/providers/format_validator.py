"""Subtitle format detection and content validation utilities."""

from providers.base import SubtitleFormat

_BINARY_SIGNATURES = [
    b"MZ",  # Windows PE executable
    b"\x7fELF",  # Linux ELF executable
    b"\xca\xfe\xba\xbe",  # Java class file
    b"\xfe\xed\xfa\xce",  # macOS Mach-O
    b"\xfe\xed\xfa\xcf",  # macOS Mach-O 64-bit
]


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


def _validate_subtitle_content(content: bytes, fmt: str) -> tuple[bool, str | None]:
    """Validate downloaded subtitle content matches the declared format (P4).

    Rejects executable/binary signatures and content that is clearly not a
    text-based subtitle file.

    Returns:
        (True, None) if content looks like a valid subtitle.
        (False, reason) if content appears to be malicious or wrong format.
    """
    if not content:
        return False, "Empty content"

    # Check for executable/binary signatures
    for sig in _BINARY_SIGNATURES:
        if content.startswith(sig):
            return False, f"Content has binary executable signature (0x{sig.hex()[:8]})"

    # Check that content is mostly text (subtitle files are text-based).
    # Reject if more than 30% of sampled bytes are non-printable control characters
    # (allowing for UTF-8 multi-byte sequences which may have high bytes, but not
    # random binary data which distributes evenly across all 256 byte values).
    sample = content[:1024]
    null_bytes = sample.count(b"\x00")
    if null_bytes > len(sample) * 0.05:
        return False, "Content appears to be binary data (too many null bytes)"
    # Count bytes that are neither printable ASCII nor valid UTF-8 continuation bytes
    # (i.e. bytes < 0x09 or in range 0x0E–0x1F, excluding tab/LF/CR/FF)
    control_chars = sum(1 for b in sample if (b < 0x09) or (0x0E <= b <= 0x1F))
    if control_chars > len(sample) * 0.10:
        return False, "Content appears to be binary data (too many control characters)"

    return True, None
