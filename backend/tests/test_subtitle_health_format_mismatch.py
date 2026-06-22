from services.subtitle_health.checkers.format_mismatch import detect
from services.subtitle_health.models import IssueType, Severity, TargetKind
from services.subtitle_health.scan import ScanContext, Target


def _ctx(raw, codec="srt", path="/m/x.de.srt"):
    return ScanContext(
        episode_id=1,
        video_path="/m/x.mkv",
        targets=[
            Target(
                kind=TargetKind.SIDECAR,
                path=path,
                stream_index=None,
                lang="de",
                codec=codec,
                raw=raw,
            )
        ],
    )


def test_ass_content_in_srt_is_confirmed():
    raw = b"[Script Info]\nScriptType: v4.00+\n[Events]\nDialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,Hallo\n"
    issues = detect(_ctx(raw))
    assert len(issues) == 1
    assert issues[0].type == IssueType.FORMAT_MISMATCH
    assert issues[0].severity == Severity.CONFIRMED


def test_real_srt_yields_no_issue():
    raw = b"1\n00:00:01,000 --> 00:00:02,000\nHallo Welt.\n"
    assert detect(_ctx(raw)) == []


def test_ass_codec_with_ass_content_is_fine():
    raw = b"[Script Info]\n[Events]\nDialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,Hi\n"
    assert detect(_ctx(raw, codec="ass", path="/m/x.de.ass")) == []
