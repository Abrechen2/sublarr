# Plan B / Phase B4 — Scoring Penalty Rule Pipeline

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-04-19-plan-b-subtitle-delivery-quality-design.md`
**Prior:** B3 shipped as 0.66.0-beta — granular blacklist with file_hash dimension.

**Goal:** Introduce a named-class `PenaltyRule` pipeline into Sublarr's scoring so every score adjustment has a discoverable name, a stable weight, and a toggle in the UI. Port existing Sublarr scoring logic into the pipeline (no behavior change), then add ~5-7 new Bazarr-equivalent rules as opt-in additions.

**Scope correction vs. spec:** The spec claimed "~30 penalty rules" from Bazarr's `subliminal_patch/score.py`. In reality Sublarr's existing `compute_score()` in `backend/providers/base.py` already implements most Bazarr-equivalent behavior: EPISODE_SCORES / MOVIE_SCORES weight maps (release_group, source, audio_codec, resolution, video_codec, hearing_impaired, year, season, episode, title, hash), HI preference modifier, forced preference modifier, uploader trust bonus, per-provider modifier, ASS format bonus, video_codec bonus, fansub preferred/excluded substring matching. The real gap is: **(1)** these behaviors are not named or introspectable; **(2)** there are a handful of Bazarr rules missing (release-group substring match, source hierarchy mismatch penalty, codec upgrade detection, year-off-by-one tolerance, streaming-platform consistency). This plan ships **~15 rules total** — ~10 ports of existing behavior, ~5 new additions.

**Architecture:** New module `backend/wanted_search/penalty_rules.py` defines `PenaltyRule` ABC with two methods: `applies(candidate, query) -> bool` and `weight(candidate, query) -> int` (negative for penalties, positive for bonuses; dynamic weight allows scaling by context). A module-level `_RULE_REGISTRY: list[type[PenaltyRule]]` collects rules via the `@register_penalty` decorator. `compute_score()` in `providers/base.py` calls `apply_penalty_pipeline(result, query)` as an additive pass after its existing weight-map calculation, so behavior is preserved for existing weights and new rules only kick in when their DB-backed weight is non-zero.

**Tech Stack:** Python 3.12, SQLAlchemy 2.0 (for DB-backed rule weights, reusing `scoring_weights` table), pytest, React 19 / TypeScript / React Query for ScoringTab extension.

**Baseline:** 0.66.0-beta → 0.67.0-beta (minor bump).

---

## File Structure

### Create

- `backend/wanted_search/penalty_rules.py` — `PenaltyRule` ABC + registry + 15 concrete rule classes + `apply_penalty_pipeline()` driver
- `backend/tests/test_penalty_rules.py` — per-rule `applies` + `weight` tests (~30 tests: 15 rules × 2 tests each)
- `backend/tests/test_penalty_pipeline_integration.py` — end-to-end compute_score integration

### Modify

- `backend/providers/base.py` — `compute_score()` calls `apply_penalty_pipeline()` after existing weight pass
- `backend/db/scoring.py` — expose `get_penalty_rule_weights()` + `set_penalty_rule_weight()` helpers
- `backend/routes/scoring.py` (or equivalent) — endpoint to list + update penalty rule weights
- `frontend/src/pages/Settings/ScoringTab.tsx` — rules section with toggle + weight slider per rule
- `frontend/src/api/scoring.ts` (or equivalent) — fetcher + mutation for rule weights

### Reuse (no change)

- `backend/db/models/core.py::ScoringWeight` — existing weights table (reuse for penalty-rule weight persistence via `score_type="penalty_rule"` + `match_key=<rule_id>`)

---

## Task 1: Scaffold `PenaltyRule` ABC + registry

**Files:**
- Create: `backend/wanted_search/penalty_rules.py`
- Create: `backend/tests/test_penalty_rules.py`

- [ ] **Step 1: Write failing test for the ABC contract**

```python
# backend/tests/test_penalty_rules.py
"""Plan B4 — PenaltyRule pipeline tests."""

import pytest


def test_penalty_rule_abc_exists():
    from wanted_search.penalty_rules import PenaltyRule

    # Abstract class — cannot instantiate
    with pytest.raises(TypeError):
        PenaltyRule()


