"""Drawing-state compatibility helpers backed by the shared ASS lexer."""

from ass_lexer import LAYOUT, MAX_EVENT, MAX_TAGS, ASSNeedsReviewError, _state


def drawing_state_after(tag_block: str, current: bool) -> bool:
    """Read an override block using libass argument and transform boundaries."""
    if len(tag_block) > MAX_EVENT:
        raise ASSNeedsReviewError("event size limit")
    block = tag_block[1:-1] if tag_block.startswith("{") and tag_block.endswith("}") else tag_block
    return _state(block, current, [MAX_TAGS])


def holds_language(text: str) -> bool:
    """Whether ``text`` carries something worth translating.

    Layout escapes are removed first: ``\\N`` alone is a line break, not a
    sentence, and treating it as one made the selection skip whole captions.
    """
    return bool(LAYOUT.sub(" ", text).strip())
