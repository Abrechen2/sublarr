"""Named-class penalty rule pipeline for subtitle scoring.

Each rule is a named class with:
- ``rule_id``: stable string identifier (used as DB key for weight override)
- ``default_weight``: int, signed (negative for penalties, positive for bonuses)
- ``label``: short UI label
- ``description``: longer UI description
- ``applies(candidate, query) -> bool``: predicate
- ``weight(candidate, query) -> int``: applied weight when ``applies()`` is True

Weights are resolved from the ``scoring_weights`` table (see ``db.scoring``)
with ``score_type="penalty_rule"`` and ``weight_key=rule_id``. Rule
``default_weight`` is the fallback when no DB override exists.

Rules are registered via the ``@register_penalty`` decorator and
auto-discovered at import time.

The driver :func:`apply_penalty_pipeline` is pure: it returns a
``{rule_id: applied_weight}`` breakdown dict without mutating the
candidate's score. Callers (``providers.base.compute_score``) merge the
returned entries into the overall breakdown and recompute the sum.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from providers.base import SubtitleResult, VideoQuery

logger = logging.getLogger(__name__)


_RULE_REGISTRY: list[type[PenaltyRule]] = []


# Plan B4 follow-up — TTL cache for penalty-rule weight overrides.
# Scoring runs on every provider result; reading ``scoring_weights`` per call
# hits the DB hard on large searches. Matches the 60 s TTL pattern used by
# ``providers.base._get_cached_weights``; ``invalidate_penalty_rule_weights_cache()``
# is called from the scoring config-updated hook.
_RULE_WEIGHTS_CACHE_TTL = 60  # seconds
_rule_weights_cache: dict = {"data": None, "expires": 0.0}
_rule_weights_cache_lock = threading.Lock()


def _get_cached_rule_weights() -> dict[str, int]:
    """Return the current ``{rule_id: weight}`` overrides with 60 s TTL caching.

    Falls back to an empty dict on any DB error so the pipeline stays on its
    ``default_weight`` path.
    """
    with _rule_weights_cache_lock:
        now = time.time()
        cached = _rule_weights_cache["data"]
        if cached is not None and now < _rule_weights_cache["expires"]:
            return cached

        try:
            from db.scoring import get_penalty_rule_weights

            weights = get_penalty_rule_weights()
        except Exception:
            weights = {}

        _rule_weights_cache["data"] = weights
        _rule_weights_cache["expires"] = now + _RULE_WEIGHTS_CACHE_TTL
        return weights


def invalidate_penalty_rule_weights_cache() -> None:
    """Clear the cache so the next pipeline call reloads from the DB.

    Called after ``set_penalty_rule_weight`` so operators see their changes
    immediately instead of waiting up to 60 s.
    """
    with _rule_weights_cache_lock:
        _rule_weights_cache["data"] = None
        _rule_weights_cache["expires"] = 0.0


class PenaltyRule(ABC):
    """Base class for named penalty/bonus rules applied to subtitle scoring."""

    rule_id: ClassVar[str] = ""
    default_weight: ClassVar[int] = 0
    label: ClassVar[str] = ""
    description: ClassVar[str] = ""

    @abstractmethod
    def applies(self, candidate: SubtitleResult, query: VideoQuery) -> bool:
        """Return True if this rule should apply to the candidate."""

    @abstractmethod
    def weight(self, candidate: SubtitleResult, query: VideoQuery) -> int:
        """Return the signed weight to add to the candidate's score.

        Most rules return ``self.default_weight``; dynamic rules can scale
        the weight by context.
        """


def register_penalty(cls: type[PenaltyRule]) -> type[PenaltyRule]:
    """Decorator to register a ``PenaltyRule`` subclass in the module registry."""
    if not cls.rule_id:
        raise ValueError(f"PenaltyRule {cls.__name__} must define rule_id")
    if cls in _RULE_REGISTRY:
        return cls
    _RULE_REGISTRY.append(cls)
    return cls


# Plan B4 follow-up — when a pipeline rule fires with a non-zero weight we
# skip the matching legacy weight-map credit so callers that still populate
# ``SubtitleResult.matches`` don't double-count. Map: rule_id → weight-map
# keys the rule supersedes. Rules without an entry have no legacy equivalent.
_RULE_SUPERSEDES: dict[str, tuple[str, ...]] = {
    "release_group_match": ("release_group",),
    "source_match": ("source",),
    "audio_codec_match": ("audio_codec",),
    "resolution_match": ("resolution",),
    "video_codec_match": ("video_codec",),
    "format_bonus_ass": ("format_bonus",),
    "hi_preference_prefer": ("hi_preference",),
    "hi_preference_exclude_or_only": ("hi_preference",),
    "forced_preference_prefer": ("forced_preference",),
    "forced_preference_exclude_or_only": ("forced_preference",),
}


# Custom regex rules — user-defined Sonarr-style release-profile conditions
# stored in the ``custom_scoring_rules`` table. Compiled patterns are cached
# with the same 60 s TTL as rule-weight overrides; the CRUD routes call
# ``invalidate_custom_rules_cache()`` so edits apply immediately.
#
# Matching input is capped to bound worst-case regex backtracking on
# adversarial provider strings.
_CUSTOM_RULES_CACHE_TTL = 60  # seconds
_MAX_MATCH_INPUT_LEN = 300
_custom_rules_cache: dict = {"data": None, "expires": 0.0}
_custom_rules_cache_lock = threading.Lock()


def _get_cached_custom_rules() -> list[tuple[int, re.Pattern, int]]:
    """Return enabled custom rules as ``[(id, compiled_pattern, weight)]``.

    Falls back to an empty list on any DB error; rules whose pattern no
    longer compiles (edited DB row, downgrade artifacts) are skipped.
    """
    with _custom_rules_cache_lock:
        now = time.time()
        cached = _custom_rules_cache["data"]
        if cached is not None and now < _custom_rules_cache["expires"]:
            return cached

        compiled: list[tuple[int, re.Pattern, int]] = []
        try:
            from db.repositories.custom_rules import CustomScoringRuleRepository

            for rule in CustomScoringRuleRepository().list_rules(enabled_only=True):
                try:
                    compiled.append(
                        (rule["id"], re.compile(rule["pattern"], re.IGNORECASE), rule["weight"])
                    )
                except re.error:
                    logger.warning(
                        "Custom scoring rule %d has invalid pattern; skipped", rule["id"]
                    )
        except Exception:
            logger.debug("Custom rule load failed", exc_info=True)

        _custom_rules_cache["data"] = compiled
        _custom_rules_cache["expires"] = now + _CUSTOM_RULES_CACHE_TTL
        return compiled


def invalidate_custom_rules_cache() -> None:
    """Clear the custom-rule cache so the next pipeline call reloads from the DB."""
    with _custom_rules_cache_lock:
        _custom_rules_cache["data"] = None
        _custom_rules_cache["expires"] = 0.0


def apply_custom_regex_rules(candidate: SubtitleResult, query: VideoQuery) -> dict[str, int]:
    """Apply user-defined regex rules to the candidate's release_info.

    Returns ``{"custom_<id>": weight}`` entries for every matching enabled
    rule. Pure function — does not mutate the candidate.
    """
    breakdown: dict[str, int] = {}
    info = (candidate.release_info or "")[:_MAX_MATCH_INPUT_LEN]
    if not info:
        return breakdown
    for rule_id, pattern, weight in _get_cached_custom_rules():
        try:
            if weight != 0 and pattern.search(info):
                breakdown[f"custom_{rule_id}"] = int(weight)
        except Exception as e:
            logger.warning("Custom scoring rule %d raised: %s", rule_id, e)
    return breakdown


def apply_penalty_pipeline(
    candidate: SubtitleResult,
    query: VideoQuery,
) -> dict[str, int]:
    """Run all registered penalty rules against the candidate.

    Pure function: returns a dict of ``{rule_id: applied_weight}`` suitable
    for merging into the caller's breakdown map. Does NOT mutate
    ``candidate.score``.

    For each rule:
    1. If ``rule.applies(candidate, query)`` returns False → skip.
    2. Look up the configured weight override in ``scoring_weights``
       (``score_type="penalty_rule"``, ``weight_key=rule_id``); fall back
       to ``rule.default_weight``.
    3. If the configured weight is 0 → treat as disabled and skip.
    4. Call ``rule.weight(candidate, query)``. If the rule returned its
       own ``default_weight`` (the simple path), scale by the configured
       override; otherwise keep the dynamic value the rule computed.

    User-defined custom regex rules (``custom_scoring_rules`` table) run
    after the registry rules and contribute ``custom_<id>`` entries.
    """
    breakdown: dict[str, int] = {}

    overrides = _get_cached_rule_weights()

    for rule_cls in _RULE_REGISTRY:
        try:
            rule = rule_cls()
            if not rule.applies(candidate, query):
                continue
            configured_weight = overrides.get(rule_cls.rule_id, rule_cls.default_weight)
            if configured_weight == 0:
                continue  # User disabled this rule (or default is 0 and no override)
            applied = rule.weight(candidate, query)
            # If the rule returned its own default_weight, scale by the
            # configured override so user-edited weights take effect.
            if applied == rule_cls.default_weight and rule_cls.default_weight != 0:
                applied = configured_weight
            breakdown[rule_cls.rule_id] = int(applied)
        except Exception as e:
            logger.warning("Penalty rule %s raised: %s", rule_cls.rule_id, e)

    breakdown.update(apply_custom_regex_rules(candidate, query))

    return breakdown


def superseded_legacy_keys(pipeline_breakdown: dict[str, int]) -> set[str]:
    """Return the weight-map keys that the current pipeline breakdown covers.

    Callers (``providers.base.compute_score``) drop these keys from the legacy
    weight-map credit to avoid double-counting. Only non-zero pipeline
    contributions cause supersession — a disabled rule (weight 0) leaves the
    legacy path untouched.
    """
    superseded: set[str] = set()
    for rule_id, applied in pipeline_breakdown.items():
        if applied == 0:
            continue
        for key in _RULE_SUPERSEDES.get(rule_id, ()):
            superseded.add(key)
    return superseded


# ─── Port group — reproduce existing Sublarr scoring as named rules ──────────


@register_penalty
class ReleaseGroupMatchRule(PenaltyRule):
    rule_id = "release_group_match"
    default_weight = 14  # matches EPISODE_SCORES["release_group"]
    label = "Release Group Match"
    description = (
        "Candidate release_info contains the query release_group (case-insensitive substring)."
    )

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


_AUDIO_CODECS: tuple[str, ...] = ("dts", "ac3", "aac", "eac3", "truehd", "flac", "opus")


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
    description = "Candidate format is ASS or SSA (Sublarr prefers styled subs)."

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
        return getattr(query, "hi_preference", "include") == "prefer" and candidate.hearing_impaired

    def weight(self, candidate, query) -> int:
        return self.default_weight


@register_penalty
class HiPreferenceExcludeOrOnlyRule(PenaltyRule):
    rule_id = "hi_preference_exclude_or_only"
    default_weight = -999
    label = "HI Preference — Exclude / Only Kill"
    description = (
        "Query says exclude-HI and candidate is HI, or says only-HI and candidate isn't. "
        "Kills the candidate."
    )

    def applies(self, candidate, query) -> bool:
        pref = getattr(query, "hi_preference", "include")
        if pref == "exclude" and candidate.hearing_impaired:
            return True
        if pref == "only" and not candidate.hearing_impaired:  # noqa: SIM103 - clarity
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
        return getattr(query, "forced_scoring", "include") == "prefer" and candidate.forced

    def weight(self, candidate, query) -> int:
        return self.default_weight


@register_penalty
class ForcedPreferenceExcludeOrOnlyRule(PenaltyRule):
    rule_id = "forced_preference_exclude_or_only"
    default_weight = -999
    label = "Forced Preference — Exclude / Only Kill"
    description = (
        "Query says exclude-forced and candidate is forced, or says only-forced and candidate "
        "isn't. Kills the candidate."
    )

    def applies(self, candidate, query) -> bool:
        pref = getattr(query, "forced_scoring", "include")
        if pref == "exclude" and candidate.forced:
            return True
        if pref == "only" and not candidate.forced:  # noqa: SIM103 - clarity
            return True
        return False

    def weight(self, candidate, query) -> int:
        return self.default_weight


# ─── Add group — new Bazarr-equivalent opt-in rules (default_weight=0) ───────


@register_penalty
class ReleaseGroupSubstringLooseRule(PenaltyRule):
    rule_id = "release_group_substring_loose"
    default_weight = 0  # opt-in; suggested +5 when enabled
    label = "Release Group Substring (Loose)"
    description = (
        "Release_info contains the first 3 chars of the query release_group. "
        "Catches abbreviated group names."
    )

    def applies(self, candidate, query) -> bool:
        rg = (query.release_group or "").strip().lower()
        if len(rg) < 3:
            return False
        prefix = rg[:3]
        info = (candidate.release_info or "").lower()
        # Skip if the strict match would already fire to avoid double-counting.
        if rg in info:
            return False
        return prefix in info

    def weight(self, candidate, query) -> int:
        return self.default_weight


_SOURCE_HIERARCHY: dict[str, int] = {
    "bluray": 3,
    "web-dl": 2,
    "webdl": 2,
    "webrip": 1,
    "hdtv": 0,
}


@register_penalty
class SourceHierarchyPenaltyRule(PenaltyRule):
    rule_id = "source_hierarchy_penalty"
    default_weight = 0  # opt-in; suggested -10
    label = "Source Hierarchy Penalty"
    description = (
        "Candidate source is lower-tier than the query source "
        "(WEB-DL candidate for BluRay query, etc.)."
    )

    @staticmethod
    def _tier(info_or_src: str) -> int:
        s = (info_or_src or "").lower()
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


_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")


@register_penalty
class YearOffByOneToleranceRule(PenaltyRule):
    rule_id = "year_off_by_one_tolerance"
    default_weight = 0  # opt-in; suggested +5
    label = "Year Off-By-One Tolerance"
    description = (
        "Candidate mentions a year within +/-1 of the query year "
        "(common when release-year differs from production-year)."
    )

    def applies(self, candidate, query) -> bool:
        if query.year is None:
            return False
        info = candidate.release_info or ""
        for match in _YEAR_RE.finditer(info):
            cy = int(match.group(0))
            if abs(cy - query.year) == 1:
                return True
        return False

    def weight(self, candidate, query) -> int:
        return self.default_weight


@register_penalty
class CodecUpgradePenaltyRule(PenaltyRule):
    rule_id = "codec_upgrade_penalty"
    default_weight = 0  # opt-in; suggested -3
    label = "Codec Upgrade Mismatch Penalty"
    description = (
        "Query video uses a more efficient codec than the candidate "
        "(e.g. file is x265 but candidate says x264)."
    )

    _RANK: ClassVar[dict[str, int]] = {
        "av1": 3,
        "x265": 2,
        "hevc": 2,
        "h265": 2,
        "x264": 1,
        "h264": 1,
        "avc": 1,
    }

    def _rank(self, s: str) -> int:
        s = (s or "").lower()
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
    default_weight = 0  # opt-in; suggested -50
    label = "Machine-Translation Penalty"
    description = "Candidate is flagged as machine-translated or has high MT confidence (>=80)."

    def applies(self, candidate, query) -> bool:
        if candidate.machine_translated:
            return True
        return (candidate.mt_confidence or 0.0) >= 80.0

    def weight(self, candidate, query) -> int:
        return self.default_weight
