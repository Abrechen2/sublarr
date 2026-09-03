"""A non-positive page must never reach the database as a negative OFFSET.

Found on 2026-09-03 by probing the deployed 1.14.0-rc.4:
``GET /api/v1/wanted?page=0`` answered HTTP 500 on RC *and* on prod, because
``offset = (page - 1) * per_page`` went to Postgres as ``OFFSET -50``:

    psycopg2.errors.InvalidRowCountInResultOffsetClause: OFFSET must not be negative

Note what this test can and cannot see. The suite runs on SQLite, and SQLite
accepts a negative OFFSET silently — ``select x from t limit 50 offset -50``
returns rows — so no assertion about a raised error would ever fail here.
What *is* observable on both engines is the page the repository reports back,
which is why that is what these assert. ``db/repositories/blacklist.py`` has
carried the same clamp, with the same kind of test, since before this bug.
"""


def test_page_zero_is_clamped(app_ctx):
    from db.wanted import get_wanted_items

    result = get_wanted_items(page=0, per_page=50)

    assert result["page"] == 1
    assert result["per_page"] == 50


def test_negative_page_is_clamped(app_ctx):
    from db.wanted import get_wanted_items

    assert get_wanted_items(page=-5, per_page=50)["page"] == 1


def test_non_positive_per_page_is_clamped(app_ctx):
    from db.wanted import get_wanted_items

    # A negative LIMIT is the same class of defect as a negative OFFSET.
    assert get_wanted_items(page=1, per_page=0)["per_page"] >= 1
    assert get_wanted_items(page=1, per_page=-10)["per_page"] >= 1


def test_a_normal_page_is_left_alone(app_ctx):
    from db.wanted import get_wanted_items

    result = get_wanted_items(page=2, per_page=25)

    assert result["page"] == 2
    assert result["per_page"] == 25
