"""Issue a UI session in a test client the way ``ui_auth.start_session`` does."""

import time

import ui_auth


def grant_ui_session(sess) -> None:
    """Mark ``sess`` as a password session of the current generation.

    Primes ``ui_auth``'s session-state cache with the defaults (generation
    "0", nothing revoked) so the check needs no database.
    """
    ui_auth._session_state_cache = (time.monotonic(), "0", {})
    sess["ui_authenticated"] = True
    sess["ui_generation"] = "0"
    sess["ui_sid"] = "test-sid"
