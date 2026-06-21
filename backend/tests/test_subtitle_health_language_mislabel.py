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


def test_embedded_dup_does_not_suppress_other_streams():
    """FIX 4: dup_paths must key on (path, stream_index), not path alone.

    streams 0+1 share identical bytes (MD5 dup pair); stream 2 has DISTINCT
    bytes (english + trailing newline) so it is NOT in the dup group, but it
    shares the same video_path as the dup pair. The old code added t.path to
    dup_paths, so stream 2's content detection was wrongly suppressed. With the
    fix, dup_paths holds (path, stream_index) tuples, and stream 2's tuple is
    not there, so content detection still runs and flags 'declared de, content en'.
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
            # Stream 2: distinct bytes (not an MD5 dup), but same path.
            # Declared 'de', content is English → must be flagged.
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
    # stream 2 must still be flagged by content detection
    assert any(i.stream_index == 2 for i in issues)