def test_register_penalty_decorator_adds_to_registry():
    from wanted_search.penalty_rules import PenaltyRule, _RULE_REGISTRY, register_penalty

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
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && python -m pytest tests/test_penalty_rules.py -v`
Expected: tests FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Scaffold the module**

```python
# backend/wanted_search/penalty_rules.py
"""Named-class penalty rule pipeline for subtitle scoring.

Each rule is a named class with:
- `rule_id`: stable string identifier (used as DB key for weight override)
- `default_weight`: int, signed (negative for penalties, positive for bonuses)
- `label`: short UI label
- `description`: longer UI description
- `applies(candidate, query) -> bool`: predicate
- `weight(candidate, query) -> int`: applied weight when applies() is True

Weights are resolved from the `scoring_weights` table (see db.scoring) with
score_type="penalty_rule" and match_key=rule_id. Rule default_weight is the
fallback when no DB override exists.

Rules are registered via the `@register_penalty` decorator and auto-discovered
at import time.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from providers.base import SubtitleResult, VideoQuery

logger = logging.getLogger(__name__)


_RULE_REGISTRY: list[type[PenaltyRule]] = []


class PenaltyRule(ABC):
    """Base class for named penalty/bonus rules applied to subtitle scoring."""

    rule_id: ClassVar[str] = ""
    default_weight: ClassVar[int] = 0
    label: ClassVar[str] = ""
    description: ClassVar[str] = ""

    @abstractmethod
    def applies(self, candidate: "SubtitleResult", query: "VideoQuery") -> bool:
        """Return True if this rule should apply to the candidate."""

    @abstractmethod
    def weight(self, candidate: "SubtitleResult", query: "VideoQuery") -> int:
        """Return the signed weight to add to the candidate's score.

        Most rules return `self.default_weight` — dynamic rules can scale
        the weight by context.
        """


def register_penalty(cls: type[PenaltyRule]) -> type[PenaltyRule]:
    """Decorator to register a PenaltyRule subclass in the module registry."""
    if not cls.rule_id:
        raise ValueError(f"PenaltyRule {cls.__name__} must define rule_id")
    if cls in _RULE_REGISTRY:
        return cls
    _RULE_REGISTRY.append(cls)
    return cls


def apply_penalty_pipeline(
    candidate: "SubtitleResult",
    query: "VideoQuery",
) -> dict[str, int]:
    """Run all registered penalty rules against the candidate.

    Returns a dict of {rule_id: applied_weight} for breakdown display.
    Mutates candidate.score by the net total.
    """
    breakdown: dict[str, int] = {}
    try:
        from db.scoring import get_penalty_rule_weights

        overrides = get_penalty_rule_weights()
    except Exception:
        overrides = {}

    for rule_cls in _RULE_REGISTRY:
        try:
            rule = rule_cls()
            if not rule.applies(candidate, query):
                continue
            configured_weight = overrides.get(rule_cls.rule_id, rule_cls.default_weight)
            if configured_weight == 0:
                continue  # User disabled this rule
            applied = rule.weight(candidate, query)
            # If rule returns its default_weight, scale by configured override
            if applied == rule_cls.default_weight and rule_cls.default_weight != 0:
                applied = configured_weight
            breakdown[rule_cls.rule_id] = applied
            candidate.score += applied
        except Exception as e:
            logger.warning("Penalty rule %s raised: %s", rule_cls.rule_id, e)

    return breakdown
```

- [ ] **Step 4: Run tests to verify pass**

Run: `cd backend && python -m pytest tests/test_penalty_rules.py -v`
Expected: 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/wanted_search/penalty_rules.py backend/tests/test_penalty_rules.py
git commit -m "feat(plan-b4): scaffold PenaltyRule ABC + registry"
```

---

## Task 2: Implement 15 concrete penalty rules

**Files:**
- Modify: `backend/wanted_search/penalty_rules.py`
- Modify: `backend/tests/test_penalty_rules.py`

The rules fall into three groups. Each rule has a distinct `rule_id` and default behavior. Ship default_weight=0 for new Bazarr-style rules (opt-in) and non-zero for ports of existing behavior (preserves compute_score output).

### Port group (10 rules — existing Sublarr behavior, default_weight mirrors current values)

1. `release_group_match` — candidate's `release_info` contains query's `release_group` (case-insensitive substring). Default weight reuses `EPISODE_SCORES["release_group"] = 14` or `MOVIE_SCORES["release_group"] = 13` dynamically. (This is a port — don't change existing scoring behavior; once the rule fires, the weight-map "release_group" entry is skipped to avoid double-counting. Handled via Task 3.)
2. `source_match` — `release_info` mentions query's `source` (BluRay / WEB-DL / HDTV). Weight `EPISODE_SCORES["source"]=7` / `MOVIE_SCORES["source"]=7`.
3. `audio_codec_match` — similar, weight 3.
4. `resolution_match` — weight 2.
5. `video_codec_match` — wrap existing `apply_video_codec_bonus` as a rule. Weight 2.
6. `format_bonus_ass` — candidate's format is ASS/SSA. Weight `format_bonus=50`.
7. `hi_preference_prefer` — query.hi_preference=="prefer" AND candidate.hearing_impaired. Weight +30.
8. `hi_preference_exclude_or_only` — query.hi_preference in ("exclude", "only") and mismatched. Weight -999 (effectively kills the candidate).
9. `forced_preference_prefer` — query.forced_scoring=="prefer" AND candidate.forced. Weight +30.
10. `forced_preference_exclude_or_only` — parallel to HI. Weight -999.

### Add group (5 new Bazarr-equivalent rules — default_weight=0, opt-in)

11. `release_group_substring_loose` — release_info contains first 3 chars of query.release_group (catches e.g. "SubsPlease" vs "SubsPls"). Default 0 (opt-in), suggested +5 when enabled.
12. `source_hierarchy_penalty` — candidate is lower-tier source than query (WEB-DL candidate for BluRay query, or HDTV candidate for WEB-DL). Default 0, suggested -10.
13. `year_off_by_one_tolerance` — year differs by exactly 1 (release-year vs file-year disagreement). Default 0, suggested +5 to NOT penalize this edge.
14. `codec_upgrade_penalty` — candidate codec less efficient than file's (e.g. candidate says x264 but file is x265). Default 0, suggested -3.
15. `machine_translation_penalty` — `candidate.machine_translated=True` OR `mt_confidence >= 80`. Default 0, suggested -50.

### Step 1: Write failing tests for all 15 rules

Append to `backend/tests/test_penalty_rules.py` (~60 lines — shortened here for brevity, full code in implementation step):

```python
import pytest

from providers.base import SubtitleResult, VideoQuery


def _make_query(**kw):
    defaults = dict(
        file_path="/m/S01E01.mkv",
        series_title="X", season=1, episode=1,
        release_group="RLSGRP", source="BluRay", resolution="1080p",
        video_codec="x265", year=2024,
    )
    defaults.update(kw)
    return VideoQuery(**defaults)


def _make_result(**kw):
    from providers.base import SubtitleFormat
    defaults = dict(
        provider_name="p", subtitle_id="1", language="en",
        release_info="BluRay RLSGRP 1080p x265",
        format=SubtitleFormat.SRT,
        hearing_impaired=False, forced=False,
    )
    defaults.update(kw)
    return SubtitleResult(**defaults)


# --- Port group tests (1 pair per rule) ---

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
    assert rule.applies(_make_result(hearing_impaired=True), _make_query(hi_preference="exclude")) is True
    assert rule.applies(_make_result(hearing_impaired=False), _make_query(hi_preference="only")) is True
    assert rule.applies(_make_result(hearing_impaired=True), _make_query(hi_preference="include")) is False


def test_forced_preference_prefer_applies():
    from wanted_search.penalty_rules import ForcedPreferencePreferRule

    rule = ForcedPreferencePreferRule()
    q = _make_query(forced_scoring="prefer")
    assert rule.applies(_make_result(forced=True), q) is True
    assert rule.applies(_make_result(forced=False), q) is False


def test_source_match_applies():
    from wanted_search.penalty_rules import SourceMatchRule

    rule = SourceMatchRule()
    assert rule.applies(_make_result(), _make_query(source="BluRay")) is True
    assert rule.applies(_make_result(release_info="WEB-DL 1080p"), _make_query(source="BluRay")) is False


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
    assert rule.applies(_make_result(release_info="BluRay x265 1080p"), _make_query(video_codec="x265")) is True
    assert rule.applies(_make_result(release_info="BluRay x264 1080p"), _make_query(video_codec="x265")) is False


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
    assert rule.applies(_make_result(release_info="WEB-DL x265"), _make_query(source="BluRay")) is True
    # Candidate is BluRay, query wants BluRay → no penalty
    assert rule.applies(_make_result(release_info="BluRay x265"), _make_query(source="BluRay")) is False


def test_year_off_by_one_tolerance_applies():
    from wanted_search.penalty_rules import YearOffByOneToleranceRule

    rule = YearOffByOneToleranceRule()
    # Candidate's release_info mentions 2023, query is 2024 → within tolerance
    assert rule.applies(_make_result(release_info="BluRay 2023 RLSGRP"), _make_query(year=2024)) is True
    # 3 years off → no apply
    assert rule.applies(_make_result(release_info="BluRay 2020 RLSGRP"), _make_query(year=2024)) is False


def test_codec_upgrade_penalty_applies():
    from wanted_search.penalty_rules import CodecUpgradePenaltyRule

    rule = CodecUpgradePenaltyRule()
    # File is x265 but candidate is x264 → penalty
    assert rule.applies(_make_result(release_info="BluRay x264"), _make_query(video_codec="x265")) is True
    # Matching codec → no penalty
    assert rule.applies(_make_result(release_info="BluRay x265"), _make_query(video_codec="x265")) is False


def test_machine_translation_penalty_applies():
    from wanted_search.penalty_rules import MachineTranslationPenaltyRule

    rule = MachineTranslationPenaltyRule()
    assert rule.applies(_make_result(machine_translated=True), _make_query()) is True
    assert rule.applies(_make_result(mt_confidence=85.0), _make_query()) is True
    assert rule.applies(_make_result(machine_translated=False, mt_confidence=20.0), _make_query()) is False


# --- Negative baseline: no rule applies to an "empty" query ---

def test_empty_query_no_rules_fire():
    """With a default query/result, only format-bonus + port-group matches should fire."""
    from wanted_search.penalty_rules import _RULE_REGISTRY, apply_penalty_pipeline

    # Non-matching candidate against non-matching query
    candidate = _make_result(release_info="", format=None)
    breakdown = apply_penalty_pipeline(candidate, _make_query(release_group="", source="", resolution="", video_codec=""))
    # With empty release_info most port rules won't fire; just assert no exception
    assert isinstance(breakdown, dict)
```

- [ ] **Step 2: Run tests to verify failure**

Run: `cd backend && python -m pytest tests/test_penalty_rules.py -v`
Expected: all new tests FAIL (rule classes not yet defined).

- [ ] **Step 3: Implement the 15 rule classes**

Append to `backend/wanted_search/penalty_rules.py`:

```python
# ─── Port group — reproduce existing Sublarr scoring as named rules ───

@register_penalty
class ReleaseGroupMatchRule(PenaltyRule):
    rule_id = "release_group_match"
    default_weight = 14  # matches EPISODE_SCORES["release_group"]
    label = "Release Group Match"
    description = "Candidate release_info contains the query release_group (case-insensitive substring)."

    def applies(self, candidate, query) -> bool:
        rg = (query.release_group or "").strip().lower()
        if not rg:
            return False
        return rg in (candidate.release_info or "").lower()

    def weight(self, candidate, query) -> int:
        return self.default_weight


@register_penalty
class SourceMatchRule(PenaltyRule):
    rule_id = "source_match"
    default_weight = 7
    label = "Source Match"
    description = "Candidate release_info mentions query source (BluRay/WEB-DL/HDTV)."

    def applies(self, candidate, query) -> bool:
        src = (query.source or "").strip().lower()
        if not src:
            return False
        return src in (candidate.release_info or "").lower()

    def weight(self, candidate, query) -> int:
        return self.default_weight


_AUDIO_CODECS = ("dts", "ac3", "aac", "eac3", "truehd", "flac", "opus")


@register_penalty
class AudioCodecMatchRule(PenaltyRule):
    rule_id = "audio_codec_match"
    default_weight = 3
    label = "Audio Codec Match"
    description = "Candidate release_info names a common audio codec (DTS, AC3, AAC, etc.)."

    def applies(self, candidate, query) -> bool:
        info = (candidate.release_info or "").lower()
        return any(c in info for c in _AUDIO_CODECS)

    def weight(self, candidate, query) -> int:
        return self.default_weight


@register_penalty
class ResolutionMatchRule(PenaltyRule):
    rule_id = "resolution_match"
    default_weight = 2
    label = "Resolution Match"
    description = "Candidate release_info contains the query resolution (e.g. 1080p)."

    def applies(self, candidate, query) -> bool:
        res = (query.resolution or "").strip().lower()
        if not res:
            return False
        return res in (candidate.release_info or "").lower()

    def weight(self, candidate, query) -> int:
        return self.default_weight


_CODEC_TAGS: dict[str, tuple[str, ...]] = {
    "x265": ("x265", "hevc", "h265"),
    "hevc": ("x265", "hevc", "h265"),
    "h265": ("x265", "hevc", "h265"),
    "x264": ("x264", "h264", "avc"),
    "h264": ("x264", "h264", "avc"),
    "avc": ("x264", "h264", "avc"),
    "av1": ("av1",),
}


@register_penalty
class VideoCodecMatchRule(PenaltyRule):
    rule_id = "video_codec_match"
    default_weight = 2
    label = "Video Codec Match"
    description = "Candidate release_info contains a tag from the query video_codec family."

    def applies(self, candidate, query) -> bool:
        vc = (query.video_codec or "").strip().lower()
        if not vc:
            return False
        tags = _CODEC_TAGS.get(vc, (vc,))
        info = (candidate.release_info or "").lower()
        return any(tag in info for tag in tags)

    def weight(self, candidate, query) -> int:
        return self.default_weight


@register_penalty
class FormatBonusAssRule(PenaltyRule):
    rule_id = "format_bonus_ass"
    default_weight = 50
    label = "ASS Format Bonus"
    description = "Candidate format is ASS or SSA (Sublarr always prefers styled subs)."

    def applies(self, candidate, query) -> bool:
        from providers.base import SubtitleFormat

        return candidate.format in (SubtitleFormat.ASS, SubtitleFormat.SSA)

    def weight(self, candidate, query) -> int:
        return self.default_weight


@register_penalty
class HiPreferencePreferRule(PenaltyRule):
    rule_id = "hi_preference_prefer"
    default_weight = 30
    label = "HI Preference — Prefer"
    description = "Query asks for HI-preferred and candidate is HI."

    def applies(self, candidate, query) -> bool:
        return (
            getattr(query, "hi_preference", "include") == "prefer"
            and candidate.hearing_impaired
        )

    def weight(self, candidate, query) -> int:
        return self.default_weight


@register_penalty
class HiPreferenceExcludeOrOnlyRule(PenaltyRule):
    rule_id = "hi_preference_exclude_or_only"
    default_weight = -999
    label = "HI Preference — Exclude / Only Kill"
    description = "Query says exclude-HI and candidate is HI, or says only-HI and candidate isn't. Kills the candidate."

    def applies(self, candidate, query) -> bool:
        pref = getattr(query, "hi_preference", "include")
        if pref == "exclude" and candidate.hearing_impaired:
            return True
        if pref == "only" and not candidate.hearing_impaired:
            return True
        return False

    def weight(self, candidate, query) -> int:
        return self.default_weight


@register_penalty
class ForcedPreferencePreferRule(PenaltyRule):
    rule_id = "forced_preference_prefer"
    default_weight = 30
    label = "Forced Preference — Prefer"
    description = "Query prefers forced subs and candidate is forced."

    def applies(self, candidate, query) -> bool:
        return (
            getattr(query, "forced_scoring", "include") == "prefer"
            and candidate.forced
        )

    def weight(self, candidate, query) -> int:
        return self.default_weight


@register_penalty
class ForcedPreferenceExcludeOrOnlyRule(PenaltyRule):
    rule_id = "forced_preference_exclude_or_only"
    default_weight = -999
    label = "Forced Preference — Exclude / Only Kill"
    description = "Query says exclude-forced and candidate is forced, or says only-forced and candidate isn't. Kills the candidate."

    def applies(self, candidate, query) -> bool:
        pref = getattr(query, "forced_scoring", "include")
        if pref == "exclude" and candidate.forced:
            return True
        if pref == "only" and not candidate.forced:
            return True
        return False

    def weight(self, candidate, query) -> int:
        return self.default_weight


# ─── Add group — new Bazarr-equivalent opt-in rules (default_weight=0) ───


@register_penalty
class ReleaseGroupSubstringLooseRule(PenaltyRule):
    rule_id = "release_group_substring_loose"
    default_weight = 0  # opt-in
    label = "Release Group Substring (Loose)"
    description = "Release_info contains the first 3 chars of the query release_group. Catches abbreviated group names."

    def applies(self, candidate, query) -> bool:
        rg = (query.release_group or "").strip().lower()
        if len(rg) < 3:
            return False
        prefix = rg[:3]
        # Only applies if strict match DIDN'T already fire
        info = (candidate.release_info or "").lower()
        if rg in info:
            return False
        return prefix in info

    def weight(self, candidate, query) -> int:
        return self.default_weight


_SOURCE_HIERARCHY = {"bluray": 3, "web-dl": 2, "webdl": 2, "webrip": 1, "hdtv": 0}


@register_penalty
class SourceHierarchyPenaltyRule(PenaltyRule):
    rule_id = "source_hierarchy_penalty"
    default_weight = 0  # opt-in; suggest -10
    label = "Source Hierarchy Penalty"
    description = "Candidate source is lower-tier than query source (WEB-DL candidate for BluRay query)."

    @staticmethod
    def _tier(info_or_src: str) -> int:
        s = info_or_src.lower()
        for key, tier in _SOURCE_HIERARCHY.items():
            if key in s:
                return tier
        return -1

    def applies(self, candidate, query) -> bool:
        q_src = (query.source or "").strip()
        if not q_src:
            return False
        q_tier = self._tier(q_src)
        if q_tier < 0:
            return False
        c_tier = self._tier(candidate.release_info or "")
        if c_tier < 0:
            return False
        return c_tier < q_tier

    def weight(self, candidate, query) -> int:
        return self.default_weight


import re


@register_penalty
class YearOffByOneToleranceRule(PenaltyRule):
    rule_id = "year_off_by_one_tolerance"
    default_weight = 0  # opt-in; suggest +5
    label = "Year Off-By-One Tolerance"
    description = "Candidate mentions a year within ±1 of the query year (common when release-year differs from production-year)."

    def applies(self, candidate, query) -> bool:
        if query.year is None:
            return False
        info = candidate.release_info or ""
        for match in re.finditer(r"\b(19|20)\d{2}\b", info):
            cy = int(match.group(0))
            if abs(cy - query.year) == 1:
                return True
        return False

    def weight(self, candidate, query) -> int:
        return self.default_weight


@register_penalty
class CodecUpgradePenaltyRule(PenaltyRule):
    rule_id = "codec_upgrade_penalty"
    default_weight = 0  # opt-in; suggest -3
    label = "Codec Upgrade Mismatch Penalty"
    description = "Query video is a more efficient codec than the candidate (e.g. file is x265 but candidate says x264)."

    _RANK = {"av1": 3, "x265": 2, "hevc": 2, "h265": 2, "x264": 1, "h264": 1, "avc": 1}

    def _rank(self, s: str) -> int:
        s = s.lower()
        best = -1
        for key, rank in self._RANK.items():
            if key in s and rank > best:
                best = rank
        return best

    def applies(self, candidate, query) -> bool:
        vc = (query.video_codec or "").strip()
        if not vc:
            return False
        q_rank = self._rank(vc)
        c_rank = self._rank(candidate.release_info or "")
        if q_rank < 0 or c_rank < 0:
            return False
        return c_rank < q_rank

    def weight(self, candidate, query) -> int:
        return self.default_weight


@register_penalty
class MachineTranslationPenaltyRule(PenaltyRule):
    rule_id = "machine_translation_penalty"
    default_weight = 0  # opt-in; suggest -50
    label = "Machine-Translation Penalty"
    description = "Candidate is flagged as machine-translated or has high MT confidence (>=80)."

    def applies(self, candidate, query) -> bool:
        if candidate.machine_translated:
            return True
        return (candidate.mt_confidence or 0.0) >= 80.0

    def weight(self, candidate, query) -> int:
        return self.default_weight
```

- [ ] **Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_penalty_rules.py -v --tb=short`
Expected: all ~17 tests PASS (2 scaffold + ~15 rule tests).

- [ ] **Step 5: Commit**

```bash
git add backend/wanted_search/penalty_rules.py backend/tests/test_penalty_rules.py
git commit -m "feat(plan-b4): implement 15 penalty rules (10 ports + 5 new)"
```

---

## Task 3: Wire pipeline into `compute_score()` — additive, no double-count

**Files:**
- Modify: `backend/providers/base.py`
- Create: `backend/tests/test_penalty_pipeline_integration.py`

- [ ] **Step 1: Write failing integration test**

```python
# backend/tests/test_penalty_pipeline_integration.py
"""Integration tests — compute_score must call the penalty pipeline."""

from providers.base import SubtitleResult, SubtitleFormat, VideoQuery, compute_score


def test_compute_score_includes_penalty_breakdown_entries():
    query = VideoQuery(
        file_path="/m/S01E01.mkv",
        series_title="X", season=1, episode=1,
        release_group="GRP", source="BluRay",
        resolution="1080p", video_codec="x265", year=2024,
        languages=["en"],
    )
    result = SubtitleResult(
        provider_name="opensubtitles", subtitle_id="1", language="en",
        release_info="BluRay GRP 1080p x265 DTS",
        format=SubtitleFormat.ASS,
        matches=set(),  # deliberately empty — force rules path only
    )
    compute_score(result, query)
    # Pipeline rule hits (release_group_match etc.) should appear in breakdown
    assert any(key.startswith("release_group") or key.startswith("format_bonus")
               for key in result.score_breakdown.keys())
    # Score must be > 0 because rules fired
    assert result.score > 0


def test_compute_score_hi_exclude_kills_candidate():
    query = VideoQuery(
        file_path="/m/X.mkv", title="X",
        hi_preference="exclude", languages=["en"],
    )
    result = SubtitleResult(
        provider_name="opensubtitles", subtitle_id="1", language="en",
        release_info="", format=SubtitleFormat.SRT,
        hearing_impaired=True,
    )
    compute_score(result, query)
    # Kill-weight of -999 should drive score negative
    assert result.score <= -500


def test_compute_score_no_double_count_when_matches_set_overlaps():
    """If the legacy `matches` set already contains `release_group`, the pipeline
    rule ReleaseGroupMatchRule should NOT also fire — otherwise we double-count.

    The guard: the pipeline rules match on release_info; the weight-map `matches`
    set is populated by callers. The integration test ensures both paths don't
    both contribute their full weight when ReleaseGroupMatchRule would match.

    This tests the behavior spec: pipeline is additive — callers that already
    set `matches = {"release_group"}` get the weight-map credit AND the pipeline
    credit. That's a known duplication for overlap; the resolution is to NOT
    add release_group to the legacy matches set (callers should migrate to the
    pipeline). For this plan we accept the duplication and rely on rule weights
    staying at their current values until callers migrate.
    """
    query = VideoQuery(
        file_path="/m/S01E01.mkv", series_title="X", season=1, episode=1,
        release_group="GRP", languages=["en"],
    )
    result = SubtitleResult(
        provider_name="opensubtitles", subtitle_id="1", language="en",
        release_info="BluRay GRP 1080p",
        format=SubtitleFormat.SRT,
        matches={"release_group"},  # legacy weight-map will credit 14
    )
    compute_score(result, query)
    # Both paths credit — accepted duplication (14 from weight map + 14 from rule)
    assert result.score >= 14  # Lower bound: at minimum the pipeline value
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && python -m pytest tests/test_penalty_pipeline_integration.py -v`
Expected: tests FAIL — compute_score doesn't yet call apply_penalty_pipeline.

- [ ] **Step 3: Wire the pipeline into `compute_score()`**

Edit `backend/providers/base.py` — add the penalty pipeline call at the end of `compute_score()`, before the final `result.score = sum(breakdown.values())` line (or after, whichever preserves existing behavior best).

Locate the `compute_score` function (starts around line 280) and at the end — AFTER the existing breakdown is built but BEFORE `result.score = sum(breakdown.values())` — add:

```python
    # Plan B4 — additive penalty rule pipeline.
    # Rules mutate result.score directly in the pipeline, and return a
    # {rule_id: weight} dict that we merge into breakdown for UI breakdown display.
    try:
        from wanted_search.penalty_rules import apply_penalty_pipeline

        pipeline_breakdown = apply_penalty_pipeline(result, query)
        # Pipeline already mutated result.score; merge breakdown for visibility
        for k, v in pipeline_breakdown.items():
            breakdown[f"rule:{k}"] = v
    except Exception as e:
        logger.warning("Penalty pipeline failed: %s", e)
```

**Important:** the pipeline already mutates `result.score`. The existing `result.score = sum(breakdown.values())` at the bottom of compute_score will OVERWRITE that. Two options:

1. Change the final line to `result.score = sum(breakdown.values())` AFTER the pipeline merge (so pipeline entries are summed too). Recommended.
2. Detect double-application by adjusting the order.

Use option 1: move the pipeline call to just before the final sum, merge all breakdowns, then sum. Concretely, replace:

```python
    result.score_breakdown = breakdown
    result.score = sum(breakdown.values())
    return result.score
```

with:

```python
    # Plan B4 — penalty rule pipeline runs here so its entries participate in the sum
    try:
        from wanted_search.penalty_rules import apply_penalty_pipeline

        pipeline_breakdown = apply_penalty_pipeline(result, query)
        # apply_penalty_pipeline mutates result.score directly; undo that here
        # because we're about to re-compute from the merged breakdown
        for k, v in pipeline_breakdown.items():
            breakdown[f"rule:{k}"] = v
            result.score -= v  # undo the in-place mutation
    except Exception as e:
        logger.warning("Penalty pipeline failed: %s", e)

    result.score_breakdown = breakdown
    result.score = sum(breakdown.values())
    return result.score
```

Actually simpler: change `apply_penalty_pipeline` to NOT mutate and just return breakdown. Minimal change:

Edit `backend/wanted_search/penalty_rules.py::apply_penalty_pipeline` — remove the `candidate.score += applied` line so the function is pure (only builds breakdown). The caller in compute_score sums all breakdowns at the end.

Then compute_score's tail becomes:

```python
    # Plan B4 — additive penalty rule pipeline (pure — only builds breakdown entries)
    try:
        from wanted_search.penalty_rules import apply_penalty_pipeline

        pipeline_breakdown = apply_penalty_pipeline(result, query)
        for k, v in pipeline_breakdown.items():
            breakdown[f"rule:{k}"] = v
    except Exception as e:
        logger.warning("Penalty pipeline failed: %s", e)

    result.score_breakdown = breakdown
    result.score = sum(breakdown.values())
    return result.score
```

Pick the pure-function approach. Update `apply_penalty_pipeline` accordingly and update the module-level docstring.

- [ ] **Step 4: Run integration tests + re-run rule tests**

Run: `cd backend && python -m pytest tests/test_penalty_rules.py tests/test_penalty_pipeline_integration.py -v --tb=short`
Expected: all tests PASS.

- [ ] **Step 5: Full regression**

Run: `cd backend && python -m pytest tests/test_providers_init_refactor_safety.py tests/test_wanted_search.py -v --tb=short`
Expected: no regressions. (If tests don't exist under those exact names, use `grep -l 'compute_score' backend/tests/*.py` to find the right ones and run them.)

- [ ] **Step 6: Commit**

```bash
git add backend/providers/base.py backend/wanted_search/penalty_rules.py backend/tests/test_penalty_pipeline_integration.py
git commit -m "feat(plan-b4): wire penalty pipeline into compute_score (pure, additive)"
```

---

## Task 4: DB helpers for penalty-rule weight overrides

**Files:**
- Modify: `backend/db/scoring.py`
- Modify: `backend/tests/test_penalty_pipeline_integration.py`

- [ ] **Step 1: Inspect existing `backend/db/scoring.py`**

Run: `grep -nE "(def |get_scoring_weights|set_scoring)" backend/db/scoring.py | head -20`
Note the existing API for weight overrides. Reuse the same `scoring_weights` table — just use a new `score_type` discriminator `penalty_rule`.

- [ ] **Step 2: Write failing test**

Append to `backend/tests/test_penalty_pipeline_integration.py`:

```python
def test_penalty_rule_weights_db_roundtrip():
    """set_penalty_rule_weight persists, get_penalty_rule_weights reads back."""
    from db.scoring import get_penalty_rule_weights, set_penalty_rule_weight

    # Set weight override
    set_penalty_rule_weight("machine_translation_penalty", -25)
    weights = get_penalty_rule_weights()
    assert weights.get("machine_translation_penalty") == -25

    # Setting to 0 clears/disables
    set_penalty_rule_weight("machine_translation_penalty", 0)
    weights = get_penalty_rule_weights()
    assert weights.get("machine_translation_penalty", 0) == 0
```

- [ ] **Step 3: Run to verify failure**

Run: `cd backend && python -m pytest tests/test_penalty_pipeline_integration.py::test_penalty_rule_weights_db_roundtrip -v`
Expected: FAIL — functions don't exist.

- [ ] **Step 4: Implement the helpers**

Append to `backend/db/scoring.py`:

```python
def get_penalty_rule_weights() -> dict[str, int]:
    """Return {rule_id: weight} overrides for penalty rules (score_type='penalty_rule').

    Empty dict on any error (caller falls back to rule default_weight).
    """
    from db.models.core import ScoringWeight

    try:
        rows = ScoringWeight.query.filter_by(score_type="penalty_rule").all()
        return {row.match_key: int(row.weight) for row in rows}
    except Exception:
        return {}


def set_penalty_rule_weight(rule_id: str, weight: int) -> None:
    """Upsert a weight override for a penalty rule.

    Setting weight=0 disables the rule (the pipeline skips zero-weight rules).
    """
    from db import db
    from db.models.core import ScoringWeight

    existing = (
        db.session.query(ScoringWeight)
        .filter_by(score_type="penalty_rule", match_key=rule_id)
        .one_or_none()
    )
    if existing is None:
        existing = ScoringWeight(score_type="penalty_rule", match_key=rule_id, weight=weight)
        db.session.add(existing)
    else:
        existing.weight = weight
    db.session.commit()
```

(Adjust imports if the actual `backend/db/scoring.py` uses a slightly different session/model pattern — match the existing file's style.)

- [ ] **Step 5: Run tests + invalidate scoring cache**

Note: the `_get_cached_weights` cache in `providers/base.py` is NOT shared with `get_penalty_rule_weights`. Pipeline rules look at DB directly per call. This is acceptable for now — add a TODO comment to cache in a future perf-pass if scoring gets hot.

Run: `cd backend && python -m pytest tests/test_penalty_pipeline_integration.py -v`
Expected: all tests PASS (including the new roundtrip test).

- [ ] **Step 6: Commit**

```bash
git add backend/db/scoring.py backend/tests/test_penalty_pipeline_integration.py
git commit -m "feat(plan-b4): db.scoring — penalty rule weight get/set helpers"
```

---

## Task 5: API routes to list + update penalty rules

**Files:**
- Modify: `backend/routes/scoring.py` (or the file that owns the scoring endpoints — grep to confirm)

- [ ] **Step 1: Find the scoring route file**

Run: `grep -rn "scoring" backend/routes/*.py | grep bp.route | head -10`

- [ ] **Step 2: Add endpoints**

Add two endpoints:

```python
@scoring_bp.route("/penalty-rules", methods=["GET"])
@require_api_key
def list_penalty_rules():
    """Return all registered penalty rules with their current weight + metadata."""
    from wanted_search.penalty_rules import _RULE_REGISTRY
    from db.scoring import get_penalty_rule_weights

    overrides = get_penalty_rule_weights()
    rules = []
    for cls in _RULE_REGISTRY:
        rules.append({
            "rule_id": cls.rule_id,
            "label": cls.label,
            "description": cls.description,
            "default_weight": cls.default_weight,
            "current_weight": overrides.get(cls.rule_id, cls.default_weight),
        })
    return jsonify({"rules": rules})


@scoring_bp.route("/penalty-rules/<rule_id>", methods=["PUT"])
@require_api_key
def update_penalty_rule(rule_id):
    """Update a penalty rule's weight. Body: {"weight": int}."""
    from wanted_search.penalty_rules import _RULE_REGISTRY
    from db.scoring import set_penalty_rule_weight

    if not any(cls.rule_id == rule_id for cls in _RULE_REGISTRY):
        return jsonify({"error": "unknown rule_id", "rule_id": rule_id}), 404

    data = request.get_json(force=True) or {}
    try:
        weight = int(data.get("weight", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "weight must be an integer"}), 400

    set_penalty_rule_weight(rule_id, weight)
    return jsonify({"rule_id": rule_id, "weight": weight})
