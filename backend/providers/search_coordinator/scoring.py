"""Post-search scoring / classification / filtering / sorting pipeline.

Extracted from providers/search_coordinator.py. Pure mixin: used by
``SearchCoordinatorMixin``.
"""

import logging

from providers.base import SubtitleFormat, compute_score

logger = logging.getLogger(__name__)


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

        Runs in strict order: compute_score → forced classification →
        forced_only filter → language/format/min_score gates → blacklist →
        must_contain / must_not_contain → release-group exclude/prefer →
        final sort (ASS first, then score desc). Returns the filtered +
        sorted list.
        """
        # Score all results (noop for anything that was already scored)
        for result in all_results:
            if result.score == 0:
                compute_score(result, query)

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
            all_results = [r for r in all_results if r.forced]

        # Filter by language (if query specifies languages)
        if query.languages:
            all_results = [r for r in all_results if r.language in query.languages]

        # Filter by format — include UNKNOWN since some providers omit format metadata
        if format_filter:
            all_results = [
                r
                for r in all_results
                if r.format == format_filter or r.format == SubtitleFormat.UNKNOWN
            ]

        # Filter by min score
        if min_score > 0:
            all_results = [r for r in all_results if r.score >= min_score]

        # Filter blacklisted subtitles
        from db.blacklist import is_blacklisted

        all_results = [r for r in all_results if not is_blacklisted(r.provider_name, r.subtitle_id)]

        # mustContain / mustNotContain filtering (language profile)
        if must_contain:
            from wanted_search.profile_filters import apply_must_contain

            all_results = apply_must_contain(all_results, must_contain)
        if must_not_contain:
            from wanted_search.profile_filters import apply_must_not_contain

            all_results = apply_must_not_contain(all_results, must_not_contain)

        # Release group filtering: exclude blocked groups, boost preferred groups
        from config import get_settings

        settings = get_settings()
        _exclude = [
            g.strip().lower() for g in settings.release_group_exclude.split(",") if g.strip()
        ]
        _prefer = [g.strip().lower() for g in settings.release_group_prefer.split(",") if g.strip()]

        if _exclude:
            before = len(all_results)
            all_results = [
                r for r in all_results if not any(g in r.release_info.lower() for g in _exclude)
            ]
            filtered = before - len(all_results)
            if filtered:
                logger.debug(
                    "Release group filter: excluded %d result(s) matching %s", filtered, _exclude
                )

        if _prefer:
            bonus = settings.release_group_prefer_bonus
            for r in all_results:
                if any(g in r.release_info.lower() for g in _prefer):
                    r.score += bonus
                    r.matches.add("release_group_prefer")

        # Sort by format preference (ASS first), then by score descending
        all_results.sort(
            key=lambda r: (
                0 if r.format == SubtitleFormat.ASS else 1,  # ASS first
                -r.score,  # Then by score descending
            )
        )

        return all_results
