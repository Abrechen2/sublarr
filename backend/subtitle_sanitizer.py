"""Subtitle content sanitizer — strip malicious content before writing to disk.

Subtitle files from untrusted providers can contain content that exploits parser
bugs in media players (VLC CVE-2019-19721, Kodi, Jellyfin). This module sanitizes
subtitle content before it reaches the media library.

Threats addressed:
- ASS: Lua script extensions, drawing-mode overlays ({\\p1}...{\\p0})
- SRT/VTT: XSS-style HTML injection (<script>, event handlers, data: URIs)
- All: oversized files, binary content disguised as subtitles
"""

import logging
import re

logger = logging.getLogger(__name__)

_MAX_SUBTITLE_BYTES = 5 * 1024 * 1024  # 5 MB per subtitle file

# Drawing-mode blocks: {\p1}...{\p0} — can render full-screen overlays
# Matches any override tag containing \pN (N=1-9) up to the matching \p0 block.
_DRAWING_BLOCK_RE = re.compile(
    r"\{[^}]*\\p[1-9][^}]*\}.*?\{[^}]*\\p0[^}]*\}",
    re.DOTALL | re.IGNORECASE,
)

# HTML tags allowed in SRT/VTT subtitle text
_ALLOWED_HTML_TAGS = frozenset({"i", "b", "u", "font"})
# Attributes allowed per tag (all others stripped)
_ALLOWED_ATTRS: dict[str, frozenset[str]] = {"font": frozenset({"color"})}

# UTF-8 byte-order mark. Preserved across sanitization (BOM normalization is the
# repair pass's job, not the always-on sanitizer).
_UTF8_BOM = b"\xef\xbb\xbf"

# SRT/VTT timecode arrow flanked by two timestamps. BeautifulSoup serialization
# HTML-escapes the '>' in '-->' to '&gt;', producing a malformed timecode that
# players reject. We restore the literal arrow ONLY between two timestamps —
# timecode lines never carry user text, so this never weakens XSS sanitization
# of cue text (where escaping a literal '>' is intentionally kept).
_TS = r"\d{1,2}:\d{2}(?::\d{2})?[.,]\d{3}"
_TIMECODE_ARROW_RE = re.compile(rf"({_TS}[ \t]*)--&gt;([ \t]*{_TS})".encode())


def sanitize_ass_content(content: bytes) -> bytes:
    """Sanitize ASS/SSA subtitle content.

    Uses pysubs2 to parse and re-serialize (strips non-standard Script Info
    sections, Lua extensions, @import directives). Additionally strips dangerous
    drawing-mode tag blocks via regex.

    Args:
        content: Raw ASS/SSA file bytes.

    Returns:
        Sanitized ASS bytes.
    """
    try:
        import pysubs2

        text = content.decode("utf-8", errors="replace")
        subs = pysubs2.SSAFile.from_string(text)
        serialized = subs.to_string("ass")
        # Strip drawing-mode blocks from the re-serialized output
        serialized = _DRAWING_BLOCK_RE.sub("", serialized)
        return serialized.encode("utf-8")
    except Exception as e:
        logger.warning("ASS sanitization failed, returning original: %s", e)
        return content


def sanitize_srt_vtt_content(content: bytes) -> bytes:
    """Sanitize SRT/VTT subtitle content.

    Strips dangerous HTML (script, img, event handlers, javascript:/data: URIs)
    while preserving allowed inline formatting tags (<i>, <b>, <u>, <font color>).

    Args:
        content: Raw SRT/VTT file bytes.

    Returns:
        Sanitized bytes with dangerous HTML removed.
    """
    try:
        from bs4 import BeautifulSoup

        had_bom = content.startswith(_UTF8_BOM)
        text = content.decode("utf-8", errors="replace")
        soup = BeautifulSoup(text, "html.parser")

        # Process all tags — iterate over a frozen copy to avoid mutation issues
        for tag in list(soup.find_all(True)):
            tag_name = getattr(tag, "name", "").lower()

            # Completely remove script/style and their contents
            if tag_name in ("script", "style"):
                tag.decompose()
                continue

            if tag_name in _ALLOWED_HTML_TAGS:
                # Strip disallowed attributes
                allowed = _ALLOWED_ATTRS.get(tag_name, frozenset())
                for attr in list(tag.attrs.keys()):
                    # Remove event handlers and any attr not in the allowlist
                    if attr.lower().startswith("on") or attr not in allowed:
                        del tag[attr]
                # Strip javascript: and data: URIs from surviving attributes
                for attr in list(tag.attrs.keys()):
                    val = tag.get(attr, "")
                    if isinstance(val, str) and val.lower().lstrip().startswith(
                        ("javascript:", "data:")
                    ):
                        del tag[attr]
            else:
                # Not an allowed tag — keep text content, remove the tag wrapper
                tag.unwrap()

        sanitized = str(soup).encode("utf-8")
        # Subtitle Health: convert leaked ASS escape codes to real SRT/VTT breaks
        # so freshly-downloaded/translated sidecars never carry literal \N.
        try:
            from services.subtitle_health.fixers.repair_escapes import repair_bytes

            sanitized = repair_bytes(sanitized, codec="srt")
        except Exception:
            logger.debug("subtitle_health: inline repair skipped", exc_info=True)
        # Restore the timecode arrow that BeautifulSoup HTML-escaped to '--&gt;'.
        # Scoped to timestamp-flanked arrows only — cue-text escaping is kept.
        sanitized = _TIMECODE_ARROW_RE.sub(rb"\1-->\2", sanitized)
        # Preserve a leading BOM: the always-on sanitizer must not normalize it
        # (that is the opt-outable repair pass's responsibility).
        if had_bom and not sanitized.startswith(_UTF8_BOM):
            sanitized = _UTF8_BOM + sanitized
        return sanitized
    except Exception as e:
        logger.warning("SRT/VTT sanitization failed, returning original: %s", e)
        return content


