"""A retry policy whose ``Retry-After`` can never take a worker out of service.

urllib3 honours a ``Retry-After`` header by calling ``time.sleep()`` inside
``send()``. Two things do not reach that sleep: the request timeout, which
bounds socket operations and not the pause between attempts, and a scheduled
job's abort event, which is read between items — and the item never returns.
A server that answers a retryable status with a long ``Retry-After`` therefore
decides for itself how long the calling thread stops working.

Prod 2026-09-27 measured it. A ``wanted_search`` tick logged 1015 lines in
three minutes, went silent for 42 minutes and was filed ``timeout_abandoned``;
``mt_reseek`` followed at 16:48. The stack dump added that same morning for
exactly this question found every worker in one place:

    providers/subdl.py:562            download → _stream_download
    providers/download_manager.py:73  session.get(...)
    urllib3/util/retry.py:374         sleep_for_retry → time.sleep(retry_after)

``providers.http_session`` already states the rule this breaks: HTTP 429 is
deliberately kept out of ``status_forcelist`` so urllib3 never sleeps a rate
limit, and ``RetryingSession.request`` raises ``ProviderRateLimitError``
instead. Waiting out a provider belongs to the budget manager and the circuit
breaker, where a stop request is still heard. The retryable 5xx statuses
carried the same header through a different door.

The pause is therefore clamped rather than ignored: a provider asking for two
seconds still gets them, a provider asking for fifteen minutes gets a failed
attempt whose response reaches the caller through the normal error path.
"""

from urllib3.util.retry import Retry

# Long enough to be a courtesy, short enough that a full chain of attempts
# (three, everywhere this is used) cannot outlast any tick budget here.
MAX_HONOURED_RETRY_AFTER_S = 5.0


class BoundedRetry(Retry):
    """``Retry`` that never sleeps longer than ``max_honoured_retry_after_s``.

    urllib3 builds each further policy of a retry chain with
    ``type(self)(**params)``, so the bound survives every hop with no extra
    plumbing. That is the whole point: a clamp holding only for the first
    attempt would still lose the thread on the second.
    """

    max_honoured_retry_after_s: float = MAX_HONOURED_RETRY_AFTER_S

    def get_retry_after(self, response) -> float | None:
        """Return the server's requested pause, capped at the bound."""
        retry_after = super().get_retry_after(response)
        if retry_after is None:
            return None
        return min(retry_after, self.max_honoured_retry_after_s)
