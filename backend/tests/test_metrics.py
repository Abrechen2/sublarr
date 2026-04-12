"""Tests for metrics.py — Prometheus metrics registration, collection, and recording."""

import os
from enum import Enum
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_sample_value(metric, labels=None):
    """Extract the current value from a Prometheus metric.

    Works for Gauge, Counter, and Histogram (sum).
    """
    if labels:
        return metric.labels(**labels)._value.get()
    return metric._value.get()


def _get_counter_value(counter, labels=None):
    """Extract the total from a Counter (which only exposes _value on labeled children)."""
    if labels:
        return counter.labels(**labels)._value.get()
    return counter._value.get()


def _get_histogram_sum(histogram, labels=None):
    """Extract the sum observation from a Histogram."""
    if labels:
        return histogram.labels(**labels)._sum.get()
    return histogram._sum.get()


# ===========================================================================
# Module-level: METRICS_AVAILABLE flag and metric objects
# ===========================================================================


class TestMetricsAvailable:
    """Verify that METRICS_AVAILABLE is True and all metric objects are defined."""

    def test_metrics_available_is_true(self):
        import metrics

        assert metrics.METRICS_AVAILABLE is True

    def test_system_metrics_defined(self):
        import metrics

        assert metrics.CPU_USAGE is not None
        assert metrics.MEMORY_USAGE is not None
        assert metrics.DISK_USAGE is not None

    def test_translation_metrics_defined(self):
        import metrics

        assert metrics.TRANSLATION_TOTAL is not None
        assert metrics.TRANSLATION_DURATION is not None

    def test_provider_metrics_defined(self):
        import metrics

        assert metrics.PROVIDER_SEARCH_TOTAL is not None
        assert metrics.PROVIDER_DOWNLOAD_TOTAL is not None

    def test_queue_metrics_defined(self):
        import metrics

        assert metrics.JOB_QUEUE_SIZE is not None
        assert metrics.WANTED_QUEUE_SIZE is not None

    def test_database_metrics_defined(self):
        import metrics

        assert metrics.DATABASE_SIZE is not None
        assert metrics.DB_QUERY_DURATION is not None
        assert metrics.DB_QUERY_TOTAL is not None
        assert metrics.DB_POOL_SIZE is not None
        assert metrics.DB_POOL_CHECKED_OUT is not None
        assert metrics.DB_POOL_OVERFLOW is not None
        assert metrics.DB_BACKEND is not None

    def test_http_metrics_defined(self):
        import metrics

        assert metrics.HTTP_REQUEST_DURATION is not None
        assert metrics.HTTP_REQUEST_TOTAL is not None
        assert metrics.HTTP_REQUESTS_IN_PROGRESS is not None

    def test_cache_metrics_defined(self):
        import metrics

        assert metrics.CACHE_HITS_TOTAL is not None
        assert metrics.CACHE_MISSES_TOTAL is not None
        assert metrics.PROVIDER_CACHE_HITS_TOTAL is not None
        assert metrics.PROVIDER_CACHE_MISSES_TOTAL is not None
        assert metrics.CACHE_SIZE is not None

    def test_redis_metrics_defined(self):
        import metrics

        assert metrics.REDIS_CONNECTED is not None
        assert metrics.REDIS_MEMORY_USED is not None

    def test_queue_backend_metrics_defined(self):
        import metrics

        assert metrics.QUEUE_SIZE is not None
        assert metrics.QUEUE_ACTIVE is not None
        assert metrics.QUEUE_FAILED is not None

    def test_circuit_breaker_state_defined(self):
        import metrics

        assert metrics.CIRCUIT_BREAKER_STATE is not None

    def test_app_info_defined(self):
        import metrics

        assert metrics.APP_INFO is not None


# ===========================================================================
# Recording helpers
# ===========================================================================