def validate_content_type(content: bytes, fmt) -> bool:
    """Check that content matches the declared subtitle format.

    Args:
        content: Raw file bytes (may include UTF-8 BOM).
        fmt: SubtitleFormat instance (checked via .value attribute).

    Returns:
        True if the content structure matches the expected format, False otherwise.
    """
    stripped = content.lstrip(b"\xef\xbb\xbf")  # strip UTF-8 BOM
    fmt_value = fmt.value if hasattr(fmt, "value") else str(fmt)

    if fmt_value in ("ass", "ssa"):
        return stripped.lstrip().startswith(b"[Script Info]")

    if fmt_value == "srt":
        # First non-empty line must be a sequence number (digit only)
        for line in stripped.decode("utf-8", errors="replace").splitlines():
            line = line.strip()
            if line:
                return line.isdigit()
        return False

    if fmt_value == "vtt":
        return stripped.startswith(b"WEBVTT")

    # For unknown formats: reject binary content (high non-text byte ratio)
    sample = stripped[:1000]
    if sample:
        non_text = sum(1 for b in sample if b < 0x09 or (0x0E <= b <= 0x1F) or b == 0x7F)
        if non_text / len(sample) > 0.1:
            return False

    return True


def sanitize_subtitle(content: bytes, fmt) -> bytes:
    """Main sanitization gate — validates and sanitizes subtitle content.

    Args:
        content: Raw subtitle file bytes.
        fmt: SubtitleFormat instance indicating the file type.

    Returns:
        Sanitized subtitle bytes.

    Raises:
        ValueError: If content exceeds size limit or fails content-type check.
    """
    if len(content) > _MAX_SUBTITLE_BYTES:
        raise ValueError(
            f"Subtitle too large: {len(content) // 1024} KB > "
            f"{_MAX_SUBTITLE_BYTES // 1024} KB limit"
        )

    fmt_value = fmt.value if hasattr(fmt, "value") else str(fmt)

    if fmt_value != "unknown" and not validate_content_type(content, fmt):
        raise ValueError(f"Content does not match expected format {fmt_value!r}")

    if fmt_value in ("ass", "ssa"):
        return sanitize_ass_content(content)

    if fmt_value in ("srt", "vtt"):
        return sanitize_srt_vtt_content(content)

    # Unknown or other formats: pass through unchanged
    return content


def sanitize_subtitle_file(path: str) -> bool:
    """Sanitize an on-disk subtitle file in place (format inferred from suffix).

    Used to give locally-produced output (e.g. LLM translation results) the
    same content sanitization the provider-download path applies — prompt
    injection in model output must not be able to smuggle drawing-mode/Lua
    (ASS) or HTML/script (SRT/VTT) past the renderer. Best-effort: a read or
    parse failure logs and leaves the file untouched rather than raising into
    the translation flow.

    Returns:
        True if the file was rewritten with sanitized content, else False.
    """
    import os

    ext = os.path.splitext(path)[1].lower().lstrip(".")
    if ext in ("ass", "ssa"):
        sanitizer = sanitize_ass_content
    elif ext in ("srt", "vtt"):
        sanitizer = sanitize_srt_vtt_content
    else:
        return False

    try:
        with open(path, "rb") as fh:
            original = fh.read()
    except OSError as exc:
        logger.warning("Could not read %s for sanitization: %s", path, exc)
        return False

    cleaned = sanitizer(original)
    if cleaned == original:
        return False

    try:
        from utils.atomic_write import atomic_write_bytes

        atomic_write_bytes(path, cleaned)
    except OSError as exc:
        logger.warning("Could not write sanitized %s: %s", path, exc)
        return False
    return True
