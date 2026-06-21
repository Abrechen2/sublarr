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


def test_embedded_ger_tag_with_german_content_not_flagged():
    # "ger" is the 3-letter code for German; genuine German content must NOT
    # be flagged as mislabeled just because lingua returns "de".
    german = _read("german.srt")
    ctx = ScanContext(
        episode_id=1,
        video_path="/m/x.mkv",
        targets=[
            Target(
                kind=TargetKind.EMBEDDED,
                path="/m/x.mkv",
                stream_index=0,
                lang="ger",
                codec="srt",
                raw=german,
            ),
        ],
    )
    issues = [i for i in detect(ctx) if i.type == IssueType.LANGUAGE_MISLABEL]
    assert issues == []


def test_embedded_target_not_content_checked_here():
    # Embedded content-language mismatch is container_metadata_drift's job,
    # not language_mislabel — avoid double-reporting.
    english = _read("english.srt")
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
                raw=english,
            )
        ],
    )
    assert [i for i in detect(ctx) if i.type == IssueType.LANGUAGE_MISLABEL] == []


def test_embedded_dup_does_not_suppress_other_streams():
    """dup_paths must key on (path, stream_index), not path alone.

    Streams 0+1 share identical bytes (MD5 dup pair) and get flagged by the
    md5-dup arm. Stream 2 has DISTINCT bytes so it is NOT in the dup group.
    This test verifies:
    - dup_paths uses (path, stream_index) tuples so stream 2 is not wrongly
      excluded from its arm by proximity to the dup pair.
    - The md5-dup arm still reports both dup streams (0 and 1).
    - Stream 2 is EMBEDDED, so language_mislabel's content-detection arm
      deliberately skips it (container_metadata_drift handles that instead).
    """
    english = _read("english.srt")
    ctx = ScanContext(
        episode_id=1,
        video_path="/m/x.mkv",
        targets=[
            Target(
                kind=TargetKind.EMBEDDED,
                path="/m/x.mkv",
                stream_index=0,
                lang="de",
                codec="srt",
                raw=english,
            ),
            Target(
                kind=TargetKind.EMBEDDED,
                path="/m/x.mkv",
                stream_index=1,
                lang="en",
                codec="srt",
                raw=english,
            ),
            # Stream 2: distinct bytes (not an MD5 dup), same path.
            # Embedded → content-detection is container_metadata_drift's job.
            Target(
                kind=TargetKind.EMBEDDED,
                path="/m/x.mkv",
                stream_index=2,
                lang="de",
                codec="srt",
                raw=english + b"\n",  # distinct MD5 — not in dup group
            ),
        ],
    )
    issues = [i for i in detect(ctx) if i.type == IssueType.LANGUAGE_MISLABEL]
    # The md5-dup pair (streams 0+1) must still be reported.
    dup_stream_indexes = {i.stream_index for i in issues}
    assert 0 in dup_stream_indexes and 1 in dup_stream_indexes
    # Stream 2 is NOT flagged here — it's embedded, delegated to container_metadata_drift.
    assert 2 not in dup_stream_indexes
