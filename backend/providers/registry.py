"""Provider metadata registry — single source of truth for per-provider configuration.

Each entry specifies:
  rate_limit  : (max_requests, window_seconds) — 0/0 means no limit
  timeout     : int seconds — used when provider class has no .timeout attribute
  retries     : int — used when provider class has no .max_retries attribute

Providers not listed use the ProviderManager defaults:
  rate_limit  -> (0, 0)   (no limit)
  timeout     -> settings.provider_search_timeout
  retries     -> 2
"""

PROVIDER_METADATA: dict[str, dict] = {
    "opensubtitles": {"rate_limit": (40, 10), "timeout": 10, "retries": 3},
    "jimaku": {"rate_limit": (100, 60), "timeout": 12, "retries": 2},
    "animetosho": {"rate_limit": (50, 30), "timeout": 10, "retries": 2},
    "subdl": {"rate_limit": (30, 10), "timeout": 10, "retries": 2},
}
