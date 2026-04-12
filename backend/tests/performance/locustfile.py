"""Locust load testing for Sublarr API.

Run with:
    cd backend && locust -f tests/performance/locustfile.py --host http://localhost:5765

Headless mode (CI/quick test):
    locust -f tests/performance/locustfile.py --host http://localhost:5765 \
        --headless -u 10 -r 2 --run-time 60s --csv results
"""

import os

from locust import HttpUser, between, events, task

# API key can be set via env var or defaults to empty (for unauthenticated setups)
API_KEY = os.environ.get("SUBLARR_API_KEY", "")


@events.init_command_line_parser.add_listener
def _(parser):
    parser.add_argument("--api-key", type=str, default="", help="Sublarr API key")


@events.test_start.add_listener
def on_test_start(environment, **_):
    global API_KEY  # noqa: PLW0603
    cli_key = environment.parsed_options.api_key if hasattr(environment.parsed_options, "api_key") else ""
    if cli_key:
        API_KEY = cli_key


class SublarrUser(HttpUser):
    """Simulates a typical Sublarr user browsing the dashboard and library."""

    wait_time = between(1, 3)

    def on_start(self):
        if API_KEY:
            self.client.headers["X-Api-Key"] = API_KEY

    @task(5)
    def dashboard(self):
        """Most common: load dashboard stats."""
        self.client.get("/api/v1/stats")

    @task(3)
    def health(self):
        """Health check — lightweight."""
        self.client.get("/api/v1/health")

    @task(4)
    def library_series(self):
        """Browse library page 1."""
        self.client.get("/api/v1/library/series?page=1&per_page=25")

    @task(2)
    def wanted_list(self):
        """Check wanted items."""
        self.client.get("/api/v1/wanted?page=1&per_page=50")

    @task(2)
    def history(self):
        """Browse download history."""
        self.client.get("/api/v1/history?page=1&per_page=25")

    @task(1)
    def providers_status(self):
        """Check provider health."""
        self.client.get("/api/v1/providers")

    @task(1)
    def config(self):
        """Load config (settings page)."""
        self.client.get("/api/v1/config")

    @task(1)
    def language_profiles(self):
        """Load language profiles."""
        self.client.get("/api/v1/language-profiles")

    @task(1)
    def activity(self):
        """Check activity log."""
        self.client.get("/api/v1/activity?page=1&per_page=25")


class SublarrPowerUser(HttpUser):
    """Simulates a power user performing heavier operations."""

    wait_time = between(2, 5)
    weight = 2  # Less common than regular users

    def on_start(self):
        if API_KEY:
            self.client.headers["X-Api-Key"] = API_KEY

    @task(3)
    def library_with_search(self):
        """Search library."""
        self.client.get("/api/v1/library/series?page=1&per_page=25&q=naruto")

    @task(2)
    def series_detail(self):
        """Load series detail (first series)."""
        resp = self.client.get("/api/v1/library/series?page=1&per_page=1")
        data = resp.json()
        if data.get("data") and len(data["data"]) > 0:
            series_id = data["data"][0].get("id")
            if series_id:
                self.client.get(f"/api/v1/library/series/{series_id}")

    @task(1)
    def metrics(self):
        """Scrape Prometheus metrics."""
        self.client.get("/api/v1/metrics")

    @task(1)
    def database_health(self):
        """Check database health."""
        self.client.get("/api/v1/database/health")

    @task(1)
    def cleanup_stats(self):
        """Preview cleanup stats."""
        self.client.get("/api/v1/cleanup/stats")
