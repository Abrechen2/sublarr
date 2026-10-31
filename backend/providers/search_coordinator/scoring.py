"""Post-search scoring / classification / filtering / sorting pipeline.

Extracted from providers/search_coordinator.py. Pure mixin: used by
``SearchCoordinatorMixin``.
"""

import json
import logging
import math

import decision_log
from config_language_data import normalize_language_code
from providers.base import SubtitleFormat, compute_score
from providers.episode_gate import apply_episode_gate

logger = logging.getLogger(__name__)


#: A minimum score above any score a result can reach is a typo, not a choice.
MAX_MIN_SCORE = 10_000


def is_valid_min_score(value) -> bool:
    """A finite number between 0 and MAX_MIN_SCORE (``1e309`` is JSON for infinity, #65).

    The range is checked before anything converts to float: ``math.isfinite``
    on a 401-digit integer raised OverflowError (HTTP 500 on PUT and import).
    """
    if isinstance(value, bool) or not isinstance(value, int | float):
        return False
    if isinstance(value, float) and not math.isfinite(value):
        return False
    return 0 <= value <= MAX_MIN_SCORE


def per_language_min_scores(settings) -> dict[str, int]:
    """``score_threshold_per_language`` as ``{canonical language: score}``.

    A malformed value never breaks a search: it is ignored with a warning.
    """
    raw = getattr(settings, "score_threshold_per_language", "") if settings else ""
    if not isinstance(raw, str) or not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except ValueError:
        logger.warning("score_threshold_per_language is not JSON; ignoring it")
        return {}
    if not isinstance(parsed, dict):
        return {}
    out: dict[str, int] = {}
    for lang, score in parsed.items():
        if not is_valid_min_score(score):
            continue
        code = normalize_language_code(str(lang))
        if code:
            out[code] = int(score)
    return out


def _rejected(before: list, after: list) -> list:
    """Return the results dropped between two pipeline stages (identity diff)."""
    kept = {id(r) for r in after}
    return [r for r in before if id(r) not in kept]


