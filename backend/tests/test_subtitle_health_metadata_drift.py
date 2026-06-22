import os

from services.subtitle_health.checkers.container_metadata_drift import detect
from services.subtitle_health.models import IssueType, TargetKind
from services.subtitle_health.scan import ScanContext, Target

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "subtitle_health")


def _read(name):
    with open(os.path.join(FIX, name), "rb") as fh:
        return fh.read()


def test_embedded_lang_disagrees_with_content():
    # Embedded stream tagged 'ger' but content is English.
    ctx = ScanContext(
        episode_id=1,
        video_path="/m/x.mkv",
        targets=[
            Target(
                kind=TargetKind.EMBEDDED,
                path="/m/x.mkv",
                stream_index=0,
                lang="ger",
                codec="subrip",
                raw=_read("english.srt"),
            )
        ],
    )
    issues = detect(ctx)
    assert len(issues) == 1
    assert issues[0].type == IssueType.CONTAINER_METADATA_DRIFT


def test_sidecars_are_ignored_by_this_checker():
    ctx = ScanContext(
        episode_id=1,
        video_path="/m/x.mkv",
        targets=[
            Target(
                kind=TargetKind.SIDECAR,
                path="/m/x.de.srt",
                stream_index=None,
                lang="de",
                codec="srt",
                raw=_read("english.srt"),
            )
        ],
    )
    assert detect(ctx) == []  # language_mislabel handles sidecars


def test_embedded_untagged_stream_not_flagged():
    ctx = ScanContext(
        episode_id=1,
        video_path="/m/x.mkv",
        targets=[
            Target(
                kind=TargetKind.EMBEDDED,
                path="/m/x.mkv",
                stream_index=0,
                lang="",
                codec="subrip",
                raw=_read("english.srt"),
            )
        ],
    )
    assert detect(ctx) == []


def test_correct_embedded_lang_yields_no_issue():
    ctx = ScanContext(
        episode_id=1,
        video_path="/m/x.mkv",
        targets=[
            Target(
                kind=TargetKind.EMBEDDED,
                path="/m/x.mkv",
                stream_index=1,
                lang="ger",
                codec="subrip",
                raw=_read("german.srt"),
            )
        ],
    )
    assert detect(ctx) == []
