"""Interactive search applies the profile it already half-applied.

Forgejo #18, part 1. The function set the profile's scoring preset and,
three lines below a comment calling itself "the manual escape hatch",
ignored that same profile's provider list. A profile that counts when
scoring and not when choosing is half a thought, and the asymmetry was
invisible: one report describes a 33-second search returning partial results
from providers the profile had excluded.

It matters past display. download_specific_for_item re-searches without the
list too, so a subtitle from an excluded provider could be written to the
library with nothing having been decided.

So the list applies by default, and the escape hatch becomes a choice the
operator makes on purpose rather than one made for them.
"""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def _search_env(monkeypatch):
    import wanted_search.search as search_mod

    item = {"id": 7, "title": "Show", "season": 1, "episode": 2, "file_path": "/m/x.mkv"}
    monkeypatch.setattr(search_mod, "get_wanted_item", lambda _id: item, raising=False)
    monkeypatch.setattr(search_mod, "update_wanted_search", lambda *_a, **_k: None, raising=False)
    monkeypatch.setattr(
        search_mod,
        "build_query_from_wanted",
        lambda _item: MagicMock(languages=[], allowed_providers=[], scoring_preset=""),
        raising=False,
    )
    return search_mod


def _run(search_mod, *, profile_providers, **kwargs):
    manager = MagicMock()
    manager.search.return_value = []

    with (
        patch.object(search_mod, "get_provider_manager", return_value=manager),
        patch(
            "wanted_search.process._load_profile_filters",
            return_value={"enabled_providers": profile_providers, "scoring_preset": "anime"},
        ),
    ):
        search_mod.search_providers_for_item(7, **kwargs)

    assert manager.search.call_count == 1
    return manager.search.call_args.args[0]


def test_the_profile_provider_list_applies_by_default(_search_env):
    """The reported case: a profile limited to one provider means one provider."""
    query = _run(_search_env, profile_providers=["customapi"])
    assert query.allowed_providers == ["customapi"]


def test_the_escape_hatch_still_exists_when_asked_for(_search_env):
    """Explicitly widening the search is what the manual path is for."""
    query = _run(_search_env, profile_providers=["customapi"], all_providers=True)
    assert query.allowed_providers == []


def test_a_profile_without_a_list_restricts_nothing(_search_env):
    """An empty list has always meant "no restriction" — that does not change."""
    query = _run(_search_env, profile_providers=[])
    assert query.allowed_providers == []


def test_the_scoring_preset_is_still_applied(_search_env):
    """The half that already worked keeps working."""
    query = _run(_search_env, profile_providers=["customapi"])
    assert query.scoring_preset == "anime"