class TestRecordTranslation:
    """Tests for record_translation()."""

    def test_increments_counter_and_observes_histogram(self):
        import metrics

        # Capture before values
        before_count = _get_counter_value(
            metrics.TRANSLATION_TOTAL, {"status": "success", "format": "ass"}
        )
        before_sum = _get_histogram_sum(metrics.TRANSLATION_DURATION)

        metrics.record_translation("success", "ass", 5.5)

        after_count = _get_counter_value(
            metrics.TRANSLATION_TOTAL, {"status": "success", "format": "ass"}
        )
        after_sum = _get_histogram_sum(metrics.TRANSLATION_DURATION)

        assert after_count == before_count + 1
        assert after_sum >= before_sum + 5.5

    def test_different_labels_tracked_independently(self):
        import metrics

        before_ok = _get_counter_value(
            metrics.TRANSLATION_TOTAL, {"status": "success", "format": "srt"}
        )
        before_err = _get_counter_value(
            metrics.TRANSLATION_TOTAL, {"status": "error", "format": "srt"}
        )

        metrics.record_translation("success", "srt", 1.0)
        metrics.record_translation("error", "srt", 2.0)

        assert (
            _get_counter_value(
                metrics.TRANSLATION_TOTAL, {"status": "success", "format": "srt"}
            )
            == before_ok + 1
        )
        assert (
            _get_counter_value(
                metrics.TRANSLATION_TOTAL, {"status": "error", "format": "srt"}
            )
            == before_err + 1
        )


class TestRecordProviderSearch:
    """Tests for record_provider_search()."""

    def test_increments_counter(self):
        import metrics

        before = _get_counter_value(
            metrics.PROVIDER_SEARCH_TOTAL, {"provider": "opensubtitles", "status": "success"}
        )
        metrics.record_provider_search("opensubtitles", "success")
        after = _get_counter_value(
            metrics.PROVIDER_SEARCH_TOTAL, {"provider": "opensubtitles", "status": "success"}
        )
        assert after == before + 1


class TestRecordProviderDownload:
    """Tests for record_provider_download()."""

    def test_increments_counter(self):
        import metrics

        before = _get_counter_value(
            metrics.PROVIDER_DOWNLOAD_TOTAL, {"provider": "animetosho", "format": "ass"}
        )
        metrics.record_provider_download("animetosho", "ass")
        after = _get_counter_value(
            metrics.PROVIDER_DOWNLOAD_TOTAL, {"provider": "animetosho", "format": "ass"}
        )
        assert after == before + 1


class TestRecordHttpRequest:
    """Tests for record_http_request()."""

    def test_increments_counter_and_observes_duration(self):
        import metrics

        labels = {"method": "GET", "endpoint": "/api/v1/test", "status": "200"}
        before_count = _get_counter_value(metrics.HTTP_REQUEST_TOTAL, labels)
        before_sum = _get_histogram_sum(metrics.HTTP_REQUEST_DURATION, labels)

        metrics.record_http_request("GET", "/api/v1/test", "200", 0.123)

        after_count = _get_counter_value(metrics.HTTP_REQUEST_TOTAL, labels)
        after_sum = _get_histogram_sum(metrics.HTTP_REQUEST_DURATION, labels)

        assert after_count == before_count + 1
        assert after_sum >= before_sum + 0.123


class TestRecordDbQuery:
    """Tests for record_db_query()."""

    def test_increments_counter_and_observes_duration(self):
        import metrics

        before_count = _get_counter_value(metrics.DB_QUERY_TOTAL, {"operation": "select"})
        before_sum = _get_histogram_sum(metrics.DB_QUERY_DURATION, {"operation": "select"})

        metrics.record_db_query("select", 0.005)

        after_count = _get_counter_value(metrics.DB_QUERY_TOTAL, {"operation": "select"})
        after_sum = _get_histogram_sum(metrics.DB_QUERY_DURATION, {"operation": "select"})

        assert after_count == before_count + 1
        assert after_sum >= before_sum + 0.005


# ===========================================================================
# Collection helpers
# ===========================================================================


