"""Abstract base class for post-processing ops + module-level registry."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar

logger = logging.getLogger(__name__)


@dataclass
class OpResult:
    """Result of one post-processing op run."""

    op_id: str
    ok: bool
    duration_ms: int
    message: str


_OP_REGISTRY: list[type[BaseOp]] = []


class BaseOp(ABC):
    """Base class for all post-processing ops.

    Subclasses define:
      - op_id: stable identifier (also DB key)
      - label: short UI label
      - description: longer UI explanation
      - abort_on_error: bool (default False). If True, a failure aborts the
        whole pipeline. Most ops should stay False so one broken op doesn't
        block the rest.
      - execute(context) -> OpResult — actually do the work.
    """

    op_id: ClassVar[str] = ""
    label: ClassVar[str] = ""
    description: ClassVar[str] = ""
    abort_on_error: ClassVar[bool] = False

    @abstractmethod
    def execute(self, context: dict) -> OpResult:
        """Execute the op.

        Context keys: subtitle_path, video_path, lang, score, trigger.
        """


def register_op(cls: type[BaseOp]) -> type[BaseOp]:
    """Decorator to register an op in the module registry."""
    if not cls.op_id:
        raise ValueError(f"Op {cls.__name__} must define op_id")
    if cls in _OP_REGISTRY:
        return cls
    _OP_REGISTRY.append(cls)
    return cls
