"""Bounded ``page``/``per_page`` query parameters for list endpoints.

A page number is turned into an SQL OFFSET. Unbounded, ``page=10**24`` made
PostgreSQL fail with "bigint out of range" and the endpoint answer 500
(found on RC 2026-10-09 when a client probed the API with absurd values).
Out-of-range input is clamped, not rejected: a page past the end is simply
empty, as it would be for any page just past the last one.
"""

from __future__ import annotations

from flask import request

MAX_PAGE = 1_000_000


def page_args(default_per_page: int = 50, max_per_page: int = 200) -> tuple[int, int]:
    """``(page, per_page)`` from the request, each clamped to a sane range."""
    page = request.args.get("page", 1, type=int) or 1
    per_page = request.args.get("per_page", default_per_page, type=int) or default_per_page
    return min(max(page, 1), MAX_PAGE), min(max(per_page, 1), max_per_page)
