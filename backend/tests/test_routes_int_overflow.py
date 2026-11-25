"""A JSON number too large for int() is a bad request, not a 500.

``int(1e400)`` raises OverflowError, which the routes' ``except (TypeError,
ValueError)`` did not catch. Found through the penalty-rule weight on the RC.
"""

import pytest

_HUGE = '{"%s": 1e400}'


@pytest.mark.parametrize(
    ("path", "field"),
    [
        ("/api/v1/hooks", "timeout_seconds"),
        ("/api/v1/library/subtitle-backups/cleanup", "older_than_days"),
        ("/api/v1/scoring/penalty-rules/release_group_match", "weight"),
    ],
)
def test_huge_number_is_a_bad_request(client, path, field):
    method = client.put if "penalty-rules" in path else client.post
    rv = method(path, data=_HUGE % field, content_type="application/json")
    assert rv.status_code == 400, rv.get_data(as_text=True)