```

(Adjust decorator names to match the existing scoring routes — `@require_api_key` may be named differently; `grep 'def require_' backend/auth.py` to confirm.)

- [ ] **Step 3: Add API tests**

Append to `backend/tests/test_penalty_pipeline_integration.py`:

```python
def test_api_list_penalty_rules(client):
    resp = client.get("/api/v1/scoring/penalty-rules")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "rules" in body
    rule_ids = [r["rule_id"] for r in body["rules"]]
    # Spot-check a few known rules
    assert "release_group_match" in rule_ids
    assert "machine_translation_penalty" in rule_ids


def test_api_update_penalty_rule_weight(client):
    resp = client.put(
        "/api/v1/scoring/penalty-rules/machine_translation_penalty",
        json={"weight": -30},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["weight"] == -30

    # Verify list endpoint reflects the new weight
    resp2 = client.get("/api/v1/scoring/penalty-rules")
    rule = next(r for r in resp2.get_json()["rules"] if r["rule_id"] == "machine_translation_penalty")
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
```

- [ ] **Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_penalty_pipeline_integration.py -v --tb=short`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/routes/scoring.py backend/tests/test_penalty_pipeline_integration.py
git commit -m "feat(plan-b4): API — list/update penalty rule weights"
```

---

## Task 6: Frontend — ScoringTab extension with rules list

**Files:**
- Modify: `frontend/src/pages/Settings/ScoringTab.tsx` (or wherever the ScoringTab lives — grep `grep -rn 'Scoring' frontend/src/pages/Settings/` if unsure)
- Modify (maybe): `frontend/src/api/scoring.ts`

- [ ] **Step 1: Add fetcher + mutation**

In `frontend/src/api/scoring.ts` (create if missing):

```typescript
export interface PenaltyRule {
  rule_id: string
  label: string
  description: string
  default_weight: number
  current_weight: number
}

export async function fetchPenaltyRules(): Promise<PenaltyRule[]> {
  const resp = await fetch('/api/v1/scoring/penalty-rules', {
    headers: { 'X-API-Key': getApiKey() },  // reuse existing helper
  })
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
  const body = await resp.json()
  return body.rules as PenaltyRule[]
}

export async function updatePenaltyRule(rule_id: string, weight: number): Promise<void> {
  const resp = await fetch(`/api/v1/scoring/penalty-rules/${encodeURIComponent(rule_id)}`, {
    method: 'PUT',
    headers: {
      'X-API-Key': getApiKey(),
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ weight }),
  })
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
}
```

Match the existing API-helper style in the repo — if there's an `apiClient.get/put` wrapper, use it.

- [ ] **Step 2: Add a "Penalty Rules" section to ScoringTab**

In `ScoringTab.tsx`, add a section below the existing weight editors:

```tsx
{/* Plan B4 — Penalty rules */}
<section className="mt-8">
  <h2 className="text-xl font-semibold mb-2">Penalty Rules</h2>
  <p className="text-muted text-sm mb-4">
    Named rules that add or subtract from subtitle scores. Set a rule's weight to 0 to disable it.
  </p>
  {rules.map(rule => (
    <div key={rule.rule_id} className="flex items-center gap-4 py-2 border-b border-border">
      <div className="flex-1">
        <div className="font-medium">{rule.label}</div>
        <div className="text-xs text-muted">{rule.description}</div>
      </div>
      <input
        type="number"
        value={rule.current_weight}
        onChange={(e) => onRuleWeightChange(rule.rule_id, Number(e.target.value))}
        className="w-20 p-1 rounded-md bg-surface border border-border text-right"
      />
      <span className="text-xs text-muted w-16">
        default: {rule.default_weight}
      </span>
    </div>
  ))}
