"""Grouped statistics aggregation service (V1.6 #9, backend S2)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from db.models.providers import SubtitleDownload
from db.models.translation import TranslationEvent
from extensions import db
from services import statistics_service as stats


def _download(
    days_ago: int, *, provider="opensubtitles", language="de", source="provider", score=50
):
    db.session.add(
        SubtitleDownload(
            provider_name=provider,
            subtitle_id=f"id{days_ago}{provider}{language}{source}{score}",
            language=language,
            format="srt",
            file_path=f"/m/{days_ago}{language}{source}.srt",
            score=score,
            source=source,
            downloaded_at=datetime.now(UTC) - timedelta(days=days_ago),
        )
    )


def _translation(days_ago: int, *, backend="deepl", status="ok", chars=100, cost=200, latency=500):
    now = datetime.now(UTC) - timedelta(days=days_ago)
    db.session.add(
        TranslationEvent(
            backend=backend,
            source_lang="en",
            target_lang="de",
            lines_count=10,
            chars_in=chars,
            chars_out=chars,
            cost_estimate_micro_usd=cost,
            cache_hit=False,
            latency_ms=latency,
            status=status,
            started_at=now,
        )
    )


def test_subtitles_stats_breakdowns_and_range(app_ctx):
    _download(1, source="provider", language="de", provider="opensubtitles")
    _download(2, source="machine_translation", language="en", provider="animetosho")
    _download(20, source="provider", language="de", provider="opensubtitles")  # outside 7d
    db.session.commit()

    s = stats.get_subtitles_stats("7d")
    assert s["total"] == 2
    assert s["by_source"] == {"provider": 1, "machine_translation": 1}
    assert s["by_language"] == {"de": 1, "en": 1}

    s_all = stats.get_subtitles_stats("all")
    assert s_all["total"] == 3


def test_translation_stats(app_ctx):
    _translation(1, backend="deepl", status="ok", chars=100, cost=200, latency=400)
    _translation(1, backend="ollama", status="ok", chars=50, cost=0, latency=600)
    _translation(1, backend="deepl", status="error", chars=0, cost=0, latency=None)
    db.session.commit()

    t = stats.get_translation_stats("7d")
    assert t["total"] == 3
    assert t["by_backend"] == {"deepl": 1, "ollama": 1}  # only ok events
    assert t["total_chars"] == 150
    assert t["total_cost_micro_usd"] == 200
    assert round(t["pass_rate"], 2) == round(2 / 3, 2)
    assert t["avg_latency_ms"] == 500  # (400+600)/2
    assert "mt_awaiting_original" in t


def test_trends_reads_rollup(app_ctx):
    from services import stats_rollup

    _download(0, language="de")
    _download(1, language="en")
    db.session.commit()
    today = datetime.now(UTC).date()
    stats_rollup.upsert_rollup(today.isoformat())
    stats_rollup.upsert_rollup((today - timedelta(days=1)).isoformat())

    tr = stats.get_trends("7d")
    assert len(tr["dates"]) == 2
    assert sum(tr["downloads"]) == 2


def test_system_stats_shape(app_ctx):
    s = stats.get_system_stats()
    for key in ("cpu_percent", "memory_percent", "disk_percent", "uptime_seconds", "db_size_bytes"):
        assert key in s


def test_providers_stats_shape(app_ctx):
    p = stats.get_providers_stats()
    assert "providers" in p and isinstance(p["providers"], list)


def test_library_stats_shape(app_ctx):
    _download(1, language="de")
    _download(1, language="en")
    db.session.commit()
    lib = stats.get_library_stats()
    assert lib["subtitle_files"] >= 2
    assert set(lib["languages"]) >= {"de", "en"}
