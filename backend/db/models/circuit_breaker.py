"""ORM model for circuit breaker state persistence."""
from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from extensions import db


class CircuitBreakerState(db.Model):
    __tablename__ = "circuit_breaker_states"

    name: Mapped[str] = mapped_column(Text, primary_key=True)
    state: Mapped[str] = mapped_column(Text, nullable=False, default="closed")
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_failure_epoch: Mapped[float | None] = mapped_column(Float, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("idx_cb_state_updated", "updated_at"),)