class TestCollectSystemMetrics:
    """Tests for collect_system_metrics()."""

    def test_sets_cpu_and_memory_gauges(self):
        import metrics

        mock_process = MagicMock()
        mock_process.memory_info.return_value = SimpleNamespace(rss=123456789)

        with patch.object(metrics.psutil, "cpu_percent", return_value=42.5), patch.object(
            metrics.psutil, "Process", return_value=mock_process
        ), patch.object(
            metrics.psutil,
            "disk_usage",
            side_effect=FileNotFoundError("no /config"),
        ):
            metrics.collect_system_metrics()

        assert _get_sample_value(metrics.CPU_USAGE) == 42.5
        assert _get_sample_value(metrics.MEMORY_USAGE) == 123456789

    def test_sets_disk_usage_for_known_paths(self):
        import metrics

        mock_process = MagicMock()
        mock_process.memory_info.return_value = SimpleNamespace(rss=100)

        disk_returns = {
            "/config": SimpleNamespace(percent=55.0),
            "/media": SimpleNamespace(percent=72.3),
        }

        with patch.object(metrics.psutil, "cpu_percent", return_value=10.0), patch.object(
            metrics.psutil, "Process", return_value=mock_process
        ), patch.object(
            metrics.psutil,
            "disk_usage",
            side_effect=lambda p: disk_returns[p],
        ):
            metrics.collect_system_metrics()

        assert _get_sample_value(metrics.DISK_USAGE, {"mount": "config"}) == 55.0
        assert _get_sample_value(metrics.DISK_USAGE, {"mount": "media"}) == 72.3

    def test_handles_disk_usage_file_not_found(self):
        """FileNotFoundError on disk_usage is silently ignored."""
        import metrics

        mock_process = MagicMock()
        mock_process.memory_info.return_value = SimpleNamespace(rss=100)

        with patch.object(metrics.psutil, "cpu_percent", return_value=1.0), patch.object(
            metrics.psutil, "Process", return_value=mock_process
        ), patch.object(
            metrics.psutil,
            "disk_usage",
            side_effect=FileNotFoundError,
        ):
            # Should not raise
            metrics.collect_system_metrics()

    def test_handles_os_error_on_disk(self):
        """OSError on disk_usage is silently ignored."""
        import metrics

        mock_process = MagicMock()
        mock_process.memory_info.return_value = SimpleNamespace(rss=100)

        with patch.object(metrics.psutil, "cpu_percent", return_value=1.0), patch.object(
            metrics.psutil, "Process", return_value=mock_process
        ), patch.object(
            metrics.psutil,
            "disk_usage",
            side_effect=OSError("permission denied"),
        ):
            metrics.collect_system_metrics()

    def test_handles_psutil_exception(self):
        """Generic psutil failure is caught and logged."""
        import metrics

        with patch.object(
            metrics.psutil, "cpu_percent", side_effect=RuntimeError("psutil broken")
        ):
            # Should not raise
            metrics.collect_system_metrics()


class TestCollectQueueMetrics:
    """Tests for collect_queue_metrics()."""

    def test_sets_queue_gauges(self):
        import metrics

        with patch("metrics.get_pending_job_count", return_value=5, create=True) as mock_jobs, patch(
            "metrics.get_wanted_summary",
            return_value={"wanted": 12},
            create=True,
        ) as mock_wanted:
            # Need to patch at the import inside the function
            with patch.dict("sys.modules", {
                "db.jobs": MagicMock(get_pending_job_count=MagicMock(return_value=5)),
                "db.wanted": MagicMock(get_wanted_summary=MagicMock(return_value={"wanted": 12})),
            }):
                metrics.collect_queue_metrics()

        assert _get_sample_value(metrics.JOB_QUEUE_SIZE) == 5
        assert _get_sample_value(metrics.WANTED_QUEUE_SIZE) == 12

    def test_handles_missing_wanted_key(self):
        """If wanted_summary has no 'wanted' key, defaults to 0."""
        import metrics

        with patch.dict("sys.modules", {
            "db.jobs": MagicMock(get_pending_job_count=MagicMock(return_value=0)),
            "db.wanted": MagicMock(get_wanted_summary=MagicMock(return_value={})),
        }):
            metrics.collect_queue_metrics()

        assert _get_sample_value(metrics.WANTED_QUEUE_SIZE) == 0

    def test_handles_exception_gracefully(self):
        """Import or DB failure is caught and logged."""
        import metrics

        with patch.dict("sys.modules", {
            "db.jobs": MagicMock(
                get_pending_job_count=MagicMock(side_effect=RuntimeError("db down"))
            ),
        }):
            # Should not raise
            metrics.collect_queue_metrics()