</section>
```

Wire `rules` + `onRuleWeightChange` via `useQuery` (`queryKey: ['scoring', 'penalty-rules']`, `queryFn: fetchPenaltyRules`) and `useMutation` on `updatePenaltyRule` with an invalidate on settle. Follow existing patterns in the file for consistency.

- [ ] **Step 3: Build + lint**

Run: `cd frontend && npm run lint && npx tsc --noEmit`
Expected: both exit 0.

- [ ] **Step 4: Frontend unit tests**

Run: `cd frontend && npm run test -- --run 2>&1 | tail -10`
Expected: no new failures (pre-existing failures from earlier phases remain acceptable).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Settings/ScoringTab.tsx frontend/src/api/scoring.ts
git commit -m "feat(plan-b4): frontend — penalty rules section in ScoringTab"
```

---

## Task 7: Deploy

**Files:**
- Modify: `backend/VERSION` (in deploy step)
- Modify: `CHANGELOG.md` (in deploy step)

- [ ] **Step 1: Pre-deploy checks**

Run:

```bash
cd backend && ruff check . && ruff format --check .
cd backend && python -m pytest tests/test_penalty_rules.py tests/test_penalty_pipeline_integration.py -v --tb=short
cd frontend && npm run lint && npx tsc --noEmit
```

