import os

from services.subtitle_health.checkers.language_mislabel import detect
from services.subtitle_health.models import IssueType, Severity, TargetKind
from services.subtitle_health.scan import ScanContext, Target

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "subtitle_health")


def _read(name):
    with open(os.path.join(FIX, name), "rb") as fh:
        return fh.read()


def _target(lang, raw, path):
    return Target(
        kind=TargetKind.SIDECAR, path=path, stream_index=None, lang=lang, codec="srt", raw=raw
    )


def test_md5_duplicate_across_languages_is_confirmed():
    english = _read("english.srt")
    ctx = ScanContext(
        episode_id=1,
        video_path="/m/x.mkv",
        targets=[
            _target("de", english, "/m/x.de.srt"),  # English content tagged de
            _target("en", english, "/m/x.en.srt"),
        ],
    )
    issues = [i for i in detect(ctx) if i.type == IssueType.LANGUAGE_MISLABEL]
    assert any(i.severity == Severity.CONFIRMED and i.lang == "de" for i in issues)


def test_content_language_mismatch_without_md5_dup():
    english = _read("english.srt")
    ctx = ScanContext(
        episode_id=1,
        video_path="/m/x.mkv",
        targets=[
            _target("de", english + b"\n", "/m/x.de.srt"),  # not identical to en
            _target("en", english, "/m/x.en.srt"),
        ],
    )
    issues = [i for i in detect(ctx) if i.type == IssueType.LANGUAGE_MISLABEL]
    assert any(i.lang == "de" for i in issues)


def test_correct_languages_yield_no_issue():
    ctx = ScanContext(
        episode_id=1,
        video_path="/m/x.mkv",
        targets=[
            _target("de", _read("german.srt"), "/m/x.de.srt"),
            _target("en", _read("english.srt"), "/m/x.en.srt"),
        ],
    )
    assert [i for i in detect(ctx) if i.type == IssueType.LANGUAGE_MISLABEL] == []
