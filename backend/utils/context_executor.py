"""Submit work to a thread pool with the caller's contextvars.

``ThreadPoolExecutor.submit`` does not carry the submitting thread's context
into the worker. Two things Sublarr keeps in contextvars depend on it: the
scheduler's stop signal (``abort_requested()``) and the run label that tags
every log line of a scheduled run. Work handed to a plain ``submit`` from inside
a scheduled job therefore ignores a cancel and logs as ``[-]``.

Only ``wanted_search_runner`` copied the context; this is its helper, shared.
"""

from __future__ import annotations

import contextvars
import functools
from concurrent.futures import Future


def submit_with_context(executor, fn, *args, **kwargs) -> Future:
    """``executor.submit(fn, *args, **kwargs)``, run inside a copy of this context.

    The submitted function keeps its signature — callers and test doubles see
    exactly the arguments they passed.
    """
    ctx = contextvars.copy_context()
    return executor.submit(ctx.run, functools.partial(fn, *args, **kwargs))
