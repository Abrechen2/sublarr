"""Plan B4 — PenaltyRule pipeline tests."""

import pytest


def test_penalty_rule_abc_exists():
    from wanted_search.penalty_rules import PenaltyRule

    # Abstract class — cannot instantiate
    with pytest.raises(TypeError):
        PenaltyRule()


def test_register_penalty_decorator_adds_to_registry():
    from wanted_search.penalty_rules import _RULE_REGISTRY, PenaltyRule, register_penalty

    # Count before
    before = len(_RULE_REGISTRY)

    @register_penalty
    class DummyRule(PenaltyRule):
        rule_id = "dummy_rule_test"
        default_weight = 5
        label = "Dummy"
        description = "Test rule"

        def applies(self, candidate, query):
            return False

        def weight(self, candidate, query):
            return self.default_weight

    assert len(_RULE_REGISTRY) == before + 1
    assert DummyRule in _RULE_REGISTRY

    # Cleanup so subsequent tests aren't polluted
    _RULE_REGISTRY.remove(DummyRule)


# ─── Rule-specific tests (Task 2) ────────────────────────────────────────────


def _make_query(**kw):
    from providers.base import VideoQuery

    defaults = dict(
        file_path="/m/S01E01.mkv",
        series_title="X",
        season=1,
        episode=1,
        release_group="RLSGRP",
        source="BluRay",
        resolution="1080p",
        video_codec="x265",
        year=2024,
    )
    defaults.update(kw)
    return VideoQuery(**defaults)


def _make_result(**kw):
    from providers.base import SubtitleFormat, SubtitleResult

    defaults = dict(
        provider_name="p",
        subtitle_id="1",
        language="en",
        release_info="BluRay RLSGRP 1080p x265",
        format=SubtitleFormat.SRT,
        hearing_impaired=False,
        forced=False,
    )
    defaults.update(kw)
    return SubtitleResult(**defaults)


# --- Port group tests (one pair per rule) ---


def test_release_group_match_applies():
    from wanted_search.penalty_rules import ReleaseGroupMatchRule

    rule = ReleaseGroupMatchRule()
    assert rule.applies(_make_result(), _make_query()) is True
    assert rule.applies(_make_result(release_info="BluRay OTHER 1080p"), _make_query()) is False


def test_format_bonus_ass_applies():
    from providers.base import SubtitleFormat
    from wanted_search.penalty_rules import FormatBonusAssRule

    rule = FormatBonusAssRule()
    assert rule.applies(_make_result(format=SubtitleFormat.ASS), _make_query()) is True
    assert rule.applies(_make_result(format=SubtitleFormat.SRT), _make_query()) is False


def test_hi_preference_prefer_applies():
    from wanted_search.penalty_rules import HiPreferencePreferRule

    rule = HiPreferencePreferRule()
    q = _make_query(hi_preference="prefer")
    assert rule.applies(_make_result(hearing_impaired=True), q) is True
    assert rule.applies(_make_result(hearing_impaired=False), q) is False


def test_hi_preference_exclude_applies():
    from wanted_search.penalty_rules import HiPreferenceExcludeOrOnlyRule

    rule = HiPreferenceExcludeOrOnlyRule()
    assert (
        rule.applies(_make_result(hearing_impaired=True), _make_query(hi_preference="exclude"))
        is True
    )
    assert (
        rule.applies(_make_result(hearing_impaired=False), _make_query(hi_preference="only"))
        is True
    )
    assert (
        rule.applies(_make_result(hearing_impaired=True), _make_query(hi_preference="include"))
        is False
    )


def test_forced_preference_prefer_applies():
    from wanted_search.penalty_rules import ForcedPreferencePreferRule

    rule = ForcedPreferencePreferRule()
    q = _make_query(forced_scoring="prefer")
    assert rule.applies(_make_result(forced=True), q) is True
    assert rule.applies(_make_result(forced=False), q) is False


def test_forced_preference_exclude_applies():
    from wanted_search.penalty_rules import ForcedPreferenceExcludeOrOnlyRule

    rule = ForcedPreferenceExcludeOrOnlyRule()
    assert rule.applies(_make_result(forced=True), _make_query(forced_scoring="exclude")) is True
    assert rule.applies(_make_result(forced=False), _make_query(forced_scoring="only")) is True
    assert rule.applies(_make_result(forced=True), _make_query(forced_scoring="include")) is False