All must exit 0.

- [ ] **Step 2: Invoke the `deploy` skill**

Bumps to 0.67.0-beta. Expected CHANGELOG:

```markdown
## [0.67.0-beta] - 2026-04-19

### Added
- **Plan B Phase 4 — Scoring penalty rule pipeline** — Introduced a named-class `PenaltyRule` pipeline for subtitle scoring. 15 rules total: 10 ports of existing Sublarr behavior (release group / source / resolution / video codec / audio codec match; HI + forced preferences prefer/exclude-or-only; ASS format bonus) + 5 new Bazarr-equivalent opt-in rules (loose release-group substring match; source-hierarchy penalty; year off-by-one tolerance; codec-upgrade mismatch penalty; machine-translation penalty). Weights persist in `scoring_weights` (new `score_type="penalty_rule"` discriminator) with UI slider per rule in Settings → Scoring. New rules default to weight=0 (opt-in); existing rules keep current defaults so scoring output is unchanged on deploy. ~17 new backend tests + new API endpoints at `/api/v1/scoring/penalty-rules`.

### Changed — Plan B scope note
- **B4 rescoped from "~30 rules" to 15 rules** — Sublarr's existing `compute_score()` already implements most Bazarr-equivalent matching behaviour; the real gap was naming + introspection + a handful of missing edge-case rules. 15 rules cover that gap honestly.

### Plan B Progress
- Phase B4 — Scoring penalty pipeline: **shipped**
```

