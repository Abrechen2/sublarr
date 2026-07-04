"""Combined / bilingual subtitle composition engine (V1.6 Feature #1).

Pure — no Flask/DB. Composes two (or three) per-language subtitle files into one
combined file:

* **ASS output** overlays every input's events into one script, positioning each
  language via an injected ``{\\anN}`` tag (primary bottom, secondary top by
  default; configurable per profile). Each input's styles are merged under a
  prefixed namespace so a shared "Default" style name never clobbers the other
  language's formatting.
* **SRT output** stacks the aligned cues of every input under the primary
  language's timestamps, one language per line (top-positioned language first).

Both paths run every input through ``subtitle_sanitizer`` first (ASS Lua/drawing
strip, SRT/VTT HTML sanitize) and reject bitmap-codec sources — the same rules
the embedded extractor and manual-upload paths enforce.

Alignment for SRT stacking is decided by :func:`detect_alignment`: equal cue
counts → index-parallel ("sibling"); a constant index shift that lines the
timings up → "offset"; otherwise a time-overlap join ("overlap").
"""

from __future__ import annotations

import re

import pysubs2

# ── format tables ───────────────────────────────────────────────────────────

_TEXT_FORMATS: frozenset[str] = frozenset({"ass", "ssa", "srt", "vtt"})
# Codecs we can never combine as text (same rule as the embedded extractor).
_BITMAP_FORMATS: frozenset[str] = frozenset(
    {"pgs", "hdmv_pgs", "hdmv_pgs_subtitle", "sup", "vobsub", "dvd_subtitle", "dvdsub", "xsub"}
)
_OUTPUT_FORMATS: frozenset[str] = frozenset({"ass", "srt"})

# ASS \an alignment codes for vertical position.
_AN_CODES: dict[str, int] = {"bottom": 2, "middle": 5, "top": 8}
_DEFAULT_POSITION = {"primary": "bottom", "secondary": "top"}

# Alignment-detector tuning.
_OFFSET_TOL_MS = 700  # mean per-pair start diff still considered "offset"
_MAX_OFFSET_SEARCH = 50

# Strip conflicting position tags out of an event before injecting our own \an.
_POSITION_TAG_RE = re.compile(r"\\(?:an\d|a\d+|pos\([^)]*\)|move\([^)]*\))")


