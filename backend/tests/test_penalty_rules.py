"""Plan B4 — PenaltyRule pipeline tests."""

import pytest


def test_penalty_rule_abc_exists():
    from wanted_search.penalty_rules import PenaltyRule

    # Abstract class — cannot instantiate
    with pytest.raises(TypeError):
        PenaltyRule()


def test_register_penalty_decorator_adds_to_registry():
    from wanted_search.penalty_rules import PenaltyRule, _RULE_REGISTRY, register_penalty

    # Count before
    before = len(_RULE_REGISTRY)

    @register_penalty
    class DummyRule(PenaltyRule):
        rule_id = "dummy_rule_test"
        default_weight = 5
        label = "Dummy"
        description = "Test rule"

        def applies(self, candidate, query):
            return False

        def weight(self, candidate, query):
            return self.default_weight

    assert len(_RULE_REGISTRY) == before + 1
    assert DummyRule in _RULE_REGISTRY

    # Cleanup so subsequent tests aren't polluted
    _RULE_REGISTRY.remove(DummyRule)
