"""Plan B6 — shell escape runner tests (security-focused).

The marker-file injection check verifies that a malicious
``subtitle_path`` (containing shell metacharacters) cannot be executed
as shell syntax even when the runner is enabled.
"""

import os
import shutil

import pytest


def _has_echo() -> bool:
    return bool(shutil.which("echo")) or bool(shutil.which("sh")) or bool(
        shutil.which("bash")
    )


def test_shell_runner_disabled_by_default(monkeypatch):
    """Without the env flag, shell_runner refuses to execute anything."""
    monkeypatch.delenv("SUBLARR_ALLOW_SHELL_SCRIPTS", raising=False)

    from post_processing.shell_runner import run_shell_script

    result = run_shell_script(
        script="echo hello",
        context={"subtitle_path": "/m/s.srt"},
        timeout_s=5,
    )
    assert result.ok is False
    assert "disabled" in result.message.lower() or "not allowed" in result.message.lower()


@pytest.mark.skipif(not _has_echo(), reason="echo binary not available on PATH")
def test_shell_runner_enabled_executes_safe_script(monkeypatch, tmp_path):
    """With the env flag, a benign script runs and captures stdout."""
    monkeypatch.setenv("SUBLARR_ALLOW_SHELL_SCRIPTS", "true")

    from post_processing.shell_runner import run_shell_script

    result = run_shell_script(
        script="echo hello-b6",
        context={"subtitle_path": "/m/s.srt"},
        timeout_s=10,
    )
    assert result.ok is True
    assert "hello-b6" in result.message


def test_shell_runner_blocks_injection_via_context(monkeypatch, tmp_path):
    """A subtitle_path containing shell metacharacters must not execute them.

    SECURITY ASSERTION: the marker file MUST NOT be created. If it is,
    substitution is broken and an attacker could execute arbitrary commands
    via provider-supplied filenames.
    """
    monkeypatch.setenv("SUBLARR_ALLOW_SHELL_SCRIPTS", "true")

    from post_processing.shell_runner import run_shell_script

    # Use tmp_path-scoped marker to avoid coupling to /tmp existence
    marker = tmp_path / "b6_injection_marker"
    malicious = f"/dummy/test.srt; echo INJECTED > {marker}"
    result = run_shell_script(
        script="echo got {subtitle_path}",
        context={"subtitle_path": malicious},
        timeout_s=5,
    )
    # The marker file MUST NOT have been created. This is the security gate.
    assert not marker.exists(), (
        "Command injection succeeded — FAIL. substitute function must shlex.quote"
    )
    # result.ok may be True or False — what matters is no injection happened.
    _ = result.ok


@pytest.mark.skipif(
    not shutil.which("sleep"), reason="sleep binary not available on PATH"
)
def test_shell_runner_enforces_timeout(monkeypatch):
    """A runaway script is killed after timeout."""
    monkeypatch.setenv("SUBLARR_ALLOW_SHELL_SCRIPTS", "true")

    from post_processing.shell_runner import run_shell_script

    result = run_shell_script(
        script="sleep 30",
        context={"subtitle_path": "/m/s.srt"},
        timeout_s=2,
    )
    assert result.ok is False
    assert "timeout" in result.message.lower() or "timed out" in result.message.lower()


def test_shell_runner_empty_script(monkeypatch):
    """Empty script after substitution returns an error."""
    monkeypatch.setenv("SUBLARR_ALLOW_SHELL_SCRIPTS", "true")

    from post_processing.shell_runner import run_shell_script

    result = run_shell_script(
        script="",
        context={"subtitle_path": "/m/s.srt"},
        timeout_s=5,
    )
    assert result.ok is False


def test_shell_runner_command_not_found(monkeypatch):
    """A non-existent binary is reported, not crashed."""
    monkeypatch.setenv("SUBLARR_ALLOW_SHELL_SCRIPTS", "true")

    from post_processing.shell_runner import run_shell_script

    result = run_shell_script(
        script="/nonexistent/binary-b6-xyz arg1",
        context={"subtitle_path": "/m/s.srt"},
        timeout_s=5,
    )
    assert result.ok is False


def test_shell_runner_substitution_runtime():
    """_substitute must produce shlex-safe output for every placeholder."""
    monkeypatch_env = {"SUBLARR_ALLOW_SHELL_SCRIPTS": "true"}
    _ = monkeypatch_env  # placeholder — we directly call _substitute below

    import shlex

    from post_processing.shell_runner import _substitute

    result = _substitute(
        "process {subtitle_path} {video_path} {lang} {score} {trigger}",
        {
            "subtitle_path": "evil; rm -rf /",
            "video_path": "'quoted'",
            "lang": "en",
            "score": 100,
            "trigger": "after_download",
        },
    )
    # After shlex.split, the malicious path becomes ONE argument, not three
    args = shlex.split(result, posix=True)
    assert "evil; rm -rf /" in args, (
        "shlex.quote should have preserved the dangerous string as a single arg"
    )
    # The literal ';' token must not appear as a standalone arg
    assert ";" not in args
    assert "rm" not in args  # rm must not split out as its own argument
