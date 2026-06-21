from services.subtitle_health.models import TargetKind
from services.subtitle_health.scan import ScanContext, Target


def test_target_has_metadata_defaults():
    t = Target(
        kind=TargetKind.EMBEDDED,
        path="/m/x.mkv",
        stream_index=0,
        lang="ger",
        codec="subrip",
        raw=b"",
    )
    assert t.forced is False
    assert t.default is False
    assert t.title == ""


def test_scan_context_has_target_languages_default():
    ctx = ScanContext(episode_id=1, video_path="/m/x.mkv")
    assert ctx.target_languages == []
