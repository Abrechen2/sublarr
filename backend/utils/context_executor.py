"""Submit work to a thread pool with (part of) the caller's context.

``ThreadPoolExecutor.submit`` does not carry the submitting thread's
contextvars into the worker. Two things Sublarr keeps there depend on it: the
scheduler's stop signal (``abort_requested()``) and the run label that tags
every log line of a scheduled run.

Two helpers, because those two needs are not the same:

* ``submit_with_context`` copies the WHOLE context — stop signal included.
  For work that must stop when its run is cancelled and that is written to
  cope with a stop mid-way (``wanted_search_runner``).
* ``submit_with_run_label`` carries ONLY the log correlation id (request id
  or run label). For pools whose workers were never written to see a stop:
  handing them the cancel signal made the media IO gate refuse a cancelled
  scan's queued probes, which the scanner read as "no embedded streams" and
  upserted as wrong wanted rows (review of 1.15.0-rc.2).
"""

from __future__ import annotations

import contextvars
import functools
from concurrent.futures import Future

# The log id a pool worker inherited from whoever submitted it. Read by
# app_logging._current_request_id after the Flask request id and before the
# worker's own run label.
_inherited_log_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "sublarr_inherited_log_id", default=None
)


def inherited_log_id() -> str | None:
    return _inherited_log_id.get()


def submit_with_context(executor, fn, *args, **kwargs) -> Future:
    """``executor.submit(fn, *args, **kwargs)``, run inside a copy of this context.

    The submitted function keeps its signature — callers and test doubles see
    exactly the arguments they passed.
    """
    ctx = contextvars.copy_context()
    return executor.submit(ctx.run, functools.partial(fn, *args, **kwargs))


def _run_labelled(log_id: str, call):
    _inherited_log_id.set(log_id)
    return call()


def submit_with_run_label(executor, fn, *args, **kwargs) -> Future:
    """``executor.submit(fn, ...)`` whose log lines carry the caller's log id.

    Nothing else crosses: no stop signal, no decision-log or other state. The
    worker runs in a fresh, empty context, so the id does not stick to the
    pool thread after the task.
    """
    from app_logging import NO_REQUEST_ID, _current_request_id

    call = functools.partial(fn, *args, **kwargs)
    log_id = _current_request_id()
    if not log_id or log_id == NO_REQUEST_ID:
        return executor.submit(call)
    return executor.submit(contextvars.Context().run, _run_labelled, log_id, call)
