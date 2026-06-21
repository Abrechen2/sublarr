"""Persistence for findings + fix manifests. DB failures are swallowed."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


def persist_scan_result(result, scanner_version: int = 1) -> None:
    """Replace the open findings for this episode with the fresh scan's."""
    from db.models.core import SubtitleHealthFinding
    from extensions import db

    try:
        if result.episode_id is not None:
            db.session.query(SubtitleHealthFinding).filter_by(
                episode_id=result.episode_id, status="open"
            ).delete()
        for issue in result.issues:
            db.session.add(
                SubtitleHealthFinding(
                    episode_id=issue.episode_id,
                    target_kind=issue.target_kind.value,
                    target_path=issue.target_path,
                    stream_index=issue.stream_index,
                    lang=issue.lang,
                    issue_type=issue.type.value,
                    severity=issue.severity.value,
                    count=issue.count,
                    snippets_json=json.dumps(issue.snippets[:3]),
                    raw_hash=issue.raw_hash,
                    suggested_fix=issue.suggested_fix,
                    status="open",
                    scanner_version=scanner_version,
                    detected_at=datetime.now(UTC),
                )
            )
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception("subtitle_health: persist_scan_result failed")


def _finding_to_dict(row) -> dict:
    return {
        "id": row.id,
        "episode_id": row.episode_id,
        "target_kind": row.target_kind,
        "target_path": row.target_path,
        "stream_index": row.stream_index,
        "lang": row.lang,
        "issue_type": row.issue_type,
        "severity": row.severity,
        "count": row.count,
        "snippets": json.loads(row.snippets_json or "[]"),
        "raw_hash": row.raw_hash,
        "status": row.status,
        "suggested_fix": row.suggested_fix,
    }


def get_findings_for_episode(episode_id: int) -> list[dict]:
    from db.models.core import SubtitleHealthFinding
    from extensions import db

    rows = (
        db.session.query(SubtitleHealthFinding)
        .filter_by(episode_id=episode_id, status="open")
        .all()
    )
    return [_finding_to_dict(r) for r in rows]


def get_finding(finding_id: int) -> dict | None:
    from db.models.core import SubtitleHealthFinding
    from extensions import db

    row = db.session.get(SubtitleHealthFinding, finding_id)
    return _finding_to_dict(row) if row else None


def mark_finding(finding_id: int, status: str) -> None:
    from db.models.core import SubtitleHealthFinding
    from extensions import db

    try:
        row = db.session.get(SubtitleHealthFinding, finding_id)
        if row:
            row.status = status
            db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception("subtitle_health: mark_finding failed")


def record_fix(
    *,
    finding_id,
    fixer,
    action,
    target_path,
    trashed_original_path,
    original_hash,
    fixed_hash,
    reversible,
    fixer_version=1,
) -> int | None:
    from db.models.core import SubtitleHealthFix
    from extensions import db

    try:
        row = SubtitleHealthFix(
            finding_id=finding_id,
            fixer=fixer,
            action=action,
            target_path=target_path,
            trashed_original_path=trashed_original_path,
            original_hash=original_hash,
            fixed_hash=fixed_hash,
            fixer_version=fixer_version,
            reversible=reversible,
            applied_at=datetime.now(UTC),
        )
        db.session.add(row)
        db.session.commit()
        return row.id
    except Exception:
        db.session.rollback()
        logger.exception("subtitle_health: record_fix failed")
        return None


def get_fix(fix_id: int) -> dict | None:
    from db.models.core import SubtitleHealthFix
    from extensions import db

    row = db.session.get(SubtitleHealthFix, fix_id)
    if not row:
        return None
    return {
        "id": row.id,
        "finding_id": row.finding_id,
        "fixer": row.fixer,
        "action": row.action,
        "target_path": row.target_path,
        "trashed_original_path": row.trashed_original_path,
        "original_hash": row.original_hash,
        "fixed_hash": row.fixed_hash,
        "reversible": row.reversible,
    }


def report_summary() -> dict:
    """Aggregate open findings across the library for the report endpoint."""
    from db.models.core import SubtitleHealthFinding
    from extensions import db

    rows = db.session.query(SubtitleHealthFinding).filter_by(status="open").all()
    by_type: dict[str, int] = {}
    episodes: set[int] = set()
    for r in rows:
        by_type[r.issue_type] = by_type.get(r.issue_type, 0) + 1
        if r.episode_id is not None:
            episodes.add(r.episode_id)
    return {
        "total_findings": len(rows),
        "by_type": by_type,
        "affected_episodes": len(episodes),
    }