class TestCollectDatabaseMetrics:
    """Tests for collect_database_metrics()."""

    def test_sets_database_size_for_existing_file(self, tmp_path):
        import metrics

        db_file = tmp_path / "test.db"
        db_file.write_bytes(b"x" * 4096)

        metrics.collect_database_metrics(str(db_file))

        assert _get_sample_value(metrics.DATABASE_SIZE) == 4096

    def test_skips_nonexistent_file(self, tmp_path):
        import metrics

        # Set to a known value first
        metrics.DATABASE_SIZE.set(9999)

        metrics.collect_database_metrics(str(tmp_path / "nonexistent.db"))

        # Value should remain unchanged (no crash, no update)
        assert _get_sample_value(metrics.DATABASE_SIZE) == 9999

    def test_handles_os_error(self, tmp_path):
        import metrics

        db_file = tmp_path / "test.db"
        db_file.write_bytes(b"data")

        with patch("os.path.getsize", side_effect=OSError("permission denied")):
            # Should not raise — exception is caught silently
            metrics.collect_database_metrics(str(db_file))


class TestCollectCircuitBreakerMetrics:
    """Tests for collect_circuit_breaker_metrics()."""

    def test_sets_state_for_each_breaker(self):
        import metrics

        class FakeState(Enum):
            CLOSED = "closed"
            OPEN = "open"
            HALF_OPEN = "half_open"

        cb_closed = MagicMock()
        cb_closed.state = FakeState.CLOSED

        cb_open = MagicMock()
        cb_open.state = FakeState.OPEN

        cb_half = MagicMock()
        cb_half.state = FakeState.HALF_OPEN

        mock_manager = MagicMock()
        mock_manager._circuit_breakers = {
            "opensubtitles": cb_closed,
            "animetosho": cb_open,
            "subdump": cb_half,
        }

        with patch("metrics.get_provider_manager", return_value=mock_manager, create=True):
            with patch.dict("sys.modules", {
                "providers": MagicMock(get_provider_manager=MagicMock(return_value=mock_manager)),
            }):
                metrics.collect_circuit_breaker_metrics()

        assert (
            _get_sample_value(metrics.CIRCUIT_BREAKER_STATE, {"provider": "opensubtitles"}) == 0
        )
        assert _get_sample_value(metrics.CIRCUIT_BREAKER_STATE, {"provider": "animetosho"}) == 1
        assert _get_sample_value(metrics.CIRCUIT_BREAKER_STATE, {"provider": "subdump"}) == 2

    def test_handles_exception_gracefully(self):
        import metrics

        with patch.dict("sys.modules", {
            "providers": MagicMock(
                get_provider_manager=MagicMock(side_effect=RuntimeError("no manager"))
            ),
        }):
            # Should not raise
            metrics.collect_circuit_breaker_metrics()


class TestCollectDbPoolMetrics:
    """Tests for collect_db_pool_metrics()."""

    def test_sets_pool_stats_when_pool_has_size(self):
        import metrics

        mock_pool = MagicMock()
        mock_pool.size.return_value = 5
        mock_pool.checkedout.return_value = 2
        mock_pool.overflow.return_value = 0
        # hasattr(mock_pool, "size") is True by default on MagicMock

        mock_engine = MagicMock()
        mock_engine.pool = mock_pool
        mock_engine.dialect.name = "sqlite"

        mock_db = MagicMock()
        mock_db.engine = mock_engine

        with patch.dict("sys.modules", {
            "extensions": MagicMock(db=mock_db),
        }):
            metrics.collect_db_pool_metrics()

        assert _get_sample_value(metrics.DB_POOL_SIZE) == 5
        assert _get_sample_value(metrics.DB_POOL_CHECKED_OUT) == 2
        assert _get_sample_value(metrics.DB_POOL_OVERFLOW) == 0

    def test_skips_pool_stats_for_null_pool(self):
        """NullPool (SQLite default) has no size attribute."""
        import metrics

        mock_pool = MagicMock(spec=[])  # empty spec = no attributes
        mock_engine = MagicMock()
        mock_engine.pool = mock_pool
        mock_engine.dialect.name = "sqlite"

        mock_db = MagicMock()
        mock_db.engine = mock_engine

        with patch.dict("sys.modules", {
            "extensions": MagicMock(db=mock_db),
        }):
            # Should not raise even though pool has no size()
            metrics.collect_db_pool_metrics()

    def test_handles_exception(self):
        import metrics

        with patch.dict("sys.modules", {
            "extensions": MagicMock(
                db=MagicMock(engine=property(lambda s: (_ for _ in ()).throw(RuntimeError("boom"))))
            ),
        }):
            # Should not raise
            metrics.collect_db_pool_metrics()


