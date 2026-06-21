from services.subtitle_health import store
from services.subtitle_health.models import (
    Issue,
    IssueType,
    ScanResult,
    Severity,
    TargetKind,
)


def _result():
    issue = Issue(
        type=IssueType.ASS_ESCAPE_LEAK,
        severity=Severity.CONFIRMED,
        episode_id=5,
        target_kind=TargetKind.SIDECAR,
        target_path="/m/x.de.srt",
        stream_index=None,
        lang="de",
        count=3,
        snippets=["a"],
        raw_hash="hh",
        fixable=True,
        suggested_fix="repair_escapes",
    )
    return ScanResult(episode_id=5, video_path="/m/x.mkv", issues=[issue])


def test_persist_and_query_findings(app_ctx):
    store.persist_scan_result(_result(), scanner_version=1)
    rows = store.get_findings_for_episode(5)
    assert len(rows) == 1
    assert rows[0]["issue_type"] == "ass_escape_leak"
    assert rows[0]["status"] == "open"


def test_persist_replaces_prior_open_findings(app_ctx):
    store.persist_scan_result(_result(), scanner_version=1)
    store.persist_scan_result(_result(), scanner_version=1)
    rows = store.get_findings_for_episode(5)
    assert len(rows) == 1  # re-scan replaces, does not duplicate


def test_suggested_fix_persisted(app_ctx):
    store.persist_scan_result(_result(), scanner_version=1)
    rows = store.get_findings_for_episode(5)
    assert rows[0]["suggested_fix"] == "repair_escapes"


def test_record_and_get_manifest(app_ctx):
    fix_id = store.record_fix(
        finding_id=None,
        fixer="repair_escapes",
        action="repair_escapes",
        target_path="/m/x.de.srt",
        trashed_original_path="/trash/x.de.srt",
        original_hash="o",
        fixed_hash="f",
        reversible=True,
    )
    m = store.get_fix(fix_id)
    assert m["fixer"] == "repair_escapes"
    assert m["reversible"] is True
