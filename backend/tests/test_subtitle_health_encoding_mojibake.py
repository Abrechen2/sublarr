from services.subtitle_health.checkers.encoding_mojibake import detect
from services.subtitle_health.models import IssueType, Severity, TargetKind
from services.subtitle_health.scan import ScanContext, Target


def _ctx(raw):
    return ScanContext(
        episode_id=1,
        video_path="/m/x.mkv",
        targets=[
            Target(
                kind=TargetKind.SIDECAR,
                path="/m/x.de.srt",
                stream_index=None,
                lang="de",
                codec="srt",
                raw=raw,
            )
        ],
    )


def test_invalid_utf8_is_confirmed():
    raw = "1\n00:00:01,000 --> 00:00:02,000\nSchön warm.\n".encode("cp1252")
    issues = detect(_ctx(raw))
    assert len(issues) == 1
    assert issues[0].type == IssueType.ENCODING_MOJIBAKE
    assert issues[0].severity == Severity.CONFIRMED


def test_mojibake_markers_are_suspicious():
    raw = "1\n00:00:01,000 --> 00:00:02,000\nSchÃ¶n Ã¼berall Ã¤hnlich.\n".encode()
    issues = detect(_ctx(raw))
    assert len(issues) == 1
    assert issues[0].severity == Severity.SUSPICIOUS


def test_clean_utf8_yields_no_issue():
    raw = "1\n00:00:01,000 --> 00:00:02,000\nSchön warm.\n".encode()
    assert detect(_ctx(raw)) == []
