"""Translator domain exceptions.

Kept dependency-free so any layer can catch these without pulling the
translator's own imports in.
"""

from __future__ import annotations

#: Machine-readable marker on a failure result: the source was read fine and
#: simply holds nothing to translate. A sentence would have to be matched on,
#: and sentences get rewritten.
NO_TRANSLATABLE_DIALOGUE = "no_translatable_dialogue"

# An unsupported event or unsafe model answer is not proof of an empty track.
# Keep it distinct so the queue does not take its terminal no-dialogue path.
ASS_REVIEW_REQUIRED = "ass_review_required"


class NothingToTranslateError(Exception):
    """The source was read, and it carries no dialogue to translate.

    Not an environment fault, and that distinction is the whole point: an
    outage is worth retrying because it passes, while a signs-and-songs track
    reads the same way on every attempt. Anime releases ship such tracks
    routinely — karaoke romaji for the opening, typeset signs, no spoken lines.
    One on the reference install holds 7 856 events and not one in a dialog
    style.

    Callers must close the work out without scheduling another attempt. The
    queue walked its backoff ladder over this and spent up to ten attempts per
    item on an answer that cannot change.
    """


class TranslationAbortedError(Exception):
    """The translation stopped between batches because it was asked to.

    Not a failure: the batches already finished are cached, and the work
    resumes from there on the next attempt. Callers must therefore requeue
    rather than count a failed attempt — spending one of the item's attempts
    on a scheduler timeout is how items get buried through no fault of their
    own.
    """
