"""Plan B5 — embedded track-selection ranks by language + forced + HI flags."""

from unittest.mock import patch


def _make_probe_streams():
    """Fake ffprobe output with 3 matching-language tracks for scoring."""
    return {
        "streams": [
            {
                "codec_type": "subtitle",
                "index": 2,
                "codec_name": "subrip",
                "tags": {"language": "eng"},
                "disposition": {"forced": 0},
            },
            {
                "codec_type": "subtitle",
                "index": 3,
                "codec_name": "subrip",
                "tags": {"language": "eng", "title": "SDH"},
                "disposition": {"forced": 0},
            },
            {
                "codec_type": "subtitle",
                "index": 4,
                "codec_name": "subrip",
                "tags": {"language": "eng", "title": "Forced"},
                "disposition": {"forced": 1},
            },
        ]
    }


def test_forced_query_prefers_forced_track_bonus():
    from providers.base import VideoQuery
    from providers.embedded import EmbeddedSubtitlesProvider

    provider = EmbeddedSubtitlesProvider()
    q = VideoQuery(file_path="/x.mkv", languages=["en"], forced_only=True, title="X")

    with (
        patch("providers.embedded.get_media_streams", return_value=_make_probe_streams()),
        patch("providers.embedded.os.path.exists", return_value=True),
    ):
        results = provider.search(q)

    # All three results should be returned; score_bonus differs by flags
    bonuses = {r.provider_data["stream_index"]: r.provider_data["score_bonus"] for r in results}
    # The forced track (index 4) should have the highest bonus
    assert bonuses[4] > bonuses[2]
    assert bonuses[4] > bonuses[3]


def test_hi_preference_only_boosts_hi_track():
    from providers.base import VideoQuery
    from providers.embedded import EmbeddedSubtitlesProvider

    provider = EmbeddedSubtitlesProvider()
    q = VideoQuery(file_path="/x.mkv", languages=["en"], hi_preference="prefer", title="X")

    with (
        patch("providers.embedded.get_media_streams", return_value=_make_probe_streams()),
        patch("providers.embedded.os.path.exists", return_value=True),
    ):
        results = provider.search(q)

    bonuses = {r.provider_data["stream_index"]: r.provider_data["score_bonus"] for r in results}
    # SDH track (index 3) should beat plain track (index 2) when HI preferred
    assert bonuses[3] > bonuses[2]