class CombineError(Exception):
    """Raised when subtitles cannot be combined. Carries an HTTP status."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


# ── source selection ────────────────────────────────────────────────────────

# Lower rank wins. A plain sidecar (no modifier) is preferred over HI, HI over
# forced — matches the "plain > hi > forced" source priority in the spec.
_MODIFIER_RANK = {None: 0, "": 0, "hi": 1, "sdh": 1, "cc": 1, "forced": 2}


def pick_best_sidecar(candidates: list[dict]) -> dict | None:
    """Pick the best sidecar for one language by source priority.

    ``candidates`` are sidecar dicts carrying a ``modifier`` key
    (``None`` = plain, ``"hi"``, ``"forced"``, …). Returns the highest-priority
    one, or ``None`` if the list is empty.
    """
    if not candidates:
        return None
    return min(candidates, key=lambda c: _MODIFIER_RANK.get(c.get("modifier"), 3))


# ── alignment detection ─────────────────────────────────────────────────────


def _mean_abs_diff(a: list[int], pairs: list[tuple[int, int]], b: list[int]) -> float:
    return sum(abs(a[i] - b[j]) for i, j in pairs) / len(pairs)


def detect_alignment(primary_starts: list[int], secondary_starts: list[int]) -> tuple[str, int]:
    """Classify how two cue timelines align.

    Returns ``(mode, offset)`` where *mode* is ``"sibling"`` (pair by index),
    ``"offset"`` (pair primary[i] with secondary[i + offset]), or ``"overlap"``
    (pair by time overlap). *offset* is only meaningful for ``"offset"``.
    """
    n, m = len(primary_starts), len(secondary_starts)
    if n == 0 or m == 0:
        return ("overlap", 0)
    if n == m:
        return ("sibling", 0)

    best: tuple[float, int, int] | None = None  # (cost, offset, coverage)
    min_pairs = max(3, min(n, m) // 2)
    limit = min(_MAX_OFFSET_SEARCH, max(n, m))
    for off in range(-limit, limit + 1):
        pairs = [(i, i + off) for i in range(n) if 0 <= i + off < m]
        if len(pairs) < min_pairs:
            continue
        cost = _mean_abs_diff(primary_starts, pairs, secondary_starts)
        if best is None or cost < best[0] or (cost == best[0] and len(pairs) > best[2]):
            best = (cost, off, len(pairs))

    if best is not None and best[0] <= _OFFSET_TOL_MS:
        return ("offset", best[1])
    return ("overlap", 0)


# ── loading / sanitizing ────────────────────────────────────────────────────


def _load_and_sanitize(path: str, fmt: str) -> pysubs2.SSAFile:
    fmt = (fmt or "").lower()
    if fmt in _BITMAP_FORMATS:
        raise CombineError(415, f"Cannot combine bitmap subtitle format '{fmt}'")
    if fmt not in _TEXT_FORMATS:
        raise CombineError(415, f"Unsupported subtitle format '{fmt}'")

    from providers.base import SubtitleFormat
    from subtitle_sanitizer import sanitize_subtitle

    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError as exc:
        raise CombineError(404, f"Subtitle file not readable: {path}") from exc

    try:
        sanitized = sanitize_subtitle(raw, SubtitleFormat(fmt))
    except ValueError as exc:
        raise CombineError(422, f"Subtitle failed the security check: {exc}") from exc

    text = sanitized.decode("utf-8", errors="replace")
    try:
        return pysubs2.SSAFile.from_string(text)
    except Exception as exc:  # pysubs2 raises various parse errors
        raise CombineError(422, f"Could not parse subtitle '{path}': {exc}") from exc


def _an_for_index(idx: int, position: dict) -> int:
    if idx == 0:
        return _AN_CODES.get(position.get("primary", "bottom"), 2)
    if idx == 1:
        return _AN_CODES.get(position.get("secondary", "top"), 8)
    return _AN_CODES["middle"]  # 3rd+ language stacks in the middle


# ── ASS overlay ─────────────────────────────────────────────────────────────


def _merge_styles(dest: pysubs2.SSAFile, src: pysubs2.SSAFile, prefix: str) -> dict[str, str]:
    """Copy src styles into dest under prefixed names. Returns {old: new}."""
    mapping: dict[str, str] = {}
    styles = src.styles or {"Default": pysubs2.SSAStyle()}
    for name, style in styles.items():
        new_name = f"{prefix}{name}"
        dest.styles[new_name] = style.copy()
        mapping[name] = new_name
    return mapping


def _compose_ass(subs: list[pysubs2.SSAFile], an_codes: list[int]) -> pysubs2.SSAFile:
    result = pysubs2.SSAFile()
    result.info.update(subs[0].info)

    for idx, src in enumerate(subs):
        style_map = _merge_styles(result, src, prefix=f"L{idx}_")
        fallback_style = next(iter(style_map.values()))
        an = an_codes[idx]
        for ev in src.events:
            if ev.is_comment:
                continue
            new = ev.copy()
            new.style = style_map.get(ev.style, fallback_style)
            new.text = f"{{\\an{an}}}" + _POSITION_TAG_RE.sub("", ev.text)
            result.events.append(new)

    result.sort()
    return result


# ── SRT stacking ────────────────────────────────────────────────────────────


def _map_secondary_to_primary(
    primary: list[pysubs2.SSAEvent], secondary: list[pysubs2.SSAEvent]
) -> dict[int, str]:
    """Return {primary_index: secondary_plaintext} for the aligned cues."""
    mode, off = detect_alignment([e.start for e in primary], [e.start for e in secondary])
    out: dict[int, str] = {}
    if mode == "sibling":
        for i in range(min(len(primary), len(secondary))):
            out[i] = secondary[i].plaintext
    elif mode == "offset":
        for i in range(len(primary)):
            j = i + off
            if 0 <= j < len(secondary):
                out[i] = secondary[j].plaintext
    else:  # overlap
        for i, pe in enumerate(primary):
            texts = [se.plaintext for se in secondary if se.start < pe.end and se.end > pe.start]
            if texts:
                out[i] = "\n".join(texts)
    return out


def _compose_srt(subs: list[pysubs2.SSAFile], an_codes: list[int]) -> pysubs2.SSAFile:
    primary = subs[0].events
    maps = [_map_secondary_to_primary(primary, s.events) for s in subs[1:]]

    result = pysubs2.SSAFile()
    for i, pe in enumerate(primary):
        # (an_code, text) per language present at this cue; higher an = higher
        # on screen, so a "top" language renders before a "bottom" one.
        lines: list[tuple[int, str]] = [(an_codes[0], pe.plaintext)]
        for k, mapping in enumerate(maps):
            if i in mapping:
                lines.append((an_codes[k + 1], mapping[i]))
        lines.sort(key=lambda t: -t[0])

        ev = pysubs2.SSAEvent(start=pe.start, end=pe.end)
        ev.plaintext = "\n".join(text for _, text in lines)
        result.events.append(ev)
    return result


# ── public entry point ──────────────────────────────────────────────────────


def combine_subtitles(
    inputs: list[dict],
    output_format: str,
    position: dict | None = None,
) -> bytes:
    """Compose ``inputs`` (ordered, primary first) into one combined file.

    Each input is ``{"language", "path", "format"}``. Returns the combined
    subtitle bytes in ``output_format`` (``"ass"`` or ``"srt"``). Raises
    :class:`CombineError` on bad input, unsupported/bitmap source, or a source
    that fails the security check.
    """
    if len(inputs) < 2:
        raise CombineError(400, "Combining needs at least two subtitle inputs")
    output_format = (output_format or "").lower()
    if output_format not in _OUTPUT_FORMATS:
        raise CombineError(400, f"Unsupported combine output format '{output_format}'")

    position = position or dict(_DEFAULT_POSITION)
    an_codes = [_an_for_index(i, position) for i in range(len(inputs))]
    subs = [_load_and_sanitize(inp["path"], inp.get("format", "")) for inp in inputs]

    if output_format == "ass":
        result = _compose_ass(subs, an_codes)
    else:
        result = _compose_srt(subs, an_codes)

    return result.to_string(output_format).encode("utf-8")
