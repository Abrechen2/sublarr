"""Notification repository: CRUD for templates, history, and quiet hours.

Provides template lookup with fallback chain, notification history logging,
quiet hours checking with overnight range and day-of-week support.
"""

import json
import logging
from datetime import datetime

from sqlalchemy import delete, func, select

from db.models.notifications import (
    NotificationHistory,
    NotificationTemplate,
    QuietHoursConfig,
)
from db.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class NotificationRepository(BaseRepository):
    """Repository for notification templates, history, and quiet hours."""

    # ---- Template CRUD -------------------------------------------------------

    def create_template(self, name: str, title_template: str = "",
                        body_template: str = "", event_type: str = None,
                        service_name: str = None, enabled: int = 1) -> dict:
        """Create a new notification template.

        Returns:
            Dict representation of the created template.
        """
        now = self._now()
        entry = NotificationTemplate(
            name=name,
            title_template=title_template,
            body_template=body_template,
            event_type=event_type,
            service_name=service_name,
            enabled=enabled,
            created_at=now,
            updated_at=now,
        )
        self.session.add(entry)
        self._commit()
        return self._to_dict(entry)

    def get_template(self, template_id: int) -> dict | None:
        """Get a single template by ID.

        Returns:
            Dict or None if not found.
        """
        entry = self.session.get(NotificationTemplate, template_id)
        return self._to_dict(entry)

    def get_templates(self, event_type: str = None) -> list[dict]:
        """Get all templates, optionally filtered by event_type.

        Returns:
            List of template dicts.
        """
        stmt = select(NotificationTemplate).order_by(NotificationTemplate.id)
        if event_type is not None:
            stmt = stmt.where(NotificationTemplate.event_type == event_type)
        entries = self.session.execute(stmt).scalars().all()
        return [self._to_dict(e) for e in entries]

    def update_template(self, template_id: int, **kwargs) -> dict | None:
        """Update a template by ID with arbitrary column values.

        Returns:
            Updated dict or None if not found.
        """
        entry = self.session.get(NotificationTemplate, template_id)
        if entry is None:
            return None
        for key, value in kwargs.items():
            if hasattr(entry, key):
                setattr(entry, key, value)
        entry.updated_at = self._now()
        self._commit()
        return self._to_dict(entry)

    def delete_template(self, template_id: int) -> bool:
        """Delete a template by ID.

        Returns:
            True if deleted, False if not found.
        """
        entry = self.session.get(NotificationTemplate, template_id)
        if entry is None:
            return False
        self.session.delete(entry)
        self._commit()
        return True

    def find_template_for_event(self, event_type: str,
                                service_name: str = None) -> dict | None:
        """Find the best matching template for an event using fallback chain.

        Priority: specific (service+event) > event-only > default (both null).

        Returns:
            Dict of matching template or None.
        """
        # 1. Try specific match: event_type + service_name
        if service_name:
            stmt = (
                select(NotificationTemplate)
                .where(
                    NotificationTemplate.event_type == event_type,
                    NotificationTemplate.service_name == service_name,
                    NotificationTemplate.enabled == 1,
                )
                .limit(1)
            )
            entry = self.session.execute(stmt).scalar_one_or_none()
            if entry is not None:
                return self._to_dict(entry)

        # 2. Try event-only match: event_type with no service_name
        stmt = (
            select(NotificationTemplate)
            .where(
                NotificationTemplate.event_type == event_type,
                NotificationTemplate.service_name.is_(None),
                NotificationTemplate.enabled == 1,
            )
            .limit(1)
        )
        entry = self.session.execute(stmt).scalar_one_or_none()
        if entry is not None:
            return self._to_dict(entry)

        # 3. Try default: both null
        stmt = (
            select(NotificationTemplate)
            .where(
                NotificationTemplate.event_type.is_(None),
                NotificationTemplate.service_name.is_(None),
                NotificationTemplate.enabled == 1,
            )
            .limit(1)
        )
        entry = self.session.execute(stmt).scalar_one_or_none()
        return self._to_dict(entry)

    # ---- History -------------------------------------------------------------

    def log_notification(self, event_type: str, title: str, body: str,
                         template_id: int = None, service_urls: str = None,
                         status: str = "sent", error: str = "") -> dict:
        """Log a notification to history.

        Returns:
            Dict representation of the log entry.
        """
        entry = NotificationHistory(
            event_type=event_type,
            title=title,
            body=body,
            template_id=template_id,
            service_urls=service_urls,
            status=status,
            error=error,
            sent_at=self._now(),
        )
        self.session.add(entry)
        self._commit()
        return self._to_dict(entry)

    def get_history(self, page: int = 1, per_page: int = 50,
                    event_type: str = None) -> dict:
        """Get paginated notification history.

        Returns:
            Dict with items, total, page, per_page.
        """
        count_stmt = select(func.count(NotificationHistory.id))
        query_stmt = (
            select(NotificationHistory)
            .order_by(NotificationHistory.sent_at.desc())
        )

        if event_type is not None:
            count_stmt = count_stmt.where(
                NotificationHistory.event_type == event_type
            )
            query_stmt = query_stmt.where(
                NotificationHistory.event_type == event_type
            )

        total = self.session.execute(count_stmt).scalar() or 0

        offset = (page - 1) * per_page
        query_stmt = query_stmt.offset(offset).limit(per_page)
        entries = self.session.execute(query_stmt).scalars().all()

        return {
            "items": [self._to_dict(e) for e in entries],
            "total": total,
            "page": page,
            "per_page": per_page,
        }

    def get_notification(self, notification_id: int) -> dict | None:
        """Get a single notification history entry by ID.

        Returns:
            Dict or None if not found.
        """
        entry = self.session.get(NotificationHistory, notification_id)
        return self._to_dict(entry)

    def clear_history(self, before_date: str = None) -> int:
        """Clear notification history, optionally before a date.

        Returns:
            Count of deleted records.
        """
        stmt = delete(NotificationHistory)
        if before_date:
            stmt = stmt.where(NotificationHistory.sent_at < before_date)
        result = self.session.execute(stmt)
        self._commit()
        return result.rowcount

    # ---- Quiet Hours ---------------------------------------------------------

    def create_quiet_hours(self, name: str, start_time: str, end_time: str,
                           days_of_week: str = "[0,1,2,3,4,5,6]",
                           exception_events: str = '["error"]',
                           enabled: int = 1) -> dict:
        """Create a quiet hours configuration.

        Returns:
            Dict representation of the created config.
        """
        now = self._now()
        entry = QuietHoursConfig(
            name=name,
            start_time=start_time,
            end_time=end_time,
            days_of_week=days_of_week,
            exception_events=exception_events,
            enabled=enabled,
            created_at=now,
            updated_at=now,
        )
        self.session.add(entry)
        self._commit()
        return self._to_dict(entry)

    def get_quiet_hours_configs(self) -> list[dict]:
        """Get all quiet hours configurations.

        Returns:
            List of quiet hours config dicts.
        """
        stmt = select(QuietHoursConfig).order_by(QuietHoursConfig.id)
        entries = self.session.execute(stmt).scalars().all()
        return [self._to_dict(e) for e in entries]

    def update_quiet_hours(self, config_id: int, **kwargs) -> dict | None:
        """Update a quiet hours config by ID.

        Returns:
            Updated dict or None if not found.
        """
        entry = self.session.get(QuietHoursConfig, config_id)
        if entry is None:
            return None
        for key, value in kwargs.items():
            if hasattr(entry, key):
                setattr(entry, key, value)
        entry.updated_at = self._now()
        self._commit()
        return self._to_dict(entry)

    def delete_quiet_hours(self, config_id: int) -> bool:
        """Delete a quiet hours config by ID.

        Returns:
            True if deleted, False if not found.
        """
        entry = self.session.get(QuietHoursConfig, config_id)
        if entry is None:
            return False
        self.session.delete(entry)
        self._commit()
        return True

    def is_quiet_hours(self, event_type: str) -> bool:
        """Check if current time falls within any active quiet hours window.

        Supports overnight ranges (e.g. 22:00 - 07:00) and day-of-week filters.
        Exception events bypass quiet hours.

        Args:
            event_type: The event type to check against exception lists.

        Returns:
            True if notifications should be suppressed, False otherwise.
        """
        stmt = select(QuietHoursConfig).where(QuietHoursConfig.enabled == 1)
        configs = self.session.execute(stmt).scalars().all()

        if not configs:
            return False

        now = datetime.now()
        current_time = now.strftime("%H:%M")
        current_day = now.weekday()  # 0=Monday in Python

        for config in configs:
            # Check if event is in exception list
            try:
                exceptions = json.loads(config.exception_events or "[]")
            except (json.JSONDecodeError, TypeError):
                exceptions = []

            if event_type in exceptions:
                continue  # This event bypasses this quiet hours config

            # Check day of week
            try:
                days = json.loads(config.days_of_week or "[0,1,2,3,4,5,6]")
            except (json.JSONDecodeError, TypeError):
                days = [0, 1, 2, 3, 4, 5, 6]

            if current_day not in days:
                continue

            # Check time range
            start = config.start_time
            end = config.end_time

            if start <= end:
                # Normal range (e.g. 09:00 - 17:00)
                if start <= current_time <= end:
                    return True
            else:
                # Overnight range (e.g. 22:00 - 07:00)
                if current_time >= start or current_time <= end:
                    return True

        return False
