from services.subtitle_health.checkers.ass_escape_leak import detect
from services.subtitle_health.models import IssueType, Severity, TargetKind
from services.subtitle_health.scan import ScanContext, Target


def _ctx(raw: bytes):
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


def test_detects_literal_backslash_N():  # noqa: N802
    raw = b"1\n00:00:01,000 --> 00:00:02,000\nDu hast erkannt\\Nwie gut?\n"
    issues = detect(_ctx(raw))
    assert len(issues) == 1
    assert issues[0].type == IssueType.ASS_ESCAPE_LEAK
    assert issues[0].severity == Severity.CONFIRMED
    assert issues[0].count == 1
    assert "\\N" in issues[0].snippets[0]


def test_ignores_double_escaped_NN():  # noqa: N802
    raw = b"1\n00:00:01,000 --> 00:00:02,000\nA literal \\\\N token.\n"
    assert detect(_ctx(raw)) == []


def test_clean_srt_yields_no_issue():
    raw = b"1\n00:00:01,000 --> 00:00:02,000\nGanz normaler Text.\n"
    assert detect(_ctx(raw)) == []


def test_tag_leak_only_is_suspicious():
    raw = b"1\n00:00:01,000 --> 00:00:02,000\n{\\an8}Schild oben\n"
    issues = detect(_ctx(raw))
    assert len(issues) == 1
    assert issues[0].severity == Severity.SUSPICIOUS


def test_embedded_ass_with_N_is_not_flagged():  # noqa: N802
    """FIX 1: codec guard — \\N is valid in ASS/SSA; must not false-positive."""
    raw = b"[Events]\nDialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,Hallo\\Nwelt\n"
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
            ),
        ],
    )
    assert detect(ctx) == []
