"""Safety-guard tests for scripts/stage-rc-from-prod.sh.

The script clones the prod Sublarr Postgres into the RC Postgres — destructive on
the target. These tests pin the guard logic that prevents it from ever hitting
prod/beta or running without an explicit FORCE=1. All refusal paths exit before
any SSH/docker call, so the tests need no live host.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "stage-rc-from-prod.sh"


def _find_bash():
    """Locate a POSIX bash. On Windows, prefer Git Bash and avoid the WSL relay
    (System32\\bash.exe), which cannot execute a Windows-path script."""
    for p in (
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files\Git\usr\bin\bash.exe",
        r"C:\Program Files (x86)\Git\bin\bash.exe",
    ):
        if os.path.exists(p):
            return p
    which = shutil.which("bash")
    if which and "system32" not in which.lower():
        return which
    return None


BASH = _find_bash()
pytestmark = pytest.mark.skipif(BASH is None, reason="no POSIX bash (only WSL relay) available")


def _run(env):
    return subprocess.run(
        [BASH, SCRIPT.as_posix()],
        env={**os.environ, **env},
        capture_output=True,
        text=True,
    )


def test_refuses_without_force():
    r = _run({"FORCE": "", "TARGET_PG": "sublarr-rc-postgres"})
    assert r.returncode == 2
    assert "FORCE=1" in r.stderr


def test_refuses_prod_target():
    r = _run({"FORCE": "1", "TARGET_PG": "sublarr-postgres"})
    assert r.returncode == 3


def test_refuses_beta_target():
    r = _run({"FORCE": "1", "TARGET_PG": "sublarr-beta-postgres"})
    assert r.returncode == 3


def test_refuses_unknown_target():
    r = _run({"FORCE": "1", "TARGET_PG": "random-pg"})
    assert r.returncode == 4
