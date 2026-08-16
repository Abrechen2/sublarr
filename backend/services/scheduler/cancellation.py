"""Cooperative cancellation for scheduled jobs.

`_tick_wrapper` bounds a job with `future.result(timeout=...)`, which bounds
the *wait*, not the *work*: `concurrent.futures` cannot cancel a thread that
has already started. A job that overran its ceiling was reported as finished
and kept running — one user's `subtitle_health_sweep` was still reading their
library sixteen hours after the scheduler logged its timeout, and pausing the
job did not stop it either.

Killing the thread is not an option: it would abandon a half-written file or a
half-committed transaction. So cancellation here is cooperative. A job checks
`abort_requested()` between work units and returns; the granularity of the stop
is the size of one unit, and no caller may promise better than that.

Job code needs nothing but `abort_requested()`. There is deliberately no
"raise on abort" variant: a job that returns normally can still record what it
completed, and a partial result that reaches the database beats a clean stack
unwind that discards it.

The plumbing that decides
which event that call sees lives here, because getting it wrong is invisible:
`ThreadPoolExecutor.submit` does NOT carry the caller's context into the worker
thread, so a ContextVar set by the scheduler would leave every job reading the
default and every check silently answering "keep going".
"""

from __future__ import annotations

import contextlib
import contextvars
import logging
import threading
import uuid

logger = logging.getLogger(__name__)

# The event belonging to the run executing on THIS thread. Set inside the
# worker callable, never by the thread that submits it — see module docstring.
_current_event: contextvars.ContextVar[threading.Event | None] = contextvars.ContextVar(
    "sublarr_job_cancel_event", default=None
)

# Events for runs currently in flight, keyed by job id. The scheduler thread
# needs to reach a running job's event from outside it (to signal a timeout or
# a pause), which a ContextVar cannot do.
_lock = threading.Lock()
_events: dict[str, threading.Event] = {}

# A human-readable id per run, keyed by that run's event object. Keyed by the
# event and not by the job id because an abandoned run and the run that
# replaced it are both live at once and must not answer to the same name —
# telling them apart in the log is the entire point.
#
# Riding on the event costs nothing and inherits its propagation: the event
# already reaches exactly the threads that belong to the run, including nested
# pool workers that re-bind it via `bound`. A second ContextVar would have to
# be threaded through every one of those sites by hand, and the site that got
# forgotten would be invisible.
_labels: dict[threading.Event, str] = {}


def begin_run(job_id: str) -> threading.Event:
    """Register a fresh event for a starting run and return it.

    A previous event for the same id is dropped rather than reused: a run that
    was abandoned still holds its own event object, and its thread must keep
    seeing the set flag so it stops at its next check point. Handing the new
    run that same, already-set event would make it abort immediately.
    """
    event = threading.Event()
    # Short and unique-enough to separate two runs of one job in a log file;
    # this is a correlation handle, not a security token.
    label = f"{job_id}:{uuid.uuid4().hex[:8]}"
    with _lock:
        _events[job_id] = event
        _labels[event] = label
    return event


def end_run(job_id: str, event: threading.Event) -> None:
    """Drop the registry entry, but only if it is still this run's event.

    An abandoned run finishing late must not unregister the event of the run
    that replaced it.
    """
    with _lock:
        if _events.get(job_id) is event:
            del _events[job_id]
        # The label goes unconditionally: it belongs to THIS event, so an
        # abandoned run cleaning up late drops its own name and not its
        # successor's. Leaving it would leak one entry per run for the life
        # of the process.
        _labels.pop(event, None)


def current_run_label() -> str | None:
    """The id of the scheduled run executing on this thread, or None.

    None for anything that is not scheduler work — a webhook, a route, a
    manual script. That distinction is the reason this exists: sweep work and
    webhook work log through the same modules from the same kind of
    background thread, and on 2026-08-15 that made a `timeout_abandoned`
    diagnosis impossible to close.
    """
    event = _current_event.get()
    if event is None:
        return None
    # Deliberately unlocked. This sits on the per-log-record path — every
    # record logged outside a request context asks — and a dict lookup is
    # atomic under the GIL, so the lock would buy nothing but contention
    # between the very worker threads whose logs it exists to label. The
    # writers still hold it: they mutate two structures and need them to
    # agree with each other, a reader of one does not.
    return _labels.get(event)


def request_stop(job_id: str, *, reason: str) -> bool:
    """Ask the run of ``job_id`` to stop at its next check point.

    Returns False when no run is registered, which is the normal case for a
    pause on an idle job.
    """
    with _lock:
        event = _events.get(job_id)
    if event is None:
        return False
    if not event.is_set():
        logger.info("scheduler: asked %s to stop (%s)", job_id, reason)
    event.set()
    return True


def activate(event: threading.Event) -> contextvars.Token:
    """Bind ``event`` to the calling thread. Call this INSIDE the worker."""
    return _current_event.set(event)


def deactivate(token: contextvars.Token) -> None:
    _current_event.reset(token)


def current_event() -> threading.Event | None:
    """The stop event bound to this thread, or None outside a scheduled run.

    Lets a caller that owns a nested pool re-bind the same event inside its
    workers — see `bound`.
    """
    return _current_event.get()


@contextlib.contextmanager
def bound(event: threading.Event | None):
    """Bind ``event`` for the duration of the block. No-op when None.

    The hazard in the module docstring repeats itself one level down: a job
    that runs its own ThreadPoolExecutor re-creates exactly the situation the
    scheduler already works around, because the copy stops at *its* worker.
    `wanted_search` did this, and every check inside an item silently read
    "keep going" — auto-sync was still starting minute-long ffsubsync runs
    seven minutes after a cancel (prod 2026-08-15).

    Pair it with a context-copying submit so the binding actually reaches the
    worker; binding alone only fixes the submitting thread.
    """
    if event is None:
        yield
        return
    token = activate(event)
    try:
        yield
    finally:
        deactivate(token)


def abort_requested() -> bool:
    """Whether the job running on this thread has been asked to stop.

    Returns False outside a scheduled run, so the same job function stays
    callable from a route, a test, or a manual script without special-casing.
    """
    event = _current_event.get()
    return event is not None and event.is_set()
