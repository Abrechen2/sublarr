"""Regression: provider search methods must re-raise ProviderRateLimitError.

Found in prod: animetosho and 4 other providers swallowed 429s in their
outer `except Exception`, preventing the SearchCoordinator's rate-limit
handler and Phase 3's record_429 learning from ever firing.
"""

from __future__ import annotations

import pytest

from providers.base import ProviderAuthError, ProviderRateLimitError, VideoQuery

# Some providers filter by language before hitting the network (legendasdivx
# only searches Portuguese, titrari only Romanian). Pass a language that
# bypasses that short-circuit so we actually reach the ``except`` clause.
PROVIDER_MODULES = [
    # (module, class, languages)
    ("providers.animetosho", "AnimeToshoProvider", ["en", "de"]),
    ("providers.opensubtitles", "OpenSubtitlesProvider", ["en", "de"]),
    ("providers.subdl", "SubDLProvider", ["en", "de"]),
    ("providers.legendasdivx", "LegendasDivxProvider", ["pt"]),
    ("providers.titrari", "TitrariProvider", ["ro"]),
]


class _FakeSession:
    """Minimal session stand-in that always raises ProviderRateLimitError.

    Providers call ``self.session.get(...)`` (and sometimes ``post``) as their
    first network operation inside ``search``. Raising from any of these
    methods guarantees the outer ``except`` clause is exercised without
    needing to patch ``requests.Session`` globally.
    """

    def _raise(self, *_args, **_kwargs):
        raise ProviderRateLimitError("test", retry_after=60)

    get = _raise
    post = _raise
    head = _raise
    request = _raise


@pytest.mark.parametrize("mod_name,cls_name,languages", PROVIDER_MODULES)
def test_provider_reraises_rate_limit_error(monkeypatch, mod_name, cls_name, languages):
    """When a provider's first network call raises ProviderRateLimitError,
    the outer search() method must let it propagate, not swallow it.
    """
    import importlib

    mod = importlib.import_module(mod_name)
    cls = getattr(mod, cls_name)
    instance = cls.__new__(cls)  # bypass __init__ which may require config
    instance.session = _FakeSession()

    # Providers may read attributes in search() before hitting the network —
    # give them safe defaults so we reach the network call (which raises).
    import datetime as _dt

    defaults = {
        "api_key": "k",
        "username": "u",
        "password": "p",
        "tier": "free",
        "_logged_in": True,
        "_authenticated": True,
        "_search_count": 0,
        "_daily_limit": 145,
        "_last_search_date": _dt.date.today(),
        "_last_reset_date": _dt.date.today(),
        "user_agent": "Sublarr/1.0",
        "timeout": 20,
    }
    for attr, default in defaults.items():
        if not hasattr(instance, attr):
            setattr(instance, attr, default)

    # Build a query rich enough that providers don't short-circuit before
    # reaching the network call (they check for search terms / ids first).
    q = VideoQuery(
        file_path="/tmp/show.s01e01.mkv",
        languages=languages,
        forced_only=False,
        title="Test Show",
        series_title="Test Show",
        year=2024,
        season=1,
        episode=1,
        absolute_episode=1,
        imdb_id="tt1234567",
    )

    with pytest.raises(ProviderRateLimitError):
        instance.search(q)


@pytest.mark.parametrize("mod_name,cls_name,languages", PROVIDER_MODULES)
def test_provider_reraises_auth_error(monkeypatch, mod_name, cls_name, languages):
    """Mirror test: ProviderAuthError must also propagate, not be swallowed."""
    import importlib

    mod = importlib.import_module(mod_name)
    cls = getattr(mod, cls_name)
    instance = cls.__new__(cls)

    class _AuthSession:
        def _raise(self, *_a, **_k):
            raise ProviderAuthError("test")

        get = _raise
        post = _raise
        head = _raise
        request = _raise

    instance.session = _AuthSession()

    import datetime as _dt

    defaults = {
        "api_key": "k",
        "username": "u",
        "password": "p",
        "tier": "free",
        "_logged_in": True,
        "_authenticated": True,
        "_search_count": 0,
        "_daily_limit": 145,
        "_last_search_date": _dt.date.today(),
        "_last_reset_date": _dt.date.today(),
        "user_agent": "Sublarr/1.0",
        "timeout": 20,
    }
    for attr, default in defaults.items():
        if not hasattr(instance, attr):
            setattr(instance, attr, default)

    q = VideoQuery(
        file_path="/tmp/show.s01e01.mkv",
        languages=languages,
        forced_only=False,
        title="Test Show",
        series_title="Test Show",
        year=2024,
        season=1,
        episode=1,
        absolute_episode=1,
        imdb_id="tt1234567",
    )

    with pytest.raises(ProviderAuthError):
        instance.search(q)
