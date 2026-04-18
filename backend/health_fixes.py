"""Subtitle auto-fix functions.

Extracted from health_checker.py. Each fix_* function mutates a
pysubs2.SSAFile in-place and returns the count of repairs made.
FIX_MAP wires detection-rule names to their fixer — apply_fixes() in
health_checker iterates it by name.
"""


def fix_duplicate_lines(subs) -> int:
    """Remove exact duplicate events. Returns count removed."""
    seen = set()
    to_remove = []
    for idx, event in enumerate(subs.events):
        if event.is_comment:
            continue
        key = (event.start, event.end, event.text, event.style)
        if key in seen:
            to_remove.append(idx)
        else:
            seen.add(key)
    # Remove in reverse order to preserve indices
    for idx in reversed(to_remove):
        del subs.events[idx]
    return len(to_remove)


def fix_timing_overlaps(subs) -> int:
    """Trim previous event end to current event start for same-style overlaps.

    Returns count of overlaps fixed.
    """
    groups = {}
    for idx, event in enumerate(subs.events):
        if event.is_comment:
            continue
        key = (event.style, getattr(event, "layer", 0))
        if key not in groups:
            groups[key] = []
        groups[key].append((idx, event))

    fixed = 0
    for group_key, events in groups.items():
        sorted_events = sorted(events, key=lambda x: x[1].start)
        for i in range(1, len(sorted_events)):
            prev_idx, prev = sorted_events[i - 1]
            curr_idx, curr = sorted_events[i]
            if curr.start < prev.end:
                prev.end = curr.start
                fixed += 1
    return fixed


def fix_missing_styles(subs) -> int:
    """Change undefined style references to 'Default'. Returns count fixed."""
    if not hasattr(subs, "styles") or not subs.styles:
        return 0

    defined_styles = set(subs.styles.keys())
    fixed = 0
    for event in subs.events:
        if event.is_comment:
            continue
        if event.style not in defined_styles:
            event.style = "Default"
            fixed += 1
    return fixed


def fix_empty_events(subs) -> int:
    """Remove events with empty plaintext. Returns count removed."""
    to_remove = []
    for idx, event in enumerate(subs.events):
        if event.is_comment:
            continue
        if not event.plaintext.strip():
            to_remove.append(idx)
    for idx in reversed(to_remove):
        del subs.events[idx]
    return len(to_remove)


def fix_negative_timing(subs) -> int:
    """Swap start and end when end < start. Returns count fixed."""
    fixed = 0
    for event in subs.events:
        if event.is_comment:
            continue
        if event.end < event.start:
            event.start, event.end = event.end, event.start
            fixed += 1
    return fixed


def fix_zero_duration(subs) -> int:
    """Remove zero-duration events. Returns count removed."""
    to_remove = []
    for idx, event in enumerate(subs.events):
        if event.is_comment:
            continue
        if event.start == event.end:
            to_remove.append(idx)
    for idx in reversed(to_remove):
        del subs.events[idx]
    return len(to_remove)


# Map check names to fix functions
FIX_MAP = {
    "duplicate_lines": fix_duplicate_lines,
    "timing_overlaps": fix_timing_overlaps,
    "missing_styles": fix_missing_styles,
    "empty_events": fix_empty_events,
    "negative_timing": fix_negative_timing,
    "zero_duration": fix_zero_duration,
}