def test_source_match_applies():
    from wanted_search.penalty_rules import SourceMatchRule

    rule = SourceMatchRule()
    assert rule.applies(_make_result(), _make_query(source="BluRay")) is True
    assert (
        rule.applies(_make_result(release_info="WEB-DL 1080p"), _make_query(source="BluRay"))
        is False
    )


def test_resolution_match_applies():
    from wanted_search.penalty_rules import ResolutionMatchRule

    rule = ResolutionMatchRule()
    assert rule.applies(_make_result(), _make_query(resolution="1080p")) is True
    assert rule.applies(_make_result(), _make_query(resolution="720p")) is False


def test_audio_codec_match_applies():
    from wanted_search.penalty_rules import AudioCodecMatchRule

    rule = AudioCodecMatchRule()
    assert rule.applies(_make_result(release_info="BluRay DTS 1080p"), _make_query()) is True
    assert rule.applies(_make_result(release_info="BluRay 1080p"), _make_query()) is False


def test_video_codec_match_applies():
    from wanted_search.penalty_rules import VideoCodecMatchRule

    rule = VideoCodecMatchRule()
    assert (
        rule.applies(
            _make_result(release_info="BluRay x265 1080p"), _make_query(video_codec="x265")
        )
        is True
    )
    assert (
        rule.applies(
            _make_result(release_info="BluRay x264 1080p"), _make_query(video_codec="x265")
        )
        is False
    )


# --- Add group (new opt-in rules) ---


def test_release_group_substring_loose_applies():
    from wanted_search.penalty_rules import ReleaseGroupSubstringLooseRule

    rule = ReleaseGroupSubstringLooseRule()
    q = _make_query(release_group="SubsPlease")
    assert rule.applies(_make_result(release_info="SubsPls 1080p"), q) is True
    assert rule.applies(_make_result(release_info="OTHER 1080p"), q) is False


def test_source_hierarchy_penalty_applies():
    from wanted_search.penalty_rules import SourceHierarchyPenaltyRule

    rule = SourceHierarchyPenaltyRule()
    # Candidate is WEB-DL, query wants BluRay → applies
    assert (
        rule.applies(_make_result(release_info="WEB-DL x265"), _make_query(source="BluRay")) is True
    )
    # Candidate is BluRay, query wants BluRay → no penalty
    assert (
        rule.applies(_make_result(release_info="BluRay x265"), _make_query(source="BluRay"))
        is False
    )


def test_year_off_by_one_tolerance_applies():
    from wanted_search.penalty_rules import YearOffByOneToleranceRule

    rule = YearOffByOneToleranceRule()
    # Candidate's release_info mentions 2023, query is 2024 → within tolerance
    assert (
        rule.applies(_make_result(release_info="BluRay 2023 RLSGRP"), _make_query(year=2024))
        is True
    )
    # 4 years off → no apply
    assert (
        rule.applies(_make_result(release_info="BluRay 2020 RLSGRP"), _make_query(year=2024))
        is False
    )


def test_codec_upgrade_penalty_applies():
    from wanted_search.penalty_rules import CodecUpgradePenaltyRule

    rule = CodecUpgradePenaltyRule()
    # File is x265 but candidate is x264 → penalty
    assert (
        rule.applies(_make_result(release_info="BluRay x264"), _make_query(video_codec="x265"))
        is True
    )
    # Matching codec → no penalty
    assert (
        rule.applies(_make_result(release_info="BluRay x265"), _make_query(video_codec="x265"))
        is False
    )


def test_machine_translation_penalty_applies():
    from wanted_search.penalty_rules import MachineTranslationPenaltyRule

    rule = MachineTranslationPenaltyRule()
    assert rule.applies(_make_result(machine_translated=True), _make_query()) is True
    assert rule.applies(_make_result(mt_confidence=85.0), _make_query()) is True
    assert (
        rule.applies(_make_result(machine_translated=False, mt_confidence=20.0), _make_query())
        is False
    )


# --- Negative baseline: empty query/result shouldn't crash ---


def test_empty_query_no_rules_crash():
    """With an empty release_info + empty query fields, the pipeline must not raise."""
    from wanted_search.penalty_rules import apply_penalty_pipeline

    candidate = _make_result(release_info="", format=None)
    breakdown = apply_penalty_pipeline(
        candidate,
        _make_query(release_group="", source="", resolution="", video_codec="", year=None),
    )
    assert isinstance(breakdown, dict)
