"""Test worker scaling logic for search workers."""

from services.wanted_search_runner import _compute_max_workers


def test_worker_scaling():
    """Verify worker count respects CPU cores, leaving 2 for API."""
    assert _compute_max_workers(total=50, cpu_count=4) == 2  # DS920+: leave 2 cores
    assert _compute_max_workers(total=50, cpu_count=8) == 4  # cap stays 4
    assert _compute_max_workers(total=50, cpu_count=2) == 1  # never 0
    assert _compute_max_workers(total=1, cpu_count=16) == 1  # never more than items
    assert _compute_max_workers(total=50, cpu_count=None) == 2  # unknown: conservative
