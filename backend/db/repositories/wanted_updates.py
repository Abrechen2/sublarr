"""Mutation mixin for WantedRepository — row-level update helpers.

Extracted from db/repositories/wanted.py. Covers the five
individual-row update methods plus the allowlist used by the partial
outcome update, so the scheduler's call site
``repo.update_wanted_search_outcome(...)`` keeps its field-name safety
net without leaking internal details back into the main repository
file.
"""

from sqlalchemy import update

from db.models.core import WantedItem


class _WantedUpdatesMixin:
    """Row-level update methods mixed into WantedRepository."""

    # Allowed fields for ``update_wanted_search_outcome``. Anything not in this
    # set is silently ignored so typos in callers don't mutate unrelated rows.
    _OUTCOME_ALLOWED_FIELDS = frozenset(
        {
            "status",
            "search_count",
            "error_count",
            "failure_kind",
            "retry_after",
            "last_error_at",
            "last_search_at",
            "error",
        }
    )

    def update_wanted_status(self, item_id: int, status: str, error: str = "") -> bool:
        """Update a wanted item's status."""
        item = self.session.get(WantedItem, item_id)
        if not item:
            return False
        item.status = status
        item.error = error
        item.updated_at = self._now()
        self._commit()
        return True

    def update_wanted_search_outcome(
        self,
        item_id: int,
        *,
        search_count_increment: int = 0,
        error_count_increment: int = 0,
        reset_failure: bool = False,
        **fields,
    ) -> bool:
        """Partial update for scheduler-driven search outcomes.

        Supported fields (anything else is ignored): ``status, search_count,
        error_count, failure_kind, retry_after, last_error_at, last_search_at,
        error``.

        Column semantics:
        - ``error`` field uses **None-means-don't-touch** — passing
          ``error=None`` leaves the column unchanged. Pass ``error=""`` to
          explicitly clear it. This prevents silent data loss when a caller
          doesn't have a message to record (e.g. a new provider_error event
          without an error string should preserve the prior operator note).
        - All other allowlisted fields accept ``None`` as a valid value
          (e.g. ``retry_after=None`` to clear it).

        Atomic SQL-side increments:
        - ``search_count_increment: int = 0`` — when > 0, emits
          ``search_count = search_count + N`` as a SQL column expression so
          concurrent scheduler threads cannot lose increments via
          read-modify-write races.
        - ``error_count_increment: int = 0`` — same semantics for
          ``error_count``.

        ``reset_failure=True`` clears the failure-tracking state
        (``error_count=0, failure_kind=None, error=None, retry_after=None``).
        This is how the ``'found'`` outcome wipes prior error history.

        Returns ``True`` if the row existed and was updated, ``False`` if the
        ID was unknown (no exception — the caller is typically a background
        worker that shouldn't die just because a concurrent delete won).
        """
        # Build the patch dict respecting the allowlist. ``error`` is
        # handled separately because None means "leave column alone".
        patch: dict = {
            k: v for k, v in fields.items() if k in self._OUTCOME_ALLOWED_FIELDS and k != "error"
        }
        if "error" in fields and fields["error"] is not None:
            patch["error"] = fields["error"]

        if reset_failure:
            patch["error_count"] = 0
            patch["failure_kind"] = None
            patch["error"] = None
            patch["retry_after"] = None

        # SQL-side atomic increments to avoid read-modify-write races under
        # concurrent writers. Using column expressions (WantedItem.col + N)
        # means the DB server is the sole writer for these fields.
        if search_count_increment:
            patch["search_count"] = WantedItem.search_count + search_count_increment
        if error_count_increment:
            patch["error_count"] = WantedItem.error_count + error_count_increment

        patch["updated_at"] = self._now()

        stmt = update(WantedItem).where(WantedItem.id == item_id).values(**patch)
        result = self.session.execute(stmt)
        self._commit()
        return result.rowcount > 0

    def mark_search_attempted(self, item_id: int) -> bool:
        """Increment search_count and set last_search_at."""
        item = self.session.get(WantedItem, item_id)
        if not item:
            return False
        now = self._now()
        item.search_count = (item.search_count or 0) + 1
        item.last_search_at = now
        item.updated_at = now
        self._commit()
        return True

    def set_retry_after(self, item_id: int, retry_after) -> bool:
        """Set retry_after datetime for adaptive backoff."""
        item = self.session.get(WantedItem, item_id)
        if not item:
            return False
        item.retry_after = retry_after
        item.updated_at = self._now()
        self._commit()
        return True

    def update_existing_sub(self, item_id: int, value: str) -> bool:
        """Update the existing_sub field for a wanted item."""
        item = self.session.get(WantedItem, item_id)
        if not item:
            return False
        item.existing_sub = value
        item.updated_at = self._now()
        self._commit()
        return True

    def set_mt_pinned(self, item_id: int, pinned: bool) -> bool:
        """Pin/unpin a provisional MT (feature #8b). A pinned item is never
        auto-replaced or re-searched by ``services.mt_reseek``."""
        item = self.session.get(WantedItem, item_id)
        if not item:
            return False
        item.mt_pinned = 1 if pinned else 0
        item.updated_at = self._now()
        self._commit()
        return True

    def set_mt_pending_original(self, item_id: int, payload: str | None) -> bool:
        """Record (or clear, with ``payload=None``) the pending-original JSON
        signal set by a ``mt_on_original_found="notify"`` re-seek match."""
        item = self.session.get(WantedItem, item_id)
        if not item:
            return False
        item.mt_pending_original = payload
        item.updated_at = self._now()
        self._commit()
        return True
