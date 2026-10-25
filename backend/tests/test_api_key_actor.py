"""Admin audit log lines identify the caller without logging key material."""

import logging

from security_utils import api_key_actor

KEY = "abcdef0123456789abcdef0123456789"


def test_no_key_is_anon():
    assert api_key_actor("") == "anon"
    assert api_key_actor(None) == "anon"


def test_fingerprint_is_stable_and_distinct():
    assert api_key_actor(KEY) == api_key_actor(KEY)
    assert api_key_actor(KEY) != api_key_actor(KEY[::-1])
    assert api_key_actor(KEY).startswith("key-")


def test_fingerprint_contains_no_key_characters_prefix():
    # The old label was KEY[:6]; none of the key may appear in the label.
    assert KEY[:6] not in api_key_actor(KEY)
    assert KEY[:4] not in api_key_actor(KEY)


def test_audit_lines_do_not_log_the_key_prefix(caplog):
    from flask import Flask

    from routes.system import scheduler
    from routes.translation import events, queue

    app = Flask(__name__)
    with (
        caplog.at_level(logging.INFO),
        app.test_request_context(headers={"X-Api-Key": KEY}),
    ):
        scheduler._audit_log("job-1", "pause")
        events._audit_log("purge", days=30)
        queue._audit_log("cancel", job_id="j")

    lines = [r.getMessage() for r in caplog.records if "_admin_action" in r.getMessage()]
    assert len(lines) == 3
    for line in lines:
        assert KEY[:6] not in line
        assert f"actor={api_key_actor(KEY)}" in line
