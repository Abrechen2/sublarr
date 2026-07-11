"""The exact transform a downloaded subtitle goes through before it hits disk.

``save_subtitle()`` never writes the provider's bytes as they arrive: it sanitises
them, runs the B5 repair pass over them, writes *that*, and records the SHA-256 of
*that*. So the "pristine" hash in ``subtitle_hashes`` is the hash of the
**normalised** content, not of the raw download.

That matters because repair re-downloads the raw bytes and has to prove they are
the original by hashing them. Comparing raw bytes against a normalised hash fails
every time — which is exactly what happened on the first production dry run: all
ten files came back "provider_changed", the gate correctly refusing to overwrite
something it could not prove.

Both the download path and the repair path call this one function, so they cannot
drift apart again.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def normalise_downloaded_content(content: bytes, fmt) -> bytes:
    """Return ``content`` as ``save_subtitle`` would write (and hash) it.

    ``fmt`` accepts a ``SubtitleFormat`` or a plain string ("srt", "ass", ...).
    Mirrors the download path's error handling: a failing step is logged and
    skipped, never fatal — a subtitle that cannot be tidied is still a subtitle.
    """
    try:
        from subtitle_sanitizer import sanitize_subtitle

        content = sanitize_subtitle(content, fmt)
    except ValueError as exc:
        raise RuntimeError(f"Subtitle failed security check: {exc}") from exc
    except Exception as exc:  # noqa: BLE001 — mirrors save_subtitle
        logger.warning("Subtitle sanitization failed (skipping): %s", exc)

    try:
        from config import get_settings

        if getattr(get_settings(), "enable_subtitle_repair", True):
            from subtitle_repair import repair_bytes

            fmt_str = getattr(fmt, "value", None) or fmt or "srt"
            content = repair_bytes(content, fmt=str(fmt_str))
    except Exception as exc:  # noqa: BLE001 — mirrors save_subtitle
        logger.warning("subtitle_repair skipped during normalisation: %s", exc)

    return content
