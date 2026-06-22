from services.subtitle_health.checkers.empty_or_tiny import detect
from services.subtitle_health.models import IssueType, Severity, TargetKind
from services.subtitle_health.scan import ScanContext, Target


def _ctx(raw, forced=False):
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
                forced=forced,
            )
        ],
    )


def test_empty_file_is_confirmed():
    issues = detect(_ctx(b""))
    assert len(issues) == 1
    assert issues[0].type == IssueType.EMPTY_OR_TINY
    assert issues[0].severity == Severity.CONFIRMED


def test_tiny_full_sub_is_suspicious():
    raw = b"1\n00:00:01,000 --> 00:00:02,000\nHi.\n"
    issues = detect(_ctx(raw))
    assert len(issues) == 1
    assert issues[0].severity == Severity.SUSPICIOUS


def test_forced_track_with_few_cues_is_exempt():
    raw = b"1\n00:00:01,000 --> 00:00:02,000\nSign text.\n"
    assert detect(_ctx(raw, forced=True)) == []


def test_normal_sub_yields_no_issue():
    cues = "".join(
        f"{i}\n00:00:{i:02d},000 --> 00:00:{i:02d},500\nLine {i}.\n\n" for i in range(1, 30)
    )
    assert detect(_ctx(cues.encode())) == []
