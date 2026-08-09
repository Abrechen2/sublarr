"""Which gate is currently keeping a provider out of searches (#185).

The gaps this closes, both from the same field report: ~20 providers were
silently skipped by the pool gate and nothing in the UI said so, and a provider
whose downloads all failed kept a green success rate. The per-item decision log
answers "why did this item find nothing" one item at a time; nothing answered
"which of my providers are actually participating right now".

The order matters as much as the list. A provider can be behind several gates
at once, and reporting the wrong one sends the operator to fix the wrong thing,
so `gate` follows the order the search coordinator actually applies.
"""

import pytest

from db.repositories.providers import ProviderRepository


@pytest.fixture
def repo(app_ctx):
    return ProviderRepository()


def _health(app):
    from routes.providers.search import provider_health

    with app.test_request_context():
        return {p["name"]: p for p in provider_health().get_json()["providers"]}


def test_a_participating_provider_reports_no_gate(app_ctx, repo):
    repo.record_search("gestdown", success=True)

    entry = _health(app_ctx).get("gestdown")
    assert entry is not None
    assert entry["gate"] == "ok"


def test_an_open_circuit_breaker_is_named(app_ctx, repo, monkeypatch):
    from providers import get_provider_manager

    repo.record_search("opensubtitles", success=True)
    manager = get_provider_manager()

    class _OpenBreaker:
        state = "open"

        def allow_request(self):
            return False

    monkeypatch.setitem(manager._circuit_breakers, "opensubtitles", _OpenBreaker())

    assert _health(app_ctx)["opensubtitles"]["gate"] == "circuit_open"


def test_auto_disable_outranks_the_breaker(app_ctx, repo, monkeypatch):
    """Both can be true at once. Auto-disable is checked first in the real
    search path, and it is also the one the operator has to clear, so naming
    the breaker instead would point at a symptom.
    """
    from providers import get_provider_manager

    repo.record_search("opensubtitles", success=True)
    repo.auto_disable_provider("opensubtitles", cooldown_minutes=60)

    class _OpenBreaker:
        state = "open"

        def allow_request(self):
            return False

    monkeypatch.setitem(get_provider_manager()._circuit_breakers, "opensubtitles", _OpenBreaker())

    assert _health(app_ctx)["opensubtitles"]["gate"] == "auto_disabled"


def test_a_credentialed_provider_without_a_pool_row_says_so(app_ctx, repo, monkeypatch):
    """The gate that skipped providers silently.

    A provider that needs credentials and has no pool row is genuinely
    misconfigured, and that is worth naming — it is the one case where the
    advice "add a pool row" can actually be followed.

    The provider is stubbed because a real credentialed one never initialises
    in a test environment, and an uninitialised provider is not gated at all —
    it simply never runs.
    """
    from providers import get_provider_manager

    class _NeedsAKey:
        name = "stubprovider"
        tier = "free"
        rate_limits = {"free": {"second": 5, "hour": 200, "day": 1000}}
        config_fields = [{"key": "api_key", "label": "API Key", "required": True}]

    from routes.providers.search import _active_gate

    manager = get_provider_manager()
    monkeypatch.setitem(manager._providers, "stubprovider", _NeedsAKey())

    # Straight at the resolver: `get_provider_status` iterates the provider
    # registry, so a stub in `_providers` never reaches the endpoint's list.
    # The endpoint's use of this function is covered by the cases above.
    gate = _active_gate(manager, {"name": "stubprovider"}, {})
    assert gate == "no_pool_key", f"expected the pool gate to be named, got {gate!r}"


def test_an_uninitialised_provider_is_not_reported_as_gated(app_ctx, repo):
    """It is not blocked by anything — it never runs at all, and saying
    "budget" or "pool" about it would send the operator hunting a gate that
    was never reached."""
    repo.record_search("opensubtitles", success=True)

    assert _health(app_ctx)["opensubtitles"]["gate"] == "not_initialised"


def test_a_keyless_provider_without_a_pool_row_is_not_gated(app_ctx, repo):
    """Fixed in ee2fb756 — the health view must agree with the search path.

    If this ever disagrees, one of the two is lying about who participates.
    """
    repo.record_search("gestdown", success=True)

    assert _health(app_ctx)["gestdown"]["gate"] == "ok"
