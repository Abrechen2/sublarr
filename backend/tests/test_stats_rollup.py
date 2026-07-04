"""Daily statistics rollup (V1.6 #9, backend S1).

``stats_daily_rollup`` holds one row per calendar date with counts computed from
subtitle_downloads / translation_events / sync_job_runs. The rollup is written
idempotently by ``upsert_rollup`` (safe to re-run) and drives fast trend charts.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from db.models.providers import SubtitleDownload
from db.models.statistics import StatsDailyRollup
from extensions import db
from services import stats_rollup


def _dt(day: str, hour: int = 12) -> datetime:
    return datetime.fromisoformat(day).replace(hour=hour, tzinfo=UTC)


def _add_download(day: str, *, provider="opensubtitles", language="de", source="provider"):
    db.session.add(
        SubtitleDownload(
            provider_name=provider,
            subtitle_id=f"x{day}{language}{provider}",
            language=language,
            format="srt",
            file_path=f"/m/{day}.{language}.srt",
            score=50,
            source=source,
            downloaded_at=_dt(day),
        )
    )


def test_compute_rollup_counts_downloads_by_dimension(app_ctx):
    day = "2026-06-01"
    _add_download(day, provider="opensubtitles", language="de", source="provider")
    _add_download(day, provider="opensubtitles", language="en", source="provider")
    _add_download(day, provider="animetosho", language="de", source="machine_translation")
    # A different day must not leak in.
    _add_download("2026-06-02", provider="opensubtitles", language="de")
    db.session.commit()

    r = stats_rollup.compute_rollup_for_date(day)
    assert r["downloads"] == 3
    assert r["by_source"] == {"provider": 2, "machine_translation": 1}
    assert r["by_provider"] == {"opensubtitles": 2, "animetosho": 1}
    assert r["by_language"] == {"de": 2, "en": 1}


def test_upsert_rollup_is_idempotent(app_ctx):
    day = "2026-06-03"
    _add_download(day, language="de")
    _add_download(day, language="en")
    db.session.commit()

    stats_rollup.upsert_rollup(day)
    stats_rollup.upsert_rollup(day)  # re-run must not duplicate

    rows = db.session.query(StatsDailyRollup).filter_by(date=day).all()
    assert len(rows) == 1
    assert rows[0].downloads == 2
    assert json.loads(rows[0].by_language_json) == {"de": 1, "en": 1}


def test_upsert_rollup_reflects_new_data_on_rerun(app_ctx):
    day = "2026-06-04"
    _add_download(day, language="de")
    db.session.commit()
    stats_rollup.upsert_rollup(day)

    _add_download(day, language="en")
    db.session.commit()
    stats_rollup.upsert_rollup(day)

    row = db.session.query(StatsDailyRollup).filter_by(date=day).one()
    assert row.downloads == 2


def test_tick_rolls_up_recent_days(app_ctx):
    # today + yesterday should both get rows written.
    today = datetime.now(UTC)
    yesterday = today - timedelta(days=1)
    for d in (today, yesterday):
        db.session.add(
            SubtitleDownload(
                provider_name="opensubtitles",
                subtitle_id=f"t{d.isoformat()}",
                language="de",
                format="srt",
                file_path=f"/m/{d.date()}.de.srt",
                score=50,
                source="provider",
                downloaded_at=d,
            )
        )
    db.session.commit()

    stats_rollup.stats_rollup_tick()

    for d in (today, yesterday):
        row = db.session.query(StatsDailyRollup).filter_by(date=d.date().isoformat()).one_or_none()
        assert row is not None and row.downloads >= 1
