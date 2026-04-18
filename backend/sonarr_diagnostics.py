"""Diagnostic/overview methods mixin for SonarrClient.

Extracted from sonarr_client.py. Groups two methods that don't touch
the core HTTP plumbing and are called from diagnostics/UI surfaces
rather than the search pipeline:

- ``extended_health_check`` — five-step diagnostic snapshot
  (connection, API version, library access, webhook status, health
  issues) used by the settings UI's per-instance health panel.
- ``get_library_info`` — flat series/episode count overview used by
  the dashboard and the integration export.

Both rely on ``self._get`` + ``self.url`` from the SonarrClient host
class; mixed in via multiple inheritance so the class location stays
at ``sonarr_client.SonarrClient`` for all test patches.
"""

import logging

logger = logging.getLogger(__name__)


class _SonarrDiagnosticsMixin:
    """Diagnostics + library-overview methods composed into SonarrClient."""

    def extended_health_check(self):
        """Extended diagnostic health check for Sonarr.

        Returns a structured dict with connection status, API version info,
        library access, webhook status, and health issues. Each sub-query
        is wrapped in try/except for graceful degradation.

        Returns:
            dict with keys: connection, api_version, library_access,
                  webhook_status, health_issues
        """
        report = {
            "connection": {"healthy": False, "message": ""},
            "api_version": {"version": "", "branch": "", "app_name": ""},
            "library_access": {"series_count": 0, "accessible": False},
            "webhook_status": {"configured": False, "sublarr_webhooks": []},
            "health_issues": [],
        }

        # 1. Connection + system status
        status = self._get("/system/status")
        if status is None:
            report["connection"]["message"] = f"Cannot connect to Sonarr at {self.url}"
            return report

        report["connection"]["healthy"] = True
        report["connection"]["message"] = "OK"

        # 2. API version info
        report["api_version"]["version"] = status.get("version", "")
        report["api_version"]["branch"] = status.get("branch", "")
        report["api_version"]["app_name"] = status.get("appName", "")

        # 3. Library access
        try:
            series = self._get("/series")
            if series is not None:
                report["library_access"]["accessible"] = True
                report["library_access"]["series_count"] = len(series)
        except Exception as exc:
            logger.debug("Extended health check: series query failed: %s", exc)

        # 4. Webhook status
        try:
            notifications = self._get("/notification")
            if notifications is not None:
                report["webhook_status"]["configured"] = True
                for notif in notifications:
                    name = str(notif.get("name", "")).lower()
                    implementation = str(notif.get("implementation", "")).lower()
                    if "sublarr" in name or "sublarr" in implementation:
                        report["webhook_status"]["sublarr_webhooks"].append(
                            {
                                "name": notif.get("name", ""),
                                "implementation": notif.get("implementation", ""),
                            }
                        )
        except Exception as exc:
            logger.debug("Extended health check: notification query failed: %s", exc)

        # 5. Health issues
        try:
            health = self._get("/health")
            if health is not None:
                for item in health:
                    report["health_issues"].append(
                        {
                            "type": item.get("type", ""),
                            "message": item.get("message", ""),
                        }
                    )
        except Exception as exc:
            logger.debug("Extended health check: health query failed: %s", exc)

        return report

    def get_library_info(self, anime_only=True):
        """Get library overview with subtitle status.

        Returns:
            list: Series with episode counts and file info
        """
        series_list = self.get_anime_series() if anime_only else self.get_series()
        result = []

        for series in series_list:
            # Sonarr v3 nests counts under "statistics"
            stats = series.get("statistics", {})
            result.append(
                {
                    "id": series.get("id"),
                    "title": series.get("title"),
                    "year": series.get("year"),
                    "seasons": stats.get("seasonCount", series.get("seasonCount", 0)),
                    "episodes": stats.get("episodeCount", series.get("episodeCount", 0)),
                    "episodes_with_files": stats.get(
                        "episodeFileCount", series.get("episodeFileCount", 0)
                    ),
                    "path": series.get("path"),
                    "poster": next(
                        (
                            img.get("remoteUrl", "")
                            for img in series.get("images", [])
                            if img.get("coverType") == "poster"
                        ),
                        "",
                    ),
                    "status": series.get("status"),
                }
            )

        return result
