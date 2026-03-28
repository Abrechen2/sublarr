"""Post-download shell command execution with variable substitution.

Variables available in the command string:
    {subtitle_path}  — absolute path to the saved subtitle file
    {language}       — ISO 639-1 language code
    {provider}       — provider name (e.g. "jimaku")
    {score}          — integer match score
    {video_path}     — absolute path to the source video file (may be empty)
"""

import logging
import shlex
import subprocess

logger = logging.getLogger(__name__)


def run_post_download_command(
    command: str,
    subtitle_path: str,
    language: str,
    provider: str,
    score: int,
    video_path: str = "",
) -> None:
    """Execute the post-download shell command if configured.

    Errors are logged as warnings but never propagated — post-processing
    is best-effort and must not break the download pipeline.
    """
    if not command or not command.strip():
        return

    expanded = (
        command.replace("{subtitle_path}", shlex.quote(subtitle_path))
        .replace("{language}", shlex.quote(language))
        .replace("{provider}", shlex.quote(provider))
        .replace("{score}", str(int(score)))
        .replace("{video_path}", shlex.quote(video_path))
    )
    try:
        logger.info("Running post-download command: %s", expanded)
        subprocess.run(expanded, shell=True, timeout=60, check=False)
    except subprocess.TimeoutExpired:
        logger.warning("post_download_command timed out after 60 s")
    except Exception as exc:
        logger.warning("post_download_command failed: %s", exc)
