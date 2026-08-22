"""Translator domain exceptions.

Kept dependency-free so any layer can catch these without pulling the
translator's own imports in.
"""

from __future__ import annotations


class TranslationAbortedError(Exception):
    """The translation stopped between batches because it was asked to.

    Not a failure: the batches already finished are cached, and the work
    resumes from there on the next attempt. Callers must therefore requeue
    rather than count a failed attempt — spending one of the item's attempts
    on a scheduler timeout is how items get buried through no fault of their
    own.
    """
