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


def test_persist_backfills_issue_id(app_ctx):
    # The scan API returns ScanResult.to_dict(); the fix endpoint needs the
    # persisted finding id, so persist must backfill it onto the issue.
    result = _result()
    assert result.issues[0].id is None
    store.persist_scan_result(result, scanner_version=1)
    persisted_id = result.issues[0].id
    assert persisted_id is not None
    rows = store.get_findings_for_episode(5)
    assert rows[0]["id"] == persisted_id
    # to_dict surfaces the id for the frontend.
    assert result.to_dict()["issues"][0]["id"] == persisted_id


def test_dismiss_finding_sets_status_and_survives_rescan(app_ctx):
    store.persist_scan_result(_result(), scanner_version=1)
    fid = store.get_findings_for_episode(5)[0]["id"]
    assert store.dismiss_finding(fid) is True
    # dismissed → no longer in the open/actionable list
    assert store.get_findings_for_episode(5) == []
    # a rescan must NOT resurrect a dismissed finding
    store.persist_scan_result(_result(), scanner_version=1)
    assert store.get_finding(fid)["status"] == "dismissed"


def test_dismiss_missing_finding_returns_false(app_ctx):
    assert store.dismiss_finding(999999) is False


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
