"""Absurd page numbers are clamped instead of overflowing the SQL OFFSET.

RC 2026-10-09: GET /api/v1/wanted?page=<26 digits> answered 500 with
"bigint out of range" from PostgreSQL.
"""

from flask import Flask

from utils.pagination import MAX_PAGE, page_args


def _args(query: str):
    app = Flask(__name__)
    with app.test_request_context(f"/x?{query}"):
        return page_args(max_per_page=200)


def test_a_huge_page_is_clamped():
    assert _args("page=49999999999999999999999900") == (MAX_PAGE, 50)


def test_zero_and_negative_values_fall_back_to_sane_ones():
    assert _args("page=0&per_page=0") == (1, 50)
    assert _args("page=-5&per_page=-1") == (1, 1)


def test_per_page_is_capped():
    assert _args("page=3&per_page=100000") == (3, 200)


def test_garbage_is_ignored():
    assert _args("page=abc&per_page=xyz") == (1, 50)
