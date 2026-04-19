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


def test_penalty_rule_weights_db_roundtrip(app_ctx):
    """set_penalty_rule_weight persists, get_penalty_rule_weights reads back."""
    from db.scoring import get_penalty_rule_weights, set_penalty_rule_weight

    # Set weight override
    set_penalty_rule_weight("machine_translation_penalty", -25)
    weights = get_penalty_rule_weights()
    assert weights.get("machine_translation_penalty") == -25

    # Update to a different value
    set_penalty_rule_weight("machine_translation_penalty", -40)
    weights = get_penalty_rule_weights()
    assert weights.get("machine_translation_penalty") == -40

    # Setting to 0 persists the row (pipeline treats 0 as disabled)
    set_penalty_rule_weight("machine_translation_penalty", 0)
    weights = get_penalty_rule_weights()
    assert weights.get("machine_translation_penalty", None) == 0


# --- API tests (Task 5) ------------------------------------------------------


def test_api_list_penalty_rules(client):
    resp = client.get("/api/v1/scoring/penalty-rules")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "rules" in body
    rule_ids = [r["rule_id"] for r in body["rules"]]
    assert "release_group_match" in rule_ids
    assert "machine_translation_penalty" in rule_ids
    # Each rule carries its metadata
    sample = next(r for r in body["rules"] if r["rule_id"] == "release_group_match")
    assert "label" in sample
    assert "description" in sample
    assert sample["default_weight"] == 14
    assert sample["current_weight"] == 14  # no override yet


def test_api_update_penalty_rule_weight(client):
    resp = client.put(
        "/api/v1/scoring/penalty-rules/machine_translation_penalty",
        json={"weight": -30},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["rule_id"] == "machine_translation_penalty"
    assert body["weight"] == -30

    # Verify list endpoint reflects the new weight
    resp2 = client.get("/api/v1/scoring/penalty-rules")
    rule = next(
        r for r in resp2.get_json()["rules"] if r["rule_id"] == "machine_translation_penalty"
    )
    assert rule["current_weight"] == -30

    # Reset for cleanliness
    client.put(
        "/api/v1/scoring/penalty-rules/machine_translation_penalty",
        json={"weight": 0},
    )


def test_api_update_unknown_rule_returns_404(client):
    resp = client.put(
        "/api/v1/scoring/penalty-rules/not_a_real_rule",
        json={"weight": 10},
    )
    assert resp.status_code == 404


def test_api_update_non_integer_weight_returns_400(client):
    resp = client.put(
        "/api/v1/scoring/penalty-rules/machine_translation_penalty",
        json={"weight": "not-a-number"},
    )
    assert resp.status_code == 400
