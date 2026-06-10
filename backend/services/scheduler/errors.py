"""Scheduler domain exceptions.

Kept in a dependency-free module so both the facade (``core``) and the
package root can import them without import cycles.
"""

from __future__ import annotations


class JobNotRegisteredError(KeyError):
    """Raised when operating on an unknown JobSpec id."""


class OneshotAlreadyPendingError(RuntimeError):
    """Raised by run_now when a prior one-shot for the same job is still pending."""