class SearchScoringMixin:
    """Mixin providing the post-search result finalisation pipeline."""

    def _finalise_search_results(
        self,
        all_results: list,
        query,
        format_filter,
        min_score: int,
        must_contain,
        must_not_contain,
    ) -> list:
        """Post-search scoring / classification / filtering / sorting pipeline.

        Runs in strict order: compute_score → wrong-episode gate → forced classification →
        forced_only filter → language/format/min_score gates → blacklist →
        must_contain / must_not_contain → release-group exclude/prefer →
        final sort (ASS first, then score desc). Returns the filtered +
        sorted list.

        Every gate reports its rejections to the decision log (no-op when
        no log is active) so users can see why candidates were discarded.
        """
        # Score all results (noop for anything that was already scored)
        for result in all_results:
            if result.score == 0:
                compute_score(result, query)

        # A result naming another season/episode is another episode, whatever
        # it scores (Clevatess S02E12 <- S01E12). Runs for every provider,
        # hub bundles included.
        all_results, wrong_episode = apply_episode_gate(all_results, query)
        if wrong_episode:
            decision_log.filter_stage(
                "wrong_episode",
                len(wrong_episode),
                len(all_results),
                [r for r, _ in wrong_episode],
                wanted=f"S{query.season:02d}E{query.episode:02d}",
                reasons=[
                    reason for _, reason in wrong_episode[: decision_log.MAX_REJECTED_SAMPLES]
                ],
            )

        # Post-search forced classification: use forced_detection to classify
        # results from providers without native forced support (e.g., AnimeTosho,
        # Jimaku, SubDL). Single-pass: search once, classify results.
        from forced_detection import classify_forced_result

        for result in all_results:
            if not result.forced:
                forced_type = classify_forced_result(
                    result.filename,
                    result.provider_data if hasattr(result, "provider_data") else None,
                )
                if forced_type in ("forced", "signs"):
                    result.forced = True

        # Post-filter: if query requests forced_only, remove non-forced results
        if query.forced_only:
            before = all_results
            all_results = [r for r in all_results if r.forced]
            decision_log.filter_stage(
                "forced_only",
                len(before) - len(all_results),
                len(all_results),
                _rejected(before, all_results),
            )

        # Filter by language (if query specifies languages)
        if query.languages:
            before = all_results
            all_results = [r for r in all_results if r.language in query.languages]
            decision_log.filter_stage(
                "language",
                len(before) - len(all_results),
                len(all_results),
                _rejected(before, all_results),
                wanted=list(query.languages),
            )

        # Filter by format — include UNKNOWN since some providers omit format metadata
        if format_filter:
            before = all_results
            all_results = [
                r
                for r in all_results
                if r.format == format_filter or r.format == SubtitleFormat.UNKNOWN
            ]
            decision_log.filter_stage(
                "format",
                len(before) - len(all_results),
                len(all_results),
                _rejected(before, all_results),
                wanted=format_filter.value,
            )

        # Filter by min score — per language where Settings → Scoring sets one
        # (#61 A16: score_threshold_per_language was saved and never read).
        # The running settings, not the manager's copy from its creation: a
        # saved threshold must apply without rebuilding the manager (#64).
        from config import get_settings

        per_language = per_language_min_scores(get_settings())
        if min_score > 0 or per_language:
            before = all_results
            all_results = [
                r
                for r in all_results
                if r.score >= per_language.get(normalize_language_code(r.language), min_score)
            ]
            decision_log.filter_stage(
                "min_score",
                len(before) - len(all_results),
                len(all_results),
                _rejected(before, all_results),
                threshold=min_score,
            )

        # Filter blacklisted subtitles
        before = all_results
        all_results = [r for r in all_results if not _blacklisted(r, query)]
        decision_log.filter_stage(
            "blacklist",
            len(before) - len(all_results),
            len(all_results),
            _rejected(before, all_results),
        )

        # mustContain / mustNotContain filtering (language profile)
        if must_contain:
            from wanted_search.profile_filters import apply_must_contain

            before = all_results
            all_results = apply_must_contain(all_results, must_contain)
            decision_log.filter_stage(
                "profile_must_contain",
                len(before) - len(all_results),
                len(all_results),
                _rejected(before, all_results),
                rule=list(must_contain),
            )
        if must_not_contain:
            from wanted_search.profile_filters import apply_must_not_contain

            before = all_results
            all_results = apply_must_not_contain(all_results, must_not_contain)
            decision_log.filter_stage(
                "profile_must_not_contain",
                len(before) - len(all_results),
                len(all_results),
                _rejected(before, all_results),
                rule=list(must_not_contain),
            )

        # Release group filtering: exclude blocked groups, boost preferred groups
        from config import get_settings

        settings = get_settings()
        _exclude = [
            g.strip().lower() for g in settings.release_group_exclude.split(",") if g.strip()
        ]
        _prefer = [g.strip().lower() for g in settings.release_group_prefer.split(",") if g.strip()]

        if _exclude:
            before_list = all_results
            before = len(all_results)
            all_results = [
                r for r in all_results if not any(g in r.release_info.lower() for g in _exclude)
            ]
            filtered = before - len(all_results)
            if filtered:
                logger.debug(
                    "Release group filter: excluded %d result(s) matching %s", filtered, _exclude
                )
            decision_log.filter_stage(
                "release_group_exclude",
                filtered,
                len(all_results),
                _rejected(before_list, all_results),
                rule=_exclude,
            )

        if _prefer:
            bonus = settings.release_group_prefer_bonus
            for r in all_results:
                if any(g in r.release_info.lower() for g in _prefer):
                    r.score += bonus
                    r.matches.add("release_group_prefer")
                    # Keep the breakdown in sync so the "why this score?"
                    # tooltip accounts for every point of the final score.
                    r.score_breakdown["release_group_prefer"] = bonus

        # Sort by format preference (ASS first), then by score descending
        all_results.sort(
            key=lambda r: (
                0 if r.format == SubtitleFormat.ASS else 1,  # ASS first
                -r.score,  # Then by score descending
            )
        )

        return all_results


def _blacklisted(result, query) -> bool:
    """Blacklisted for this query's video (suspect entries are per video)."""
    from services.suspect_sidecars import blocks_result_for

    return blocks_result_for(result.provider_name, result.subtitle_id, query.file_path)
