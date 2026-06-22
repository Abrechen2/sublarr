from services.subtitle_health.checkers.missing_language import detect
from services.subtitle_health.models import IssueType, Severity, TargetKind
from services.subtitle_health.scan import ScanContext, Target


def _t(lang, kind=TargetKind.SIDECAR):
    return Target(
        kind=kind, path=f"/m/x.{lang}.srt", stream_index=None, lang=lang, codec="srt", raw=b"x"
    )


def test_missing_target_language_reported():
    ctx = ScanContext(
        episode_id=1,
        video_path="/m/x.mkv",
        targets=[_t("en")],
        target_languages=["de", "en"],
    )
    issues = detect(ctx)
    assert len(issues) == 1
    assert issues[0].type == IssueType.MISSING_LANGUAGE
    assert issues[0].severity == Severity.INFO
    assert issues[0].lang == "de"


def test_all_languages_present_yields_no_issue():
    ctx = ScanContext(
        episode_id=1,
        video_path="/m/x.mkv",
        targets=[_t("de"), _t("en", kind=TargetKind.EMBEDDED)],
        target_languages=["de", "en"],
    )
    assert detect(ctx) == []


def test_no_target_languages_configured_yields_no_issue():
    ctx = ScanContext(episode_id=1, video_path="/m/x.mkv", targets=[_t("en")])
    assert detect(ctx) == []
