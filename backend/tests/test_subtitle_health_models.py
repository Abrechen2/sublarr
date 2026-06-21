from services.subtitle_health.models import (
    Issue,
    IssueType,
    ScanResult,
    Severity,
    TargetKind,
)


def test_issue_to_dict_roundtrip():
    issue = Issue(
        type=IssueType.ASS_ESCAPE_LEAK,
        severity=Severity.CONFIRMED,
        episode_id=54680,
        target_kind=TargetKind.EMBEDDED,
        target_path="/media/x.mkv",
        stream_index=2,
        lang="ger",
        count=177,
        snippets=["Du hast erkannt\\Nwie gut..."],
        raw_hash="abc123",
        fixable=True,
        suggested_fix="repair_escapes",
    )
    d = issue.to_dict()
    assert d["type"] == "ass_escape_leak"
    assert d["severity"] == "confirmed"
    assert d["target_kind"] == "embedded"
    assert d["count"] == 177
    assert d["snippets"] == ["Du hast erkannt\\Nwie gut..."]


def test_scan_result_to_dict_groups_issues():
    issue = Issue(
        type=IssueType.LANGUAGE_MISLABEL,
        severity=Severity.CONFIRMED,
        episode_id=54680,
        target_kind=TargetKind.SIDECAR,
        target_path="/media/x.de.srt",
        stream_index=None,
        lang="de",
        count=1,
        snippets=[],
        raw_hash="deadbeef",
        fixable=True,
        suggested_fix="trash_sidecar",
    )
    result = ScanResult(episode_id=54680, video_path="/media/x.mkv", issues=[issue])
    d = result.to_dict()
    assert d["episode_id"] == 54680
    assert d["issue_count"] == 1
    assert d["issues"][0]["type"] == "language_mislabel"
    assert d["healthy"] is False


def test_scan_result_healthy_when_no_issues():
    result = ScanResult(episode_id=1, video_path="/m/x.mkv", issues=[])
    assert result.to_dict()["healthy"] is True
