"""Frequency-based glossary term candidate extractor.

Scans subtitle sidecar files (.{lang}.ass / .{lang}.srt) for a series directory
and returns a ranked list of proper-noun candidates suitable for seeding a
translation glossary.
"""

import logging
import os
import re
from collections import Counter
from typing import Any

import pysubs2

logger = logging.getLogger(__name__)

# Words that indicate a place name when present in a multi-word term
_PLACE_INDICATORS: frozenset[str] = frozenset(
    {
        "village",
        "town",
        "city",
        "forest",
        "mountain",
        "valley",
        "kingdom",
        "land",
        "island",
        "sea",
        "lake",
        "river",
        "castle",
        "temple",
        "shrine",
        "academy",
        "district",
        "region",
        "country",
        "nation",
        "realm",
        "territory",
        "province",
        "empire",
        "clan",
        "gate",
        "bridge",
        "road",
        "street",
        "square",
        "plaza",
        "park",
        "tower",
        "fortress",
        "harbor",
        "port",
        "bay",
        "cape",
        "peninsula",
        "desert",
        "plains",
        "jungle",
        "swamp",
        "marsh",
    }
)

# Regex to strip ASS override tags like {\\pos(123,456)} or {\\an8}
_ASS_TAG_RE = re.compile(r"\{[^}]*\}")

# Single title-cased proper noun: starts with uppercase, followed by 2+ lowercase letters
_SINGLE_PROPER_RE = re.compile(r"\b([A-Z][a-z]{2,})\b")

# Two-word proper noun combo: two consecutive title-cased words
_TWO_WORD_PROPER_RE = re.compile(r"\b([A-Z][a-z]{2,})\s+([A-Z][a-z]{2,})\b")

# Common English words that are title-cased but are not proper nouns
# (e.g. sentence-initial words, common nouns). We use a small stop-set to filter.
_STOPWORDS: frozenset[str] = frozenset(
    {
        "The",
        "This",
        "That",
        "These",
        "Those",
        "What",
        "When",
        "Where",
        "Which",
        "Who",
        "Why",
        "How",
        "And",
        "But",
        "For",
        "Nor",
        "Yet",
        "Not",
        "Yes",
        "Now",
        "Let",
        "Get",
        "Got",
        "Can",
        "You",
        "Your",
        "Our",
        "His",
        "Her",
        "Its",
        "Was",
        "Are",
        "Has",
        "Had",
        "Did",
        "Does",
        "Just",
        "Well",
        "Also",
        "Even",
        "Still",
        "Then",
        "Here",
        "There",
        "Come",
        "Look",
        "Wait",
        "Stop",
        "Never",
        "Always",
        "Already",
        "Because",
        "Since",
        "With",
        "From",
        "Into",
        "Over",
        "After",
        "Before",
        "About",
        "Again",
        "Back",
        "Down",
        "More",
        "Much",
        "Every",
        "Right",
        "Sure",
        "Sorry",
        "Thank",
        "Please",
        "Maybe",
        "Really",
        "Know",
        "Think",
        "Want",
        "Need",
        "Going",
        "Said",
        "Told",
        "That",
        "This",
        "Have",
        "Will",
        "With",
        "They",
        "Them",
        "Their",
        "Been",
        "Were",
        "Must",
        "Shall",
        "Very",
        "Good",
        "Too",
        "Like",
        "Just",
    }
)


def _strip_ass_tags(text: str) -> str:
    """Remove ASS override tag blocks from a subtitle line."""
    return _ASS_TAG_RE.sub("", text)


def _classify_term(term: str) -> str:
    """Classify a candidate term as 'place', 'character', or 'other'.

    Args:
        term: The candidate term string (may be one or two words).

    Returns:
        One of 'place', 'character', 'other'.
    """
    lower_words = {w.lower() for w in term.split()}
    if lower_words & _PLACE_INDICATORS:
        return "place"
    if len(term.split()) == 1:
        return "character"
    return "other"


