from services.subtitle_health.checkers.unicode_control_chars import detect
from services.subtitle_health.models import IssueType, TargetKind
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


def test_null_byte_flagged():
    raw = b"1\n00:00:01,000 --> 00:00:02,000\nHallo\x00Welt.\n"
    issues = detect(_ctx(raw))
    assert len(issues) == 1
    assert issues[0].type == IssueType.UNICODE_CONTROL_CHARS


def test_bidi_override_flagged():
    raw = ("1\n00:00:01,000 --> 00:00:02,000\nHallo‮Welt.\n").encode()
    assert len(detect(_ctx(raw))) == 1


def test_clean_text_yields_no_issue():
    raw = b"1\n00:00:01,000 --> 00:00:02,000\nHallo Welt.\n"
    assert detect(_ctx(raw)) == []
