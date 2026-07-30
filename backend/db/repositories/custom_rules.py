"""Repository for user-defined regex scoring rules."""

import logging
import re

from db.models.providers import CustomScoringRule
from db.repositories.base import BaseRepository

logger = logging.getLogger(__name__)

MAX_RULES = 200
MAX_NAME_LEN = 100
MAX_PATTERN_LEN = 500
MIN_WEIGHT = -999
MAX_WEIGHT = 999


def validate_rule_fields(name: str, pattern: str, weight: int) -> None:
    """Raise ``ValueError`` if any field is invalid (shared by create/update)."""
    if not isinstance(name, str) or not name.strip():
        raise ValueError("name must be a non-empty string")
    if len(name.strip()) > MAX_NAME_LEN:
        raise ValueError(f"name too long (max {MAX_NAME_LEN} chars)")
    if not isinstance(pattern, str) or not pattern.strip():
        raise ValueError("pattern must be a non-empty string")
    if len(pattern) > MAX_PATTERN_LEN:
        raise ValueError(f"pattern too long (max {MAX_PATTERN_LEN} chars)")
    try:
        re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        raise ValueError(f"invalid regex: {e}") from e
    if not isinstance(weight, int) or isinstance(weight, bool):
        raise ValueError("weight must be an integer")
    if not (MIN_WEIGHT <= weight <= MAX_WEIGHT):
        raise ValueError(f"weight must be between {MIN_WEIGHT} and {MAX_WEIGHT}")


class CustomScoringRuleRepository(BaseRepository):
    """CRUD for custom regex scoring rules."""

    def _to_dict(self, row: CustomScoringRule) -> dict:
        return {
            "id": row.id,
            "name": row.name,
            "pattern": row.pattern,
            "weight": row.weight,
            "enabled": bool(row.enabled),
        }

    def list_rules(self, enabled_only: bool = False) -> list[dict]:
        """Return all rules ordered by id (creation order)."""
        query = self.session.query(CustomScoringRule).order_by(CustomScoringRule.id)
        if enabled_only:
            query = query.filter(CustomScoringRule.enabled.is_(True))
        return [self._to_dict(r) for r in query.all()]

    def create_rule(self, name: str, pattern: str, weight: int, enabled: bool = True) -> dict:
        """Validate and insert a rule. Raises ``ValueError`` on invalid input."""
        validate_rule_fields(name, pattern, weight)
        count = self.session.query(CustomScoringRule).count()
        if count >= MAX_RULES:
            raise ValueError(f"at most {MAX_RULES} custom rules allowed")
        now = self._now()
        row = CustomScoringRule(
            name=name.strip(),
            pattern=pattern,
            weight=weight,
            enabled=bool(enabled),
            created_at=now,
            updated_at=now,
        )
        self.session.add(row)
        self._commit()
        logger.debug("Custom scoring rule %d created: %s", row.id, row.name)
        return self._to_dict(row)

    def update_rule(
        self,
        rule_id: int,
        name: str,
        pattern: str,
        weight: int,
        enabled: bool,
    ) -> dict | None:
        """Full update of a rule. Returns None if the id is unknown."""
        row = self.session.get(CustomScoringRule, rule_id)
        if row is None:
            return None
        validate_rule_fields(name, pattern, weight)
        row.name = name.strip()
        row.pattern = pattern
        row.weight = weight
        row.enabled = bool(enabled)
        row.updated_at = self._now()
        self._commit()
        logger.debug("Custom scoring rule %d updated", rule_id)
        return self._to_dict(row)

    def delete_rule(self, rule_id: int) -> bool:
        """Delete a rule. Returns False if the id is unknown."""
        row = self.session.get(CustomScoringRule, rule_id)
        if row is None:
            return False
        self.session.delete(row)
        self._commit()
        logger.debug("Custom scoring rule %d deleted", rule_id)
        return True
