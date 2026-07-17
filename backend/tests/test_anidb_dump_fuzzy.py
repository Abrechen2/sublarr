"""Tests for the rapidfuzz-backed Tier-4 title-dump fuzzy match + miss cache."""

from unittest.mock import patch


def _with_fake_index(index):
    import anidb_mapper

    return patch.multiple(
        anidb_mapper,
        _title_index=index,
        _title_index_loaded_at=float("inf"),  # never considered stale
    )


def test_dump_fuzzy_match_via_rapidfuzz():
    import anidb_mapper

    anidb_mapper._dump_miss_cache.clear()
    with _with_fake_index({"sousou no frieren": 17617, "one piece": 69}):
        # slight typo — must still fuzzy-match
        assert anidb_mapper.resolve_anidb_from_title_dump("Sousou no Friren") == 17617


def test_dump_no_match_is_cached():
    import anidb_mapper

    anidb_mapper._dump_miss_cache.clear()
    with _with_fake_index({"one piece": 69}):
        with patch.object(
            anidb_mapper, "_fuzzy_best_match", wraps=anidb_mapper._fuzzy_best_match
        ) as fuzzy:
            assert anidb_mapper.resolve_anidb_from_title_dump("zzz nothing alike zzz") is None
            assert anidb_mapper.resolve_anidb_from_title_dump("zzz nothing alike zzz") is None
        assert fuzzy.call_count == 1, "second miss must be served from _dump_miss_cache"


def test_dump_exact_match_still_works():
    import anidb_mapper

    anidb_mapper._dump_miss_cache.clear()
    with _with_fake_index({"one piece": 69}):
        assert anidb_mapper.resolve_anidb_from_title_dump("One Piece") == 69
