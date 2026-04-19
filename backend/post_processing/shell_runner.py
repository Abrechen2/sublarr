"""Opt-in shell script executor for post-processing (Plan B6).

ONLY loads when ``SUBLARR_ALLOW_SHELL_SCRIPTS=true``. Uses
``subprocess.run`` with ``shell=False`` + args list so user-supplied
context values can never be interpreted as shell syntax. Placeholders in
the script body are replaced with ``shlex.quote``'d values; the runner
splits the final script via ``shlex.split`` with POSIX semantics.

Security surface:
  - Env flag gate (fail-closed default)
  - ``shlex.quote`` every substituted value
  - ``subprocess.run(shell=False, args=shlex.split(...))``
  - Timeout enforced (default 30s)
  - Restricted env — only PATH passed through
  - stdout + stderr captured (truncated) to the audit record
"""

from __future__ import annotations

import logging
import os
import shlex
import subprocess
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_SUBSTITUTION_KEYS = ("subtitle_path", "video_path", "lang", "score", "trigger")
_MAX_OUTPUT_BYTES = 4000
_DEFAULT_TIMEOUT = 30


@dataclass
class ShellResult:
    op_id: str = "shell_script"
    ok: bool = False
    duration_ms: int = 0
    message: str = ""


def _flag_enabled() -> bool:
    return os.environ.get("SUBLARR_ALLOW_SHELL_SCRIPTS", "").lower() == "true"


def _substitute(script: str, context: dict) -> str:
    """Replace ``{placeholder}`` tokens with ``shlex.quote``'d context values."""
    out = script
    for key in _SUBSTITUTION_KEYS:
        value = str(context.get(key, ""))
        out = out.replace("{" + key + "}", shlex.quote(value))
    return out


def _elapsed_ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)


def run_shell_script(
    script: str,
    context: dict,
    timeout_s: int = _DEFAULT_TIMEOUT,
) -> ShellResult:
    """Execute a user-defined shell script with variable substitution.

    Returns a :class:`ShellResult` (never raises). stdout + stderr are
    captured into ``ShellResult.message`` (truncated to ~4 KB).
    """
    start = time.monotonic()

    if not _flag_enabled():
        return ShellResult(
            ok=False,
            duration_ms=0,
            message="shell scripts disabled (set SUBLARR_ALLOW_SHELL_SCRIPTS=true)",
        )

    substituted = _substitute(script, context)

    try:
        args = shlex.split(substituted, posix=True)
    except ValueError as exc:
        return ShellResult(
            ok=False, duration_ms=_elapsed_ms(start), message=f"parse error: {exc}"
        )

    if not args:
        return ShellResult(ok=False, duration_ms=0, message="empty script")

    restricted_env = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
    }

    try:
        proc = subprocess.run(
            args,
            shell=False,
            env=restricted_env,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        combined = (proc.stdout + proc.stderr).strip()[:_MAX_OUTPUT_BYTES]
        ok = proc.returncode == 0
        msg = combined or ("ok" if ok else f"exit {proc.returncode}")
        return ShellResult(ok=ok, duration_ms=_elapsed_ms(start), message=msg)
    except subprocess.TimeoutExpired:
        return ShellResult(
            ok=False, duration_ms=_elapsed_ms(start), message="timeout expired"
        )
    except FileNotFoundError as exc:
        return ShellResult(
            ok=False,
            duration_ms=_elapsed_ms(start),
            message=f"command not found: {exc}",
        )
    except Exception as exc:
        logger.warning("shell script runner failed: %s", exc)
        return ShellResult(ok=False, duration_ms=_elapsed_ms(start), message=str(exc))
