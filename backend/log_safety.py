"""Log-injection guard: escape line breaks in the values interpolated into log lines.

The text log is line-oriented: the Logs page, the support bundle and
``parse_log_line`` treat every line as one record. A request value logged as
``logger.info("Translating %s", file_path)`` that carries a newline would
start a forged record of its own (``...\\n2026-10-25 12:00:00 [ERROR] ...``).

``LineBreakEscapeFilter`` sits on every root handler (see
``app_logging._setup_logging``) and rewrites the record's *arguments* only:

- ``str`` arguments, and ``os.PathLike`` / exception arguments whose text
  contains a line break, get every line break replaced by its visible escape
  (``\\n``, ``\\r``, ``\\u2028`` ...), so an injection attempt stays readable
  in the log instead of disappearing into a fake line.
- The message template is left alone — it is code, and a deliberate
  multi-line message stays multi-line. Tracebacks (``exc_info``) are left
  alone for the same reason.

Every character ``str.splitlines()`` breaks on is covered, because that is
what the log viewer splits with, not just CR and LF.

Failure policy matches the secret redaction filter: never drop a record.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping

# Every code point str.splitlines() treats as a line boundary.
_LINE_BREAK_ESCAPES = {
    "\r": "\\r",
    "\n": "\\n",
    "\x0b": "\\x0b",
    "\x0c": "\\x0c",
    "\x1c": "\\x1c",
    "\x1d": "\\x1d",
    "\x1e": "\\x1e",
    "\x85": "\\x85",
    " ": "\\u2028",
    " ": "\\u2029",
}
_TABLE = str.maketrans(_LINE_BREAK_ESCAPES)


def escape_line_breaks(value: str) -> str:
    """Return ``value`` with every line break replaced by its visible escape."""
    return value.translate(_TABLE)


def _escape_arg(arg: object) -> object:
    if isinstance(arg, str):
        return escape_line_breaks(arg)
    if isinstance(arg, (BaseException, os.PathLike)):
        text = str(arg)
        escaped = escape_line_breaks(text)
        # Keep the original object when there is nothing to escape, so %r
        # and friends render exactly as before for the normal case.
        return escaped if escaped != text else arg
    return arg


class LineBreakEscapeFilter(logging.Filter):
    """Escape line breaks in a record's arguments (see module docstring)."""

    def filter(self, record: logging.LogRecord) -> bool:
        if getattr(record, "_sublarr_line_breaks_escaped", False):
            return True
        record._sublarr_line_breaks_escaped = True
        try:
            args = record.args
            if isinstance(args, tuple) and args:
                record.args = tuple(_escape_arg(a) for a in args)
            elif isinstance(args, Mapping) and args:
                record.args = {k: _escape_arg(v) for k, v in args.items()}
        except Exception:  # noqa: BLE001 — never drop a record over escaping
            pass
        return True
