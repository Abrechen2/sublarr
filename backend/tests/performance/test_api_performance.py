"""Performance tests for API endpoints using pytest-benchmark."""

import pytest


@pytest.mark.benchmark
class TestAPIPerformance:
    """Performance tests for API endpoints."""

    def test_health_endpoint_performance(self, client, benchmark):
        """Benchmark health endpoint response time."""
        result = benchmark(client.get, "/api/v1/health")
        assert result.status_code == 200
        # Health checks providers (may involve network); generous threshold
        assert benchmark.stats["mean"] < 5.0  # 5s

    def test_stats_endpoint_performance(self, client, benchmark):
        """Benchmark stats endpoint response time."""
        result = benchmark(client.get, "/api/v1/stats")
        assert result.status_code == 200
        # Stats should be reasonably fast (< 500ms)
        assert benchmark.stats["mean"] < 0.5

    def test_wanted_endpoint_performance(self, client, benchmark):
        """Benchmark wanted endpoint response time."""
        result = benchmark(client.get, "/api/v1/wanted?page=1&per_page=50")
        assert result.status_code == 200
        # Wanted list should be reasonably fast (< 500ms)
        assert benchmark.stats["mean"] < 0.5

    def test_providers_endpoint_performance(self, client, benchmark):
        """Benchmark providers endpoint response time."""
        result = benchmark(client.get, "/api/v1/providers")
        assert result.status_code == 200
        # Provider status should be fast (< 500ms)
        assert benchmark.stats["mean"] < 0.5


@pytest.mark.benchmark
class TestDatabasePerformance:
    """Performance tests for database operations."""

    def test_get_wanted_items_performance(self, app_ctx, benchmark):
        """Benchmark wanted items query performance."""
        from db.wanted import get_wanted_items

        result = benchmark(get_wanted_items, page=1, per_page=50)
        assert "data" in result
        # Database query should be fast (< 500ms)
        assert benchmark.stats["mean"] < 0.5

    def test_get_history_performance(self, app_ctx, benchmark):
        """Benchmark history query performance."""
        from db.library import get_download_history

        result = benchmark(get_download_history, page=1, per_page=50)
        assert "data" in result
        # Database query should be fast (< 500ms)
        assert benchmark.stats["mean"] < 0.5
