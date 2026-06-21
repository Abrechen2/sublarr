"""Detect null bytes, C0 control chars, and bidi override codepoints."""

from __future__ import annotations

import re

from services.subtitle_health.models import Issue, IssueType, Severity
from services.subtitle_health.text_utils import decode_with_confidence

# C0 controls except tab/newline/carriage-return; bidi overrides (U+202A..202E,
# U+2066..2069); and a BOM/zero-width-no-break-space appearing in the body.
_BAD_RE = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1f]"
    r"|[‪-‮⁦-⁩]"
    r"|﻿"
)


def detect(ctx) -> list[Issue]:
    issues: list[Issue] = []
    for t in ctx.targets:
        if not t.raw:
            continue
        # Strip a leading BOM (legitimate) before scanning the body.
        raw = t.raw[3:] if t.raw.startswith(b"\xef\xbb\xbf") else t.raw
        text, _enc, _conf = decode_with_confidence(raw)
        matches = _BAD_RE.findall(text)
        if not matches:
            continue
        issues.append(
            Issue(
                type=IssueType.UNICODE_CONTROL_CHARS,
                severity=Severity.SUSPICIOUS,
                episode_id=ctx.episode_id,
                target_kind=t.kind,
                target_path=t.path,
                stream_index=t.stream_index,
                lang=t.lang,
                count=len(matches),
                snippets=[
                    f"{len(matches)} control/bidi codepoint(s), first U+{ord(matches[0]):04X}"
                ],
                raw_hash="",
                fixable=False,
                suggested_fix=None,
            )
        )
    return issues
