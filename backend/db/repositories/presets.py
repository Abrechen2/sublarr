"""Filter presets repository -- CRUD for saved filter configurations."""

import json
import logging
from datetime import UTC, datetime

from sqlalchemy import and_, delete, or_, select

from db.models.core import FilterPreset
from db.repositories.base import BaseRepository

logger = logging.getLogger(__name__)

# Allowed filter field names per scope (prevents injection via preset conditions)
ALLOWED_FIELDS = {
    "wanted": {
        "status",
        "item_type",
        "subtitle_type",
        "target_language",
        "upgrade_candidate",
        "title",
    },
    "library": {"item_type", "language", "provider"},
    "history": {"provider_name", "language", "format", "score"},
}

SUPPORTED_OPERATORS = {
    "eq": lambda col, val: col == val,
    "neq": lambda col, val: col != val,
    "contains": lambda col, val: col.ilike(f"%{val}%"),
    "starts": lambda col, val: col.ilike(f"{val}%"),
    "gt": lambda col, val: col > val,
    "lt": lambda col, val: col < val,
    "in": lambda col, val: col.in_(val if isinstance(val, list) else [val]),
}


class FilterPresetsRepository(BaseRepository):
    """CRUD for filter_presets table."""

    def list_presets(self, scope: str) -> list[dict]:
        stmt = select(FilterPreset).where(FilterPreset.scope == scope)
        rows = self.session.execute(stmt).scalars().all()
        return [self._preset_to_dict(r) for r in rows]

    def get_preset(self, preset_id: int) -> dict | None:
        row = self.session.get(FilterPreset, preset_id)
        return self._preset_to_dict(row) if row else None

    def create_preset(
        self, name: str, scope: str, conditions: dict, is_default: bool = False
    ) -> dict:
        self._validate_conditions(conditions, scope)
        now = datetime.now(UTC).isoformat()
        preset = FilterPreset(
            name=name,
            scope=scope,
            conditions=json.dumps(conditions),
            is_default=1 if is_default else 0,
            created_at=now,
            updated_at=now,
        )
        self.session.add(preset)
        self._commit()
        return self._preset_to_dict(preset)

    def update_preset(
        self, preset_id: int, name: str = None, conditions: dict = None, is_default: bool = None
    ) -> dict | None:
        row = self.session.get(FilterPreset, preset_id)
        if not row:
            return None
        if name is not None:
            row.name = name
        if conditions is not None:
            self._validate_conditions(conditions, row.scope)
            row.conditions = json.dumps(conditions)
        if is_default is not None:
            row.is_default = 1 if is_default else 0
        row.updated_at = datetime.now(UTC).isoformat()
        self._commit()
        return self._preset_to_dict(row)

    def delete_preset(self, preset_id: int) -> bool:
        row = self.session.get(FilterPreset, preset_id)
        if not row:
            return False
        self.session.execute(delete(FilterPreset).where(FilterPreset.id == preset_id))
        self._commit()
        return True

    def build_clause(self, node: dict, field_map: dict):
        """Recursively build a SQLAlchemy clause from a condition tree node.

        Args:
            node: Either {"field", "op", "value"} leaf or
                  {"logic": "AND"|"OR", "conditions": [...]} group.
            field_map: Maps field name strings to SQLAlchemy column objects.

        Returns:
            SQLAlchemy BinaryExpression or BooleanClauseList.

        Raises:
            ValueError: If field or operator not in allowed maps.
        """
        if "logic" in node:
            sub_clauses = [self.build_clause(c, field_map) for c in node.get("conditions", [])]
            if not sub_clauses:
                return and_()  # empty group = no restriction
            combinator = and_ if node["logic"].upper() == "AND" else or_
            return combinator(*sub_clauses)
        else:
            field_name = node.get("field", "")
            op_name = node.get("op", "")
            value = node.get("value")
            if field_name not in field_map:
                raise ValueError(f"Unknown filter field: {field_name}")
            if op_name not in SUPPORTED_OPERATORS:
                raise ValueError(f"Unknown filter operator: {op_name}")
            return SUPPORTED_OPERATORS[op_name](field_map[field_name], value)

    def _preset_to_dict(self, row: FilterPreset) -> dict:
        return {
            "id": row.id,
            "name": row.name,
            "scope": row.scope,
            "conditions": json.loads(row.conditions or "{}"),
            "is_default": bool(row.is_default),
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }

    def _validate_conditions(self, node: dict, scope: str) -> None:
        """Validate condition tree field names against allowlist.

        Raises ValueError on violation.
        """
        allowed = ALLOWED_FIELDS.get(scope, set())
        if "logic" in node:
            for child in node.get("conditions", []):
                self._validate_conditions(child, scope)
        else:
            field = node.get("field", "")
            if field and field not in allowed:
                raise ValueError(f"Field '{field}' not allowed for scope '{scope}'")