class TestCollectCacheMetrics:
    """Tests for collect_cache_metrics()."""

    def test_sets_cache_size_when_backend_exists(self):
        import metrics

        mock_cache = MagicMock()
        mock_cache.get_stats.return_value = {"backend": "memory", "size": 42}

        mock_app = MagicMock()
        mock_app.cache_backend = mock_cache

        with patch("metrics.current_app", mock_app, create=True):
            with patch.dict("sys.modules", {
                "flask": MagicMock(current_app=mock_app),
            }):
                metrics.collect_cache_metrics()

        assert _get_sample_value(metrics.CACHE_SIZE, {"backend": "memory"}) == 42

    def test_skips_when_no_cache_backend(self):
        import metrics

        mock_app = MagicMock(spec=[])  # no cache_backend attr

        with patch.dict("sys.modules", {
            "flask": MagicMock(current_app=mock_app),
        }):
            # Should not raise
            metrics.collect_cache_metrics()


class TestCollectRedisMetrics:
    """Tests for collect_redis_metrics()."""

    def test_sets_connected_and_memory_when_redis_present(self):
        import metrics

        mock_redis = MagicMock()
        mock_redis.info.return_value = {"used_memory": 8_000_000}

        mock_cache = MagicMock()
        mock_cache.redis = mock_redis

        mock_app = MagicMock()
        mock_app.cache_backend = mock_cache

        with patch.dict("sys.modules", {
            "flask": MagicMock(current_app=mock_app),
        }):
            metrics.collect_redis_metrics()

        assert _get_sample_value(metrics.REDIS_CONNECTED) == 1
        assert _get_sample_value(metrics.REDIS_MEMORY_USED) == 8_000_000

    def test_sets_disconnected_when_no_redis(self):
        import metrics

        mock_cache = MagicMock(spec=[])  # no redis attr

        mock_app = MagicMock()
        mock_app.cache_backend = mock_cache

        with patch.dict("sys.modules", {
            "flask": MagicMock(current_app=mock_app),
        }):
            metrics.collect_redis_metrics()

        assert _get_sample_value(metrics.REDIS_CONNECTED) == 0

    def test_sets_disconnected_on_exception(self):
        import metrics

        mock_app = MagicMock()
        mock_app.cache_backend = MagicMock(
            redis=MagicMock(info=MagicMock(side_effect=ConnectionError("refused")))
        )

        with patch.dict("sys.modules", {
            "flask": MagicMock(current_app=mock_app),
        }):
            metrics.collect_redis_metrics()

        assert _get_sample_value(metrics.REDIS_CONNECTED) == 0


class TestCollectQueueJobMetrics:
    """Tests for collect_queue_job_metrics()."""

    def test_sets_queue_job_gauges(self):
        import metrics

        mock_queue = MagicMock()
        mock_queue.get_backend_info.return_value = {"type": "memory"}
        mock_queue.get_queue_length.return_value = 3
        mock_queue.get_active_jobs.return_value = ["job1"]
        mock_queue.get_failed_jobs.return_value = ["fail1", "fail2"]

        mock_app = MagicMock()
        mock_app.job_queue = mock_queue

        with patch.dict("sys.modules", {
            "flask": MagicMock(current_app=mock_app),
        }):
            metrics.collect_queue_job_metrics()

        assert _get_sample_value(metrics.QUEUE_SIZE, {"backend": "memory"}) == 3
        assert _get_sample_value(metrics.QUEUE_ACTIVE, {"backend": "memory"}) == 1
        assert _get_sample_value(metrics.QUEUE_FAILED, {"backend": "memory"}) == 2

    def test_skips_when_no_job_queue(self):
        import metrics

        mock_app = MagicMock(spec=[])  # no job_queue attr

        with patch.dict("sys.modules", {
            "flask": MagicMock(current_app=mock_app),
        }):
            # Should not raise
            metrics.collect_queue_job_metrics()


# ===========================================================================
# Endpoint helper: generate_metrics()
# ===========================================================================


