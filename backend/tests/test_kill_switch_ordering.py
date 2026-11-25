"""An excluded candidate cannot be out-bonused (#34).

hi_preference/forced_scoring "exclude"/"only" add -999 to the breakdown. That
only excluded a candidate while no bonus reached 999 points; provider
modifiers are unbounded and user-configurable. The final score of an
excluded candidate is now capped at the kill-switch value.
"""

from unittest.mock import patch

from tests.test_hi_forced_scoring import _make_query, _make_result, reset_settings  # noqa: F401


def _score(hearing_impaired: bool, modifier: int) -> int:
    from config import reload_settings
    from providers.base import compute_score, invalidate_scoring_cache

    invalidate_scoring_cache()
    reload_settings({"hi_preference": "exclude"})
    with patch("providers.base._get_cached_modifier", return_value=modifier):
        return compute_score(_make_result(hearing_impaired=hearing_impaired), _make_query())


def test_huge_bonus_does_not_lift_an_excluded_result():
    from providers.base import KILL_SWITCH_SCORE

    assert _score(hearing_impaired=True, modifier=5000) <= KILL_SWITCH_SCORE


def test_excluded_ranks_below_any_non_excluded_candidate():
    assert _score(hearing_impaired=True, modifier=5000) < _score(hearing_impaired=False, modifier=0)


def test_non_excluded_scores_are_untouched():
    assert _score(hearing_impaired=False, modifier=5000) > 5000


def test_score_still_equals_the_breakdown_sum():
    from config import reload_settings
    from providers.base import compute_score, invalidate_scoring_cache

    invalidate_scoring_cache()
    reload_settings({"hi_preference": "exclude"})
    result = _make_result(hearing_impaired=True)
    with patch("providers.base._get_cached_modifier", return_value=5000):
        score = compute_score(result, _make_query())
    assert score == sum(result.score_breakdown.values())
