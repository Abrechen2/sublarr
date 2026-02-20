"""
Locust load testing configuration for Sublarr API
Run with: locust -f locustfile.py --host=http://localhost:5765
"""

from locust import HttpUser, task, between
import random


class SublarrAPIUser(HttpUser):
    """Simulated user for Sublarr API load testing."""
    
    wait_time = between(1, 3)  # Wait 1-3 seconds between requests
    
    def on_start(self):
        """Called when a simulated user starts."""
        # Health check to ensure API is available
        self.client.get("/api/v1/health")
    
    @task(3)
    def get_health(self):
        """Health endpoint - most common request."""
        self.client.get("/api/v1/health")
    
    @task(2)
    def get_stats(self):
        """Stats endpoint."""
        self.client.get("/api/v1/stats")
    
    @task(2)
    def get_wanted(self):
        """Get wanted items."""
        self.client.get("/api/v1/wanted?page=1&per_page=50")
    
    @task(2)
    def get_wanted_summary(self):
        """Get wanted summary."""
        self.client.get("/api/v1/wanted/summary")
    
    @task(1)
    def get_providers(self):
        """Get provider status."""
        self.client.get("/api/v1/providers")
    
    @task(1)
    def get_library_series(self):
        """Get library series."""
        self.client.get("/api/v1/library/series?page=1&per_page=50")
    
    @task(1)
    def get_library_movies(self):
        """Get library movies."""
        self.client.get("/api/v1/library/movies?page=1&per_page=50")
    
    @task(1)
    def get_history(self):
        """Get download history."""
        self.client.get("/api/v1/history?page=1&per_page=50")
    
    @task(1)
    def get_blacklist(self):
        """Get blacklist."""
        self.client.get("/api/v1/blacklist?page=1&per_page=50")
    
    @task(1)
    def get_language_profiles(self):
        """Get language profiles."""
        self.client.get("/api/v1/language-profiles")
    
    @task(1)
    def get_config(self):
        """Get configuration."""
        self.client.get("/api/v1/config")
    
    @task(1)
    def refresh_wanted(self):
        """Refresh wanted items (POST request)."""
        self.client.post("/api/v1/wanted/refresh")
