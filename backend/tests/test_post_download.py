"""Tests for post_download.run_post_download_command."""


def test_run_post_download_command_noop_when_empty():
    from post_download import run_post_download_command

    # Should not raise
    run_post_download_command("", "/sub.ass", "de", "opensubtitles", 200, "/video.mkv")


def test_noop_when_whitespace():
    from post_download import run_post_download_command

    run_post_download_command("   ", "/sub.ass", "de", "opensubtitles", 200)


def test_run_post_download_command_substitutes_variables(monkeypatch):
    import subprocess

    from post_download import run_post_download_command

    calls = []

    def mock_run(cmd, shell, timeout, check):
        calls.append(cmd)

    monkeypatch.setattr(subprocess, "run", mock_run)
    run_post_download_command(
        "echo {language} {score}", "/media/ep.ass", "de", "jimaku", 180, "/media/ep.mkv"
    )
    assert len(calls) == 1
    assert "de" in calls[0]
    assert "180" in calls[0]


def test_run_post_download_command_handles_failure_gracefully(monkeypatch):
    import subprocess

    from post_download import run_post_download_command

    def mock_run(*args, **kwargs):
        raise OSError("command not found")

    monkeypatch.setattr(subprocess, "run", mock_run)
    # Must not raise
    run_post_download_command("bad_command", "/sub.ass", "de", "test", 100, "")
