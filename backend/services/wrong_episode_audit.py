"""Find saved subtitles whose release names another episode than their video.

The episode gate keeps a search from picking another episode's subtitle, but
it only sees new searches. Before it (and before the season checks of
OpenSubtitles in 1.14.6 and AnimeTosho in 1.14.2), season-1 subtitles were
saved for season-2 episodes — Clevatess S02E05/E06/E10/E12 on prod — and a
saved subtitle is never looked at again.

The audit reads, for each video and language, the release the newest
automatic download won with (from its decision log) and asks the search's
own gate about it. Only an explicit contradiction is reported ("S01E12" for
S02E12); a name without numbering, or a bare number the season may own, is
not. A hash match identified the file and is trusted.

Requeueing hands each finding to the same quarantine a rejected sync uses:
the subtitle is blocked for that video only, the file stays until a
replacement is saved, and the episode is searched again.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_SIDECAR_FORMATS = ("ass", "srt", "ssa", "vtt")


@dataclass(frozen=True)
class WrongEpisodeFinding:
    video: str
    sidecar: str
    language: str
    provider: str
    subtitle_id: str
    release: str
    reason: str

    def as_dict(self) -> dict:
        return dict(self.__dict__)


def _video_numbering(video: str) -> tuple[int, int] | None:
    from providers.episode_gate import parse_claims

    claims = parse_claims(os.path.basename(video))
    if not claims.season_episodes:
        return None
    season, episodes = claims.season_episodes[0]
    return season, min(episodes)


def _may_be_absolute(season: int, episode: int, *names: str) -> bool:
    """Whether an S01 number in the names could be this episode's absolute number.

    The search knows Sonarr's absolute number and accepts S01E<absolute>; the
    audit does not, so for a later season it leaves S01E<n> alone whenever n is
    past the episode's own number. S01E12 for S02E12 is season 1's twelfth;
    S01E17 for S02E05 may well be the seventeenth episode overall.
    """
    from providers.episode_gate import parse_claims

    if season <= 1:
        return False
    for name in names:
        for claimed_season, episodes in parse_claims(name).season_episodes:
            if claimed_season == 1 and max(episodes) > episode:
                return True
    return False


def _sidecar_for(video: str, language: str, fmt: str | None) -> str | None:
    stem = os.path.splitext(video)[0]
    for ext in dict.fromkeys([(fmt or "").lower(), *_SIDECAR_FORMATS]):
        if ext and os.path.isfile(f"{stem}.{language}.{ext}"):
            return f"{stem}.{language}.{ext}"
    return None


def _winner(decision_log_json: str | None) -> tuple[str, str]:
    try:
        final = (json.loads(decision_log_json or "{}") or {}).get("final") or {}
    except (TypeError, ValueError):
        return "", ""
    return str(final.get("filename") or ""), str(final.get("release_info") or "")


def _breakdown_keys(score_breakdown: str | None) -> set[str]:
    try:
        return set((json.loads(score_breakdown or "{}") or {}).keys())
    except (TypeError, ValueError, AttributeError):
        return set()


def _newest_provider_downloads(language: str | None) -> list:
    from db.models.providers import SubtitleDownload
    from extensions import db

    query = db.session.query(SubtitleDownload)
    if language:
        query = query.filter(SubtitleDownload.language == language)
    newest: dict[tuple[str, str], object] = {}
    for row in query.order_by(SubtitleDownload.downloaded_at.desc(), SubtitleDownload.id.desc()):
        newest.setdefault((row.file_path, row.language), row)
    return [row for row in newest.values() if (row.source or "provider") == "provider"]


def _finding_for(row) -> WrongEpisodeFinding | None:
    from providers.base import SubtitleFormat, SubtitleResult, VideoQuery
    from providers.episode_gate import episode_gate_reason
    from services.suspect_sidecars import is_suspect_sidecar

    numbering = _video_numbering(row.file_path)
    if numbering is None:
        return None
    filename, release = _winner(row.decision_log_json)
    if not (filename or release):
        return None
    sidecar = _sidecar_for(row.file_path, row.language, row.format)
    if sidecar is None or is_suspect_sidecar(sidecar):
        return None

    season, episode = numbering
    result = SubtitleResult(
        provider_name=row.provider_name,
        subtitle_id=str(row.subtitle_id),
        language=row.language,
        format=SubtitleFormat.UNKNOWN,
        filename=filename,
        release_info=release,
        matches=_breakdown_keys(row.score_breakdown),
    )
    reason = episode_gate_reason(
        result, VideoQuery(file_path=row.file_path, season=season, episode=episode)
    )
    # Only what the name contradicts; "no episode evidence" says nothing about
    # a subtitle that was already watched against its video.
    if not reason.startswith("names ") or _may_be_absolute(season, episode, filename, release):
        return None
    return WrongEpisodeFinding(
        video=row.file_path,
        sidecar=sidecar,
        language=row.language,
        provider=row.provider_name,
        subtitle_id=str(row.subtitle_id),
        release=release or filename,
        reason=reason,
    )


def scan_wrong_episodes(language: str | None = None) -> list[WrongEpisodeFinding]:
    """Saved automatic downloads whose winning release names another episode."""
    findings = []
    for row in _newest_provider_downloads(language):
        try:
            finding = _finding_for(row)
        except Exception as exc:  # noqa: BLE001 — one odd row must not stop the audit
            logger.debug("wrong-episode audit: skipped %s: %s", row.file_path, exc)
            continue
        if finding is not None:
            findings.append(finding)
    findings.sort(key=lambda f: f.video)
    return findings


def requeue_findings(findings: list[WrongEpisodeFinding]) -> int:
    """Quarantine each finding; returns how many were quarantined."""
    from services.suspect_sidecars import quarantine_wrong_sidecar, requeue_videos

    quarantined = []
    for finding in findings:
        reason = f"release {finding.release!r} {finding.reason}"
        if quarantine_wrong_sidecar(finding.sidecar, finding.video, reason, requeue=False):
            quarantined.append((finding.video, finding.language))
    # One rescan per series, not one per episode.
    requeue_videos(quarantined)
    done = len(quarantined)
    logger.info("wrong-episode audit: %d of %d findings requeued", done, len(findings))
    return done