def _collect_texts(directory: str, source_lang: str) -> list[str]:
    """Walk *directory* recursively and collect all subtitle event texts.

    Looks for files matching ``*.{source_lang}.ass`` and ``*.{source_lang}.srt``.
    Parse errors are logged as warnings and the file is skipped.

    Args:
        directory: Root directory to search.
        source_lang: Language tag used in sidecar filenames (e.g. ``"en"``).

    Returns:
        List of raw event text strings (ASS tags not yet stripped).
    """
    suffixes = (f".{source_lang}.ass", f".{source_lang}.srt")
    texts: list[str] = []

    for root, _dirs, files in os.walk(directory):
        for filename in files:
            if not any(filename.endswith(sfx) for sfx in suffixes):
                continue
            filepath = os.path.join(root, filename)
            try:
                subs = pysubs2.load(filepath, encoding="utf-8")
                for event in subs:
                    if event.text:
                        texts.append(event.text)
            except Exception as exc:  # noqa: BLE001
                logger.warning("glossary_extractor: could not parse %s — %s", filepath, exc)

    return texts


def _tokenize(texts: list[str]) -> Counter:
    """Extract proper-noun candidates from subtitle texts and count frequencies.

    Two-word combos are counted as a unit; their constituent single words are
    *not* additionally counted when they appear as part of a combo hit.

    Args:
        texts: Raw subtitle event text strings.

    Returns:
        Counter mapping candidate term → occurrence count.
    """
    counter: Counter = Counter()

    for raw in texts:
        clean = _strip_ass_tags(raw)

        # Extract two-word combos first
        two_word_matches = list(_TWO_WORD_PROPER_RE.finditer(clean))
        two_word_spans: list[tuple[int, int]] = []
        for m in two_word_matches:
            combo = f"{m.group(1)} {m.group(2)}"
            if m.group(1) not in _STOPWORDS and m.group(2) not in _STOPWORDS:
                counter[combo] += 1
                two_word_spans.append((m.start(), m.end()))

        # Extract single proper nouns, skipping positions covered by two-word combos
        for m in _SINGLE_PROPER_RE.finditer(clean):
            word = m.group(1)
            if word in _STOPWORDS:
                continue
            # Skip if this single word is entirely inside a two-word combo span
            if any(start <= m.start() and m.end() <= end for start, end in two_word_spans):
                continue
            counter[word] += 1

    return counter


def extract_candidates(
    directory: str,
    source_lang: str = "en",
    min_freq: int = 3,
    max_candidates: int = 200,
) -> list[dict[str, Any]]:
    """Extract frequency-based proper-noun candidates from subtitle sidecars.

    Scans *directory* recursively for ``*.{source_lang}.ass`` and
    ``*.{source_lang}.srt`` files, tokenizes their text, and returns a ranked
    list of term candidates.

    Args:
        directory: Root path to search for subtitle files.
        source_lang: Language tag used in sidecar filenames (e.g. ``"en"``).
        min_freq: Minimum occurrence count to include a candidate.
        max_candidates: Maximum number of candidates to return.

    Returns:
        List of dicts with keys ``source_term``, ``term_type``, ``frequency``,
        ``confidence``, sorted by frequency descending, capped at
        *max_candidates*.  Returns an empty list if the directory does not
        exist or no matching files are found.
    """
    if not os.path.isdir(directory):
        logger.debug("glossary_extractor: directory does not exist: %s", directory)
        return []

    texts = _collect_texts(directory, source_lang)
    if not texts:
        return []

    counter = _tokenize(texts)

    results: list[dict[str, Any]] = []
    for term, freq in counter.most_common():
        if freq < min_freq:
            break  # most_common() is sorted descending, so we can stop early
        term_type = _classify_term(term)
        confidence = round(min(0.5 + freq / 100, 0.99), 3)
        results.append(
            {
                "source_term": term,
                "term_type": term_type,
                "frequency": freq,
                "confidence": confidence,
            }
        )

    return results[:max_candidates]
