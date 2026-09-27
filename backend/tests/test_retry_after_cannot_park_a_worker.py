"""A server's ``Retry-After`` must not decide how long a worker stops working.

urllib3 sleeps that header inside ``send()``. The request timeout does not
bound it (it bounds socket operations) and a job's abort event does not reach
it (that is read between items, and the item never returns), so the pause is
whatever the other side asks for.

Prod 2026-09-27 paid for it twice in one afternoon. A ``wanted_search`` tick
logged 1015 lines between 15:13 and 15:16, went silent for 42 minutes and was
recorded ``timeout_abandoned`` at 15:58:50Z; ``mt_reseek`` followed at
16:48:52Z. Both stack dumps showed the tick worker waiting in
``as_completed`` while every item thread sat in
``urllib3/util/retry.py:374 sleep_for_retry → time.sleep(retry_after)``,
reached through ``providers/subdl.py:562`` → ``_stream_download``.

``providers.http_session`` had already written the rule down for HTTP 429 —
keep it out of ``status_forcelist``, raise ``ProviderRateLimitError``, let the
budget manager and circuit breaker do the waiting where a stop request is
still heard. The retryable 5xx statuses carried the same header through a door
nobody had closed.
"""

from unittest.mock import patch

from urllib3.util.retry import Retry

from utils.bounded_retry import MAX_HONOURED_RETRY_AFTER_S, BoundedRetry


class _Response:
    """The slice of urllib3's response that ``get_retry_after`` reads.

    Deliberately not a MagicMock: a mock answers ``getheader`` whatever the
    attribute name happens to be, so it would keep passing if urllib3 changed
    how the header is read — which is the one thing these tests are here for.
    """

    def __init__(self, retry_after: str | None = None, status: int = 503):
        self.status = status
        self._retry_after = retry_after

    def getheader(self, name: str, default=None):
        if name.lower() == "retry-after":
            return self._retry_after if self._retry_after is not None else default
        return default

    def get_redirect_location(self) -> bool:
        """``Retry.increment`` asks this before it looks at the status."""
        return False

    # urllib3 2.x reads headers through a mapping; keep both doors open so the
    # clamp does not quietly stop applying on an upgrade.
    @property
    def headers(self) -> dict[str, str]:
        return {} if self._retry_after is None else {"Retry-After": self._retry_after}


class TestTheClampItself:
    def test_a_long_retry_after_is_cut_to_the_bound(self):
        """The 42-minute case. SubDL asked for 900s; a worker may not go."""
        assert BoundedRetry().get_retry_after(_Response("900")) == MAX_HONOURED_RETRY_AFTER_S

    def test_a_short_retry_after_is_honoured_unchanged(self):
        """A courtesy pause is still a courtesy pause — this is a cap, not a veto."""
        assert BoundedRetry().get_retry_after(_Response("2")) == 2

    def test_no_header_means_no_pause_to_cap(self):
        """Without the header urllib3 falls back to its own bounded backoff."""
        assert BoundedRetry().get_retry_after(_Response(None)) is None

    def test_an_http_date_far_in_the_future_is_cut_too(self):
        """``Retry-After`` may be a date. The parsed seconds get the same cap."""
        response = _Response("Sun, 27 Sep 2099 15:58:50 GMT")
        assert BoundedRetry().get_retry_after(response) == MAX_HONOURED_RETRY_AFTER_S

    def test_the_sleep_that_actually_runs_is_the_capped_one(self):
        """``sleep_for_retry`` is the caller of record — assert on its sleep."""
        with patch("urllib3.util.retry.time.sleep") as sleep:
            slept = BoundedRetry().sleep_for_retry(_Response("900"))
        assert slept is True
        sleep.assert_called_once_with(MAX_HONOURED_RETRY_AFTER_S)

    def test_the_unbounded_policy_really_would_have_slept_the_full_pause(self):
        """Guards the premise: without the subclass this is a 15-minute sleep."""
        with patch("urllib3.util.retry.time.sleep") as sleep:
            Retry().sleep_for_retry(_Response("900"))
        sleep.assert_called_once_with(900)


class TestTheClampSurvivesTheChain:
    """urllib3 does not reuse one policy — it builds the next with ``new()``.

    A clamp that held only for the first attempt would still lose the thread on
    the second, and nothing else in these tests would notice.
    """

    def test_new_returns_the_bounded_policy(self):
        assert isinstance(BoundedRetry(total=3).new(), BoundedRetry)

    def test_the_bound_still_applies_after_a_status_increment(self):
        policy = BoundedRetry(total=3, status_forcelist=[503], raise_on_status=False)
        after_one_attempt = policy.increment(method="GET", url="/x", response=_Response("900"))
        assert isinstance(after_one_attempt, BoundedRetry)
        assert after_one_attempt.get_retry_after(_Response("900")) == MAX_HONOURED_RETRY_AFTER_S


class TestTheSessionsThatUseIt:
    def test_the_provider_session_carries_the_bound(self):
        from providers.http_session import create_session

        adapter = create_session().adapters["https://"]
        assert isinstance(adapter.max_retries, BoundedRetry)

    def test_429_is_still_not_urllib3s_business(self):
        """The older half of the same rule. Losing it would re-open the door."""
        from providers.http_session import create_session

        adapter = create_session().adapters["https://"]
        assert 429 not in (adapter.max_retries.status_forcelist or [])

    def test_the_webhook_session_carries_the_bound(self):
        """Here 429 *is* retried, so the cap is the only thing holding the pool."""
        from events.webhooks import _create_webhook_session

        adapter = _create_webhook_session().adapters["https://"]
        assert isinstance(adapter.max_retries, BoundedRetry)
        assert 429 in adapter.max_retries.status_forcelist
