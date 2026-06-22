"""Detect invalid UTF-8 and mojibake (cp1252-read-as-utf8 artifacts)."""

from __future__ import annotations

import re

from services.subtitle_health.models import Issue, IssueType, Severity

# Classic mojibake bigrams: a UTF-8 lead byte (Ã, Â) followed by a stray latin1
# continuation, produced when cp1252/latin-1 text is decoded as utf-8 and
# re-encoded. We score on density.
_MOJIBAKE_RE = re.compile(r"[ÃÂ][\x80-\xbf\xa0-\xff©®¤¶ ]")
_MOJIBAKE_RATIO = 0.002  # markers per character


def detect(ctx) -> list[Issue]:
    issues: list[Issue] = []
    for t in ctx.targets:
        if not t.raw:
            continue
        raw = t.raw[3:] if t.raw.startswith(b"\xef\xbb\xbf") else t.raw

        severity = None
        detail = ""
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            severity = Severity.CONFIRMED
            detail = f"invalid UTF-8 at byte {exc.start}"
            text = raw.decode("utf-8", errors="replace")
        if severity is None:
            markers = _MOJIBAKE_RE.findall(text)
            if markers and len(markers) / max(1, len(text)) >= _MOJIBAKE_RATIO:
                severity = Severity.SUSPICIOUS
                detail = f"{len(markers)} mojibake markers (e.g. {markers[0]!r})"
        if severity is None:
            continue

        issues.append(
            Issue(
                type=IssueType.ENCODING_MOJIBAKE,
                severity=severity,
                episode_id=ctx.episode_id,
                target_kind=t.kind,
                target_path=t.path,
                stream_index=t.stream_index,
                lang=t.lang,
                count=1,
                snippets=[detail],
                raw_hash="",
                fixable=True,
                suggested_fix="reencode",
            )
        )
    return issues
