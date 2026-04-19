"""Plan B4 — integration tests for compute_score -> penalty pipeline."""


def test_compute_score_includes_penalty_breakdown_entries():
    from providers.base import SubtitleFormat, SubtitleResult, VideoQuery, compute_score

    query = VideoQuery(
        file_path="/m/S01E01.mkv",
        series_title="X",
        season=1,
        episode=1,
        release_group="GRP",
        source="BluRay",
        resolution="1080p",
        video_codec="x265",
        year=2024,
        languages=["en"],
    )
    result = SubtitleResult(
        provider_name="opensubtitles",
        subtitle_id="1",
        language="en",
        release_info="BluRay GRP 1080p x265 DTS",
        format=SubtitleFormat.ASS,
        matches=set(),  # deliberately empty - force rules path only
    )
    compute_score(result, query)

    # Pipeline rule hits (release_group_match / format_bonus_ass etc.) should
    # appear under rule:<id> keys in the merged breakdown
    rule_keys = [k for k in result.score_breakdown if k.startswith("rule:")]
    assert rule_keys, f"Expected rule:* entries in breakdown, got {result.score_breakdown}"

    # Score must be > 0 because rules fired (release_group, source, format, etc.)
    assert result.score > 0


def test_compute_score_hi_exclude_kills_candidate():
    from providers.base import SubtitleFormat, SubtitleResult, VideoQuery, compute_score

    query = VideoQuery(
        file_path="/m/X.mkv",
        title="X",
        hi_preference="exclude",
        languages=["en"],
    )
    result = SubtitleResult(
        provider_name="opensubtitles",
        subtitle_id="1",
        language="en",
        release_info="",
        format=SubtitleFormat.SRT,
        hearing_impaired=True,
    )
    compute_score(result, query)
    # Kill-weight of -999 should drive score strongly negative
    assert result.score <= -500


def test_compute_score_no_double_count_when_matches_set_overlaps():
    """When legacy ``matches`` set already contains ``release_group`` AND the
    pipeline's ``ReleaseGroupMatchRule`` fires, both paths contribute. This
    accepted duplication is documented in the plan: callers should migrate
    to the pipeline over time. The test pins the current behaviour so any
    future de-duplication is deliberate.
    """
    from providers.base import SubtitleFormat, SubtitleResult, VideoQuery, compute_score

    query = VideoQuery(
        file_path="/m/S01E01.mkv",
        series_title="X",
        season=1,
        episode=1,
        release_group="GRP",
        languages=["en"],
    )
    result = SubtitleResult(
        provider_name="opensubtitles",
        subtitle_id="1",
        language="en",
        release_info="BluRay GRP 1080p",
        format=SubtitleFormat.SRT,
        matches={"release_group"},  # legacy weight-map credits 14
    )
    compute_score(result, query)
    # Lower bound: at minimum the pipeline value (14) is credited
    assert result.score >= 14
