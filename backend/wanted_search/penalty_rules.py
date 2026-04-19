"""Named-class penalty rule pipeline for subtitle scoring.

Each rule is a named class with:
- ``rule_id``: stable string identifier (used as DB key for weight override)
- ``default_weight``: int, signed (negative for penalties, positive for bonuses)
- ``label``: short UI label
- ``description``: longer UI description
- ``applies(candidate, query) -> bool``: predicate
- ``weight(candidate, query) -> int``: applied weight when ``applies()`` is True

Weights are resolved from the ``scoring_weights`` table (see ``db.scoring``)
with ``score_type="penalty_rule"`` and ``weight_key=rule_id``. Rule
``default_weight`` is the fallback when no DB override exists.

Rules are registered via the ``@register_penalty`` decorator and
auto-discovered at import time.

The driver :func:`apply_penalty_pipeline` is pure: it returns a
``{rule_id: applied_weight}`` breakdown dict without mutating the
candidate's score. Callers (``providers.base.compute_score``) merge the
returned entries into the overall breakdown and recompute the sum.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from providers.base import SubtitleResult, VideoQuery

logger = logging.getLogger(__name__)


_RULE_REGISTRY: list[type["PenaltyRule"]] = []


class PenaltyRule(ABC):
    """Base class for named penalty/bonus rules applied to subtitle scoring."""

    rule_id: ClassVar[str] = ""
    default_weight: ClassVar[int] = 0
    label: ClassVar[str] = ""
    description: ClassVar[str] = ""

    @abstractmethod
    def applies(self, candidate: "SubtitleResult", query: "VideoQuery") -> bool:
        """Return True if this rule should apply to the candidate."""

    @abstractmethod
    def weight(self, candidate: "SubtitleResult", query: "VideoQuery") -> int:
        """Return the signed weight to add to the candidate's score.

        Most rules return ``self.default_weight``; dynamic rules can scale
        the weight by context.
        """


def register_penalty(cls: type[PenaltyRule]) -> type[PenaltyRule]:
    """Decorator to register a ``PenaltyRule`` subclass in the module registry."""
    if not cls.rule_id:
        raise ValueError(f"PenaltyRule {cls.__name__} must define rule_id")
    if cls in _RULE_REGISTRY:
        return cls
    _RULE_REGISTRY.append(cls)
    return cls


def apply_penalty_pipeline(
    candidate: "SubtitleResult",
    query: "VideoQuery",
) -> dict[str, int]:
    """Run all registered penalty rules against the candidate.

    Pure function: returns a dict of ``{rule_id: applied_weight}`` suitable
    for merging into the caller's breakdown map. Does NOT mutate
    ``candidate.score``.

    For each rule:
    1. If ``rule.applies(candidate, query)`` returns False → skip.
    2. Look up the configured weight override in ``scoring_weights``
       (``score_type="penalty_rule"``, ``weight_key=rule_id``); fall back
       to ``rule.default_weight``.
    3. If the configured weight is 0 → treat as disabled and skip.
    4. Call ``rule.weight(candidate, query)``. If the rule returned its
       own ``default_weight`` (the simple path), scale by the configured
       override; otherwise keep the dynamic value the rule computed.
    """
    breakdown: dict[str, int] = {}

    try:
        from db.scoring import get_penalty_rule_weights

        overrides = get_penalty_rule_weights()
    except Exception:
        overrides = {}

    for rule_cls in _RULE_REGISTRY:
        try:
            rule = rule_cls()
            if not rule.applies(candidate, query):
                continue
            configured_weight = overrides.get(rule_cls.rule_id, rule_cls.default_weight)
            if configured_weight == 0:
                continue  # User disabled this rule (or default is 0 and no override)
            applied = rule.weight(candidate, query)
            # If the rule returned its own default_weight, scale by the
            # configured override so user-edited weights take effect.
            if applied == rule_cls.default_weight and rule_cls.default_weight != 0:
                applied = configured_weight
            breakdown[rule_cls.rule_id] = int(applied)
        except Exception as e:
            logger.warning("Penalty rule %s raised: %s", rule_cls.rule_id, e)

    return breakdown
