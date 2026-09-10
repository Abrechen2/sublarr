"""A required setting is not the same thing as a required credential.

Forgejo #18: a local CustomAPI provider needing no key at all was gated out
of every search with "no usable key in pool (all exhausted, 429-cooling, or
pool row deleted)" — advice the operator cannot follow, since there is no
credential to put in a pool row.

The predicate refused the anonymous path as soon as ANY config field was
marked required, and CustomAPI's required field is its base URL. Its API key
is declared `required: False`. The provider was therefore gated by the one
field that says where it lives, not by one that says who you are.

Measured across the registry, exactly two providers change: customapi and
subsdump — both required a URL and nothing else.
"""

from providers.search_coordinator import _provider_can_search_without_pool_key


class _Provider:
    """Stand-in carrying only the declarative contract the predicate reads."""

    def __init__(self, config_fields):
        self.config_fields = config_fields


def test_a_required_url_does_not_demand_a_pool_row():
    """The reported case: CustomAPI's shape."""
    provider = _Provider(
        [
            {"key": "customapi_base_url", "label": "Base URL", "type": "text", "required": True},
            {"key": "customapi_api_key", "label": "API Key", "type": "password", "required": False},
        ]
    )
    assert _provider_can_search_without_pool_key(provider) is True


def test_a_required_password_still_demands_one():
    provider = _Provider(
        [
            {"key": "addic7ed_username", "type": "text", "required": True},
            {"key": "addic7ed_password", "type": "password", "required": True},
        ]
    )
    assert _provider_can_search_without_pool_key(provider) is False


def test_a_required_api_key_still_demands_one_whatever_its_type():
    """The key name carries the meaning even when the type field is sloppy."""
    provider = _Provider([{"key": "opensubtitles_api_key", "type": "text", "required": True}])
    assert _provider_can_search_without_pool_key(provider) is False


def test_an_optional_credential_never_gates():
    """An account that merely raises limits must not force a pool row."""
    provider = _Provider(
        [
            {"key": "some_url", "type": "text", "required": True},
            {"key": "some_password", "type": "password", "required": False},
        ]
    )
    assert _provider_can_search_without_pool_key(provider) is True


def test_no_config_fields_at_all_means_anonymous():
    assert _provider_can_search_without_pool_key(_Provider([])) is True


def test_a_malformed_entry_keeps_the_gate():
    """The safe direction stays the safe direction: assume credentials."""
    provider = _Provider(["not-a-dict"])
    assert _provider_can_search_without_pool_key(provider) is False


def test_the_registry_changes_only_where_a_url_was_the_culprit():
    """Guard the widening: no provider with a real credential may slip through.

    Enumerating the registered providers, the old rule and the new one differ
    on exactly customapi and subsdump, and each of those requires only a URL.
    If this list grows, the change let a credentialed provider search
    anonymously — which is the direction that must never happen quietly.
    """
    from providers.registry import _PROVIDER_CLASSES, import_builtin_providers

    import_builtin_providers()

    def old_rule(cls):
        fields = getattr(cls, "config_fields", []) or []
        if not fields:
            return True
        return not any(
            (not isinstance(f, dict)) or f.get("required") for f in fields
        ) and all(isinstance(f, dict) for f in fields)

    changed = {
        name
        for name, cls in _PROVIDER_CLASSES.items()
        if old_rule(cls) != _provider_can_search_without_pool_key(cls)
    }
    assert changed == {"customapi", "subsdump"}, changed