class TestGenerateMetrics:
    """Tests for generate_metrics()."""

    def test_returns_bytes_and_content_type(self, tmp_path):
        import metrics

        db_file = tmp_path / "test.db"
        db_file.write_bytes(b"x" * 100)

        # Mock all collector functions to avoid side effects
        with patch.object(metrics, "collect_system_metrics"), patch.object(
            metrics, "collect_queue_metrics"
        ), patch.object(metrics, "collect_database_metrics"), patch.object(
            metrics, "collect_circuit_breaker_metrics"
        ), patch.object(metrics, "collect_db_pool_metrics"), patch.object(
            metrics, "collect_cache_metrics"
        ), patch.object(metrics, "collect_redis_metrics"), patch.object(
            metrics, "collect_queue_job_metrics"
        ):
            body, content_type = metrics.generate_metrics(str(db_file))

        assert isinstance(body, bytes)
        assert "text/plain" in content_type or "text/openmetrics" in content_type
        # Prometheus output should contain at least one of our custom metrics
        text = body.decode("utf-8")
        assert "sublarr_" in text

    def test_calls_all_collectors(self, tmp_path):
        import metrics

        db_file = tmp_path / "test.db"
        db_file.write_bytes(b"data")

        with patch.object(metrics, "collect_system_metrics") as m1, patch.object(
            metrics, "collect_queue_metrics"
        ) as m2, patch.object(
            metrics, "collect_database_metrics"
        ) as m3, patch.object(
            metrics, "collect_circuit_breaker_metrics"
        ) as m4, patch.object(
            metrics, "collect_db_pool_metrics"
        ) as m5, patch.object(
            metrics, "collect_cache_metrics"
        ) as m6, patch.object(
            metrics, "collect_redis_metrics"
        ) as m7, patch.object(
            metrics, "collect_queue_job_metrics"
        ) as m8:
            metrics.generate_metrics(str(db_file))

        m1.assert_called_once()
        m2.assert_called_once()
        m3.assert_called_once_with(str(db_file))
        m4.assert_called_once()
        m5.assert_called_once()
        m6.assert_called_once()
        m7.assert_called_once()
        m8.assert_called_once()

    def test_returns_fallback_when_metrics_unavailable(self, tmp_path):
        import metrics

        original = metrics.METRICS_AVAILABLE
        try:
            metrics.METRICS_AVAILABLE = False
            body, content_type = metrics.generate_metrics(str(tmp_path / "db"))
            assert body == b"# prometheus_client not installed\n"
            assert content_type == "text/plain"
        finally:
            metrics.METRICS_AVAILABLE = original


# ===========================================================================
# METRICS_AVAILABLE = False guards (early returns)
# ===========================================================================


class TestMetricsUnavailableGuards:
    """Verify all public functions are no-ops when METRICS_AVAILABLE is False."""

    @pytest.fixture(autouse=True)
    def _disable_metrics(self):
        import metrics

        original = metrics.METRICS_AVAILABLE
        metrics.METRICS_AVAILABLE = False
        yield
        metrics.METRICS_AVAILABLE = original

    def test_collect_system_metrics_noop(self):
        import metrics

        # Should not raise even though psutil calls would fail
        metrics.collect_system_metrics()

    def test_collect_queue_metrics_noop(self):
        import metrics

        metrics.collect_queue_metrics()

    def test_collect_database_metrics_noop(self):
        import metrics

        metrics.collect_database_metrics("/nonexistent")

    def test_collect_circuit_breaker_metrics_noop(self):
        import metrics

        metrics.collect_circuit_breaker_metrics()

    def test_collect_db_pool_metrics_noop(self):
        import metrics

        metrics.collect_db_pool_metrics()

    def test_collect_cache_metrics_noop(self):
        import metrics

        metrics.collect_cache_metrics()

    def test_collect_redis_metrics_noop(self):
        import metrics

        metrics.collect_redis_metrics()

    def test_collect_queue_job_metrics_noop(self):
        import metrics

        metrics.collect_queue_job_metrics()

    def test_record_translation_noop(self):
        import metrics

        metrics.record_translation("success", "ass", 1.0)

    def test_record_provider_search_noop(self):
        import metrics

        metrics.record_provider_search("test", "success")

    def test_record_provider_download_noop(self):
        import metrics

        metrics.record_provider_download("test", "srt")

    def test_record_http_request_noop(self):
        import metrics

        metrics.record_http_request("GET", "/test", "200", 0.1)

    def test_record_db_query_noop(self):
        import metrics

        metrics.record_db_query("select", 0.01)
