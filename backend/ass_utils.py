"""ASS tag/style utilities and re-exports of media-probe helpers.

This module focuses on in-file ASS operations:

- classify_styles  — split styles into dialog vs. signs/songs using patterns
  + positional-tag heuristic
- extract_tags / restore_tags — preserve override tags across translation
- fix_line_breaks — repair line break syntax that translation may mangle

The media-probe side (ffprobe / get_media_streams / stream selection /
extract_subtitle_stream) lives in ``ass_probe.py`` and is re-exported
here so ``from ass_utils import run_ffprobe / get_media_streams / …``
continues to work unchanged.
"""

import logging
import re

from ass_probe import (  # noqa: F401 — re-exported for back-compat
    extract_subtitle_stream,
    get_all_subtitle_streams,
    get_legacy_subtitle_stream_output_path,
    get_media_streams,
    get_subtitle_stream_output_path,
    has_target_language_audio,
    has_target_language_stream,
    run_ffprobe,
    select_best_subtitle_stream,
)

logger = logging.getLogger(__name__)

# Patterns for style classification.
#
# Deliberately narrow on the OP/ED front. Anything landing in the signs bucket
# is not only left untranslated but also visible to cleanup_signs and
# purge_signs_after_extract, which DELETE what they consider signs — so a
# fansub style named after a character ("Ed", "Ed Smith") must never match.
# Hence: bare "op"/"ed" only as the whole name, plus the unambiguous karaoke
# pairing ("OP Romaji", "ED English"), plus romaji anywhere — transliterated
# Japanese is never something to hand a translator.
SIGNS_PATTERNS = re.compile(
    r"sign|^op$|^ed$|romaji"
    r"|^(?:op|ed)[\s_.-]+(?:english|eng|kanji|jp|jpn|lyrics|karaoke)\b"
    r"|song|karaoke|title|note|insert|logo|screen|board|card|letter",
    re.IGNORECASE,
)
DIALOG_PATTERNS = re.compile(
    r"default|main|dialogue|italic|flashback|narrat|top|alt|internal|thought",
    re.IGNORECASE,
)

# ASS override tag pattern - matches {...} blocks
OVERRIDE_TAG_RE = re.compile(r"\{[^}]*\}")

# Position/movement tags that indicate signs
POS_MOVE_RE = re.compile(r"\\(?:pos|move|org)\s*\(")


def classify_styles(subs):
    """Classify subtitle styles into dialog (translate) and signs/songs (keep).

    Args:
        subs: pysubs2.SSAFile object

    Returns:
        tuple: (dialog_styles: set, signs_styles: set)
    """
    dialog_styles = set()
    signs_styles = set()

    # Collect lines per style for heuristic analysis
    style_lines = {}
    for event in subs.events:
        if event.is_comment:
            continue
        style_name = event.style
        if style_name not in style_lines:
            style_lines[style_name] = []
        style_lines[style_name].append(event.text)

    for style_name in style_lines:
        # Check explicit patterns first
        if SIGNS_PATTERNS.search(style_name):
            signs_styles.add(style_name)
            continue

        if DIALOG_PATTERNS.search(style_name):
            dialog_styles.add(style_name)
            continue

        # Heuristic: check if >80% of lines have \pos() or \move() tags
        lines = style_lines[style_name]
        if lines:
            pos_count = sum(1 for line in lines if POS_MOVE_RE.search(line))
            if pos_count / len(lines) > 0.8:
                signs_styles.add(style_name)
                continue

        # Default: treat as dialog
        dialog_styles.add(style_name)

    logger.info(
        "Style classification - Dialog: %s, Signs/Songs: %s",
        dialog_styles,
        signs_styles,
    )
    return dialog_styles, signs_styles


def extract_tags(text):
    """Extract ASS override tags from text, return clean text, tag info, and original length.

    Args:
        text: ASS dialog text with potential override tags

    Returns:
        tuple: (clean_text, tag_info, original_clean_length) where tag_info is a list of
               (position, tag_string) tuples for restoration
    """
    if not OVERRIDE_TAG_RE.search(text):
        return text, [], len(text)

    tag_info = []
    parts = OVERRIDE_TAG_RE.split(text)
    tags = OVERRIDE_TAG_RE.findall(text)

    clean_parts = []
    current_clean_pos = 0

    for i, part in enumerate(parts):
        if i > 0 and i - 1 < len(tags):
            tag_info.append((current_clean_pos, tags[i - 1]))
        clean_parts.append(part)
        current_clean_pos += len(part)

    clean_text = "".join(clean_parts)
    return clean_text, tag_info, len(clean_text)


def restore_tags(translated_text, tag_info, original_clean_length=None):
    """Restore ASS override tags into translated text using proportional positioning.

    Position-0 tags (prefix) stay at the beginning. Other tags are placed
    proportionally based on original/translated length ratio, snapped to the
    nearest word boundary within +/- 3 characters.

    Args:
        translated_text: Translated text without tags
        tag_info: List of (position, tag_string) from extract_tags()
        original_clean_length: Length of original clean text (for proportional calc)

    Returns:
        Text with override tags restored
    """
    if not tag_info:
        return translated_text

    result = []
    text_pos = 0
    trans_len = len(translated_text)
    orig_len = original_clean_length or trans_len

    sorted_tags = sorted(tag_info, key=lambda x: x[0])

    for pos, tag in sorted_tags:
        if pos == 0:
            insert_pos = 0
        elif orig_len > 0:
            ratio = pos / orig_len
            insert_pos = int(ratio * trans_len)
            # Snap to nearest word boundary within +/- 3 chars
            best = insert_pos
            for offset in range(-3, 4):
                check = insert_pos + offset
                if 0 <= check <= trans_len:
                    if check == trans_len or translated_text[check] in (" ", "\\"):
                        best = check
                        break
            insert_pos = best
        else:
            insert_pos = min(pos, trans_len)

        # Never go backwards
        insert_pos = max(insert_pos, text_pos)
        insert_pos = min(insert_pos, trans_len)

        if insert_pos > text_pos:
            result.append(translated_text[text_pos:insert_pos])
            text_pos = insert_pos
        result.append(tag)

    if text_pos < trans_len:
        result.append(translated_text[text_pos:])

    return "".join(result)


def fix_line_breaks(text):
    """Fix line breaks after translation.

    The model sometimes converts \\N to \\n or literal newlines.
    """
    text = text.replace("\n", "\\N")
    text = re.sub(r"(?<!\\)\\n", r"\\N", text)
    text = re.sub(r"  +", " ", text)
    return text.strip()
