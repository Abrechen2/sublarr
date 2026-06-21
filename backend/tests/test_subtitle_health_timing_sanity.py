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


def test_ass_overlap_is_not_flagged():
    # Two ASS dialogue events overlapping in time is legitimate (layers/signs).
    raw = (
        b"[Script Info]\nScriptType: v4.00+\n"
        b"[V4+ Styles]\n"
        b"[Events]\n"
        b"Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        b"Dialogue: 0,0:00:01.00,0:00:05.00,Default,,0,0,0,,First line here\n"
        b"Dialogue: 1,0:00:03.00,0:00:06.00,Default,,0,0,0,,Second overlapping line\n"
    )
    ctx = ScanContext(
        episode_id=1,
        video_path="/m/x.mkv",
        targets=[
            Target(
                kind=TargetKind.EMBEDDED,
                path="/m/x.mkv",
                stream_index=0,
                lang="ger",
                codec="ass",
                raw=raw,
            )
        ],
    )
    issues = detect(ctx)
    assert not any("overlap" in s for i in issues for s in i.snippets)
