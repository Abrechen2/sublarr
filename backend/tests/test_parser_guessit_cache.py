"""guessit is pure-CPU (~155 rebulk rule evaluations per parse) and holds the
GIL. Filenames repeat every search round — parse each one once."""

from unittest.mock import patch


def test_parse_media_file_caches_guessit_calls():
    from standalone import parser

    parser._cached_guess.cache_clear()
    calls = []
    real_guessit = parser.guessit

    def counting_guessit(name, options=None):
        calls.append(name)
        return real_guessit(name, options)

    with patch.object(parser, "guessit", side_effect=counting_guessit):
        a = parser.parse_media_file("/media/[SubsPlease] Frieren - 28 (1080p).mkv")
        b = parser.parse_media_file("/media/[SubsPlease] Frieren - 28 (1080p).mkv")

    assert a == b
    assert len(calls) <= 2, f"guessit ran {len(calls)}x for one repeated filename"
    first_round = len(calls)

    with patch.object(parser, "guessit", side_effect=counting_guessit):
        parser.parse_media_file("/media/[SubsPlease] Frieren - 28 (1080p).mkv")
    assert len(calls) == first_round, "second parse_media_file call must hit the cache"


def test_cached_guess_returns_copies():
    from standalone import parser

    parser._cached_guess.cache_clear()
    one = parser._cached_guess("[SubsPlease] Frieren - 28 (1080p).mkv", True)
    one["title"] = "MUTATED"
    two = parser._cached_guess("[SubsPlease] Frieren - 28 (1080p).mkv", True)
    assert two.get("title") != "MUTATED", "cache must not hand out its internal dict"


def test_cached_guess_copies_nested_mutables():
    """Multi-episode files yield episode=[1, 2] — the nested list must not be
    shared between cache hits (shallow dict() copies would alias it)."""
    from standalone import parser

    parser._cached_guess.cache_clear()
    one = parser._cached_guess("Show.S01E01E02.1080p.mkv", False)
    ep = one.get("episode")
    if isinstance(ep, list):
        ep.append(999)
        two = parser._cached_guess("Show.S01E01E02.1080p.mkv", False)
        assert 999 not in (two.get("episode") or []), "nested list leaked from cache"
