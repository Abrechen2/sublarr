"""Performance tests for API endpoints using pytest-benchmark."""

import pytest


@pytest.mark.benchmark
class TestAPIPerformance:
    """Performance tests for API endpoints."""

    def test_health_endpoint_performance(self, client, benchmark):
        """Benchmark health endpoint response time."""
        result = benchmark(client.get, "/api/v1/health")
        assert result.status_code == 200
        # Health endpoint should be very fast (< 10ms)
        assert benchmark.stats.mean < 0.01  # 10ms

    def test_stats_endpoint_performance(self, client, benchmark):
        """Benchmark stats endpoint response time."""
        result = benchmark(client.get, "/api/v1/stats")
        assert result.status_code == 200
        # Stats should be reasonably fast (< 100ms)
        assert benchmark.stats.mean < 0.1  # 100ms

    def test_wanted_endpoint_performance(self, client, benchmark):
        """Benchmark wanted endpoint response time."""
        result = benchmark(client.get, "/api/v1/wanted?page=1&per_page=50")
        assert result.status_code == 200
        # Wanted list should be reasonably fast (< 200ms)
        assert benchmark.stats.mean < 0.2  # 200ms

    def test_providers_endpoint_performance(self, client, benchmark):
        """Benchmark providers endpoint response time."""
        result = benchmark(client.get, "/api/v1/providers")
        assert result.status_code == 200
        # Provider status should be fast (< 100ms)
        assert benchmark.stats.mean < 0.1  # 100ms


@pytest.mark.benchmark
class TestDatabasePerformance:
    """Performance tests for database operations."""

    def test_get_wanted_items_performance(self, temp_db, benchmark):
        """Benchmark wanted items query performance."""
        from db.wanted import get_wanted_items

        result = benchmark(get_wanted_items, page=1, per_page=50)
        assert "items" in result
        # Database query should be fast (< 50ms)
        assert benchmark.stats.mean < 0.05  # 50ms

    def test_get_history_performance(self, temp_db, benchmark):
        """Benchmark history query performance."""
        from db.library import get_download_history

        result = benchmark(get_download_history, page=1, per_page=50)
        assert "history" in result or "items" in result
        # Database query should be fast (< 50ms)
        assert benchmark.stats.mean < 0.05  # 50ms
