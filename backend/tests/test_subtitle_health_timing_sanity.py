from services.subtitle_health.checkers.timing_sanity import detect
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


def test_zero_duration_cue_flagged():
    raw = b"1\n00:00:05,000 --> 00:00:05,000\nInstant.\n"
    issues = detect(_ctx(raw))
    assert len(issues) == 1
    assert issues[0].type == IssueType.TIMING_SANITY
    assert issues[0].severity == Severity.SUSPICIOUS


def test_overlapping_cues_flagged():
    raw = (
        b"1\n00:00:01,000 --> 00:00:05,000\nFirst.\n\n"
        b"2\n00:00:03,000 --> 00:00:06,000\nSecond overlaps.\n"
    )
    issues = detect(_ctx(raw))
    assert any("overlap" in s for i in issues for s in i.snippets)


def test_clean_timing_yields_no_issue():
    raw = (
        b"1\n00:00:01,000 --> 00:00:03,000\nNormal one.\n\n"
        b"2\n00:00:04,000 --> 00:00:06,000\nNormal two.\n"
    )
    assert detect(_ctx(raw)) == []
