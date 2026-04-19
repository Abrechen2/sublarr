"""Text transformation ops: strip_html, remove_bom, convert_encoding (Plan B6)."""

from __future__ import annotations

import re
import time
from pathlib import Path

from post_processing.base_op import BaseOp, OpResult, register_op

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_BOM = b"\xef\xbb\xbf"


def _elapsed_ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)


@register_op
class StripHtmlOp(BaseOp):
    op_id = "strip_html"
    label = "Strip HTML tags"
    description = (
        "Remove <i>, <b>, <font>, <br> and other HTML tags from subtitle lines."
    )

    def execute(self, context: dict) -> OpResult:
        start = time.monotonic()
        try:
            path = Path(context["subtitle_path"])
            text = path.read_text(encoding="utf-8", errors="replace")
            cleaned = _HTML_TAG_RE.sub("", text)
            if cleaned != text:
                path.write_text(cleaned, encoding="utf-8")
                msg = "html stripped"
            else:
                msg = "no html found"
            return OpResult(self.op_id, True, _elapsed_ms(start), msg)
        except Exception as exc:
            return OpResult(self.op_id, False, _elapsed_ms(start), str(exc))


@register_op
class RemoveBomOp(BaseOp):
    op_id = "remove_bom"
    label = "Remove BOM"
    description = "Strip UTF-8 BOM (0xEF 0xBB 0xBF) from the start of the subtitle file."

    def execute(self, context: dict) -> OpResult:
        start = time.monotonic()
        try:
            path = Path(context["subtitle_path"])
            data = path.read_bytes()
            if data.startswith(_BOM):
                path.write_bytes(data[len(_BOM):])
                return OpResult(self.op_id, True, _elapsed_ms(start), "bom stripped")
            return OpResult(self.op_id, True, _elapsed_ms(start), "no bom")
        except Exception as exc:
            return OpResult(self.op_id, False, _elapsed_ms(start), str(exc))


@register_op
class ConvertEncodingOp(BaseOp):
    op_id = "convert_encoding"
    label = "Convert encoding"
    description = (
        "Re-encode the subtitle to UTF-8 (auto-detects source encoding via chardet)."
    )

    def execute(self, context: dict) -> OpResult:
        start = time.monotonic()
        try:
            path = Path(context["subtitle_path"])
            raw = path.read_bytes()
            # Try UTF-8 first — skip the re-encode if already UTF-8.
            try:
                raw.decode("utf-8")
                return OpResult(self.op_id, True, _elapsed_ms(start), "already utf-8")
            except UnicodeDecodeError:
                pass
            try:
                import chardet

                detected = chardet.detect(raw) or {}
                enc = detected.get("encoding") or "windows-1252"
            except ImportError:
                enc = "windows-1252"
            text = raw.decode(enc, errors="replace")
            path.write_text(text, encoding="utf-8")
            return OpResult(
                self.op_id, True, _elapsed_ms(start), f"converted from {enc}"
            )
        except Exception as exc:
            return OpResult(self.op_id, False, _elapsed_ms(start), str(exc))