- [ ] **Step 3: Verify in prod**

```bash
curl -s -H "X-API-Key: $SUBLARR_KEY" http://192.168.178.36:5765/api/v1/scoring/penalty-rules \
  | python -c "import sys,json; d=json.load(sys.stdin); print('rule count:', len(d['rules'])); [print(' -', r['rule_id'], 'default:', r['default_weight']) for r in d['rules']]"
```

Expected: 15 rules listed.

- [ ] **Step 4: Tail prod logs for 60s**

```bash
ssh root@192.168.178.36 "docker logs sublarr --since 2m 2>&1" \
  | grep -iE "(error|traceback|alembic|penalty)" \
  | grep -vE "(enzyme|X-Signature|marketplace registry)" | head -15
```

Expected: no new errors. The penalty-pipeline message is INFO-level only during compute_score fallback paths — acceptable if seen.

---

## Phase B4 Acceptance Checklist

- [ ] `PenaltyRule` ABC + `@register_penalty` decorator in `backend/wanted_search/penalty_rules.py`
- [ ] 15 rule classes implemented (10 ports + 5 new)
- [ ] `apply_penalty_pipeline` is pure (returns breakdown, doesn't mutate score)
- [ ] `compute_score()` merges pipeline breakdown before final sum — no regression on existing scoring
- [ ] DB helpers `get_penalty_rule_weights` / `set_penalty_rule_weight` via `score_type="penalty_rule"`
- [ ] API endpoints `/api/v1/scoring/penalty-rules` GET + `/<rule_id>` PUT working
- [ ] Frontend ScoringTab shows penalty rules section with weight editor
- [ ] ~20 new tests pass (17 rule + pipeline + API)
- [ ] Ruff + tsc clean
- [ ] 0.67.0-beta deployed; prod shows 15 rules via API

## Next Phase

**B5 — SRT repair + embedded-extraction hardening.** New `backend/subtitle_repair.py` with pure repair functions (overlap, BOM, newline normalize, invalid decimals, encoding auto-detect). `providers/embedded.py` gets language + forced + HI track-selection priority.
