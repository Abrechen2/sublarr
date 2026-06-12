"""Post-download shell command execution with variable substitution.

Variables available in the command string:
    {subtitle_path}  — absolute path to the saved subtitle file
    {path}           — alias for {subtitle_path} (Bazarr compat)
    {language}       — ISO 639-1 language code
    {provider}       — provider name (e.g. "jimaku")
    {score}          — integer match score
    {media_type}     — "series" | "movie" | ""
    {video_path}     — reserved for future use; currently always substituted as '' (empty string)
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
    media_type: str = "",
    enabled: bool = True,
) -> None:
    """Execute the post-download shell command if configured and enabled.

    Errors are logged as warnings but never propagated — post-processing
    is best-effort and must not break the download pipeline.

    Variables:
        {subtitle_path}  — absolute path to the saved subtitle file
        {path}           — alias for {subtitle_path} (Bazarr compat)
        {language}       — ISO 639-1 language code
        {provider}       — provider name (e.g. "jimaku")
        {score}          — integer match score
        {media_type}     — "series" | "movie" | ""
        {video_path}     — video file path (may be empty)
    """
    if not enabled:
        return
    if not command or not command.strip():
        return

    # Quote every substituted value so a path with spaces (or shell-meaningful
    # characters from a provider) stays a single argv token after shlex.split
    # instead of fragmenting into several arguments.
    expanded = (
        command.replace("{subtitle_path}", shlex.quote(subtitle_path))
        .replace("{path}", shlex.quote(subtitle_path))
        .replace("{language}", shlex.quote(language))
        .replace("{provider}", shlex.quote(provider))
        .replace("{score}", shlex.quote(str(int(score))))
        .replace("{media_type}", shlex.quote(media_type))
        .replace("{video_path}", shlex.quote(video_path))
    )
    try:
        argv = shlex.split(expanded)
    except ValueError as exc:
        logger.warning("post_download_command: invalid shell syntax, skipping: %s", exc)
        return
    try:
        logger.info("Running post-download command: %s", argv)
        subprocess.run(argv, shell=False, timeout=60, check=False)  # noqa: S603
    except subprocess.TimeoutExpired:
        logger.warning("post_download_command timed out after 60 s")
    except Exception as exc:
        logger.warning("post_download_command failed: %s", exc)
