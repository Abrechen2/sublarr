"""Pydantic serializer tests for scheduler API."""

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from routes.system.scheduler_serializers import serialize_trigger


def test_serialize_interval_seconds():
    assert serialize_trigger(IntervalTrigger(seconds=90)) == {
        "type": "interval",
        "seconds": 90,
    }


def test_serialize_interval_minutes():
    assert serialize_trigger(IntervalTrigger(minutes=15)) == {
        "type": "interval",
        "seconds": 900,
    }


def test_serialize_cron_hour_minute():
    out = serialize_trigger(CronTrigger(hour=3, minute=0))
    assert out["type"] == "cron"
    assert out["hour"] == "3"
    assert out["minute"] == "0"


def test_serialize_cron_day_of_week():
    out = serialize_trigger(CronTrigger(day_of_week="sun", hour=5))
    assert out["type"] == "cron"
    assert out["day_of_week"] == "sun"
    assert out["hour"] == "5"
