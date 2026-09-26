"""Pydantic + plain dict serializers for the scheduler API."""

from __future__ import annotations

from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler.triggers.base import BaseTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from pydantic import BaseModel, Field, field_validator, model_validator


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
    # IANA zone the cron fields are read in. None keeps the historical UTC.
    # The container runs UTC, so without this a "night only" window picked in
    # the UI (01:00-06:59) would fire at 03:00-08:59 in CEST. A zone (not a
    # fixed offset) keeps the window on local wall-clock time across DST.
    timezone: str | None = Field(default=None, max_length=64)

    @field_validator("timezone")
    @classmethod
    def known_zone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"unknown time zone: {value!r}") from exc
        return value


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
        # The fields mean nothing without the zone they are read in.
        out["timezone"] = str(trigger.timezone)
        return out
    return {"type": "unknown", "repr": repr(trigger)}


class InvalidTriggerError(ValueError):
    """Raised when a TriggerModel can't be converted to an APScheduler trigger."""


def trigger_model_to_apscheduler(model) -> BaseTrigger:
    """Convert a validated TriggerModel into an APScheduler BaseTrigger.

    Raises InvalidTriggerError if the resulting trigger would never fire
    or if APScheduler's own validation rejects the parameters.
    """
    import datetime

    try:
        if isinstance(model, IntervalTriggerModel):
            kwargs: dict[str, int] = {}
            if model.seconds is not None:
                kwargs["seconds"] = model.seconds
            if model.minutes is not None:
                kwargs["minutes"] = model.minutes
            if model.hours is not None:
                kwargs["hours"] = model.hours
            return IntervalTrigger(**kwargs, timezone="UTC")

        # Cron
        tz = model.timezone or "UTC"
        if model.expression:
            parts = model.expression.strip().split()
            if len(parts) == 5:
                minute, hour, day, month, dow = parts
                return CronTrigger(
                    minute=minute,
                    hour=hour,
                    day=day,
                    month=month,
                    day_of_week=dow,
                    timezone=tz,
                )
            if len(parts) == 6:
                second, minute, hour, day, month, dow = parts
                return CronTrigger(
                    second=second,
                    minute=minute,
                    hour=hour,
                    day=day,
                    month=month,
                    day_of_week=dow,
                    timezone=tz,
                )
            raise InvalidTriggerError(f"expression must have 5 or 6 fields, got {len(parts)}")

        fields = {
            k: getattr(model, k)
            for k in (
                "year",
                "month",
                "day",
                "week",
                "day_of_week",
                "hour",
                "minute",
                "second",
            )
            if getattr(model, k) is not None
        }
        trig = CronTrigger(**fields, timezone=tz)

        # Reachability guard
        if trig.get_next_fire_time(None, datetime.datetime.now(datetime.UTC)) is None:
            raise InvalidTriggerError("cron trigger is unreachable (no next fire time)")
        return trig
    except InvalidTriggerError:
        raise
    except (ValueError, TypeError) as exc:
        raise InvalidTriggerError(str(exc)) from exc
