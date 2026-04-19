"""Pydantic + plain dict serializers for the scheduler API."""

from __future__ import annotations

from typing import Any, Literal

from apscheduler.triggers.base import BaseTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from pydantic import BaseModel, Field, model_validator


class IntervalTriggerModel(BaseModel):
    type: Literal["interval"]
    seconds: int | None = Field(default=None, ge=1)
    minutes: int | None = Field(default=None, ge=1)
    hours: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def exactly_one_unit(self) -> IntervalTriggerModel:
        units = [self.seconds, self.minutes, self.hours]
        if sum(1 for u in units if u is not None) != 1:
            raise ValueError("interval trigger requires exactly one of seconds/minutes/hours")
        return self


class CronTriggerModel(BaseModel):
    type: Literal["cron"]
    year: str | int | None = None
    month: str | int | None = None
    day: str | int | None = None
    week: str | int | None = None
    day_of_week: str | int | None = None
    hour: str | int | None = None
    minute: str | int | None = None
    second: str | int | None = None
    expression: str | None = None


TriggerModel = IntervalTriggerModel | CronTriggerModel


def serialize_trigger(trigger: BaseTrigger) -> dict[str, Any]:
    """Convert APScheduler trigger to stable JSON-ready dict."""
    if isinstance(trigger, IntervalTrigger):
        return {
            "type": "interval",
            "seconds": int(trigger.interval.total_seconds()),
        }
    if isinstance(trigger, CronTrigger):
        out: dict[str, Any] = {"type": "cron"}
        for field in trigger.fields:
            if field.is_default:
                continue
            out[field.name] = str(field)
        return out
    return {"type": "unknown", "repr": repr(trigger)}
