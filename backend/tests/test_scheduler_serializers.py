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


def test_interval_model_to_aps_seconds():
    from apscheduler.triggers.interval import IntervalTrigger

    from routes.system.scheduler_serializers import (
        IntervalTriggerModel,
        trigger_model_to_apscheduler,
    )

    m = IntervalTriggerModel(type="interval", seconds=90)
    trig = trigger_model_to_apscheduler(m)
    assert isinstance(trig, IntervalTrigger)
    assert trig.interval.total_seconds() == 90


def test_interval_model_to_aps_minutes():
    from routes.system.scheduler_serializers import (
        IntervalTriggerModel,
        trigger_model_to_apscheduler,
    )

    m = IntervalTriggerModel(type="interval", minutes=15)
    trig = trigger_model_to_apscheduler(m)
    assert trig.interval.total_seconds() == 900


def test_cron_model_to_aps_hour_minute():
    import datetime

    from apscheduler.triggers.cron import CronTrigger

    from routes.system.scheduler_serializers import (
        CronTriggerModel,
        trigger_model_to_apscheduler,
    )

    m = CronTriggerModel(type="cron", hour=3, minute=0)
    trig = trigger_model_to_apscheduler(m)
    assert isinstance(trig, CronTrigger)
    next_fire = trig.get_next_fire_time(None, datetime.datetime.now(datetime.UTC))
    assert next_fire is not None


def test_cron_expression_shorthand():
    from apscheduler.triggers.cron import CronTrigger

    from routes.system.scheduler_serializers import (
        CronTriggerModel,
        trigger_model_to_apscheduler,
    )

    m = CronTriggerModel(type="cron", expression="0 3 * * *")
    trig = trigger_model_to_apscheduler(m)
    assert isinstance(trig, CronTrigger)


def test_unreachable_cron_raises():
    import pytest

    from routes.system.scheduler_serializers import (
        CronTriggerModel,
        InvalidTriggerError,
        trigger_model_to_apscheduler,
    )

    m = CronTriggerModel(type="cron", day_of_week="xyz", hour=3)
    with pytest.raises(InvalidTriggerError):
        trigger_model_to_apscheduler(m)
