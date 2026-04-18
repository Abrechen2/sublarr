"""Pure parsing / decompression / detection helpers for AnimeToshoProvider.

Extracted from providers/animetosho.py. These functions are pure — they
don't touch the provider instance or any HTTP session, so they belong
naturally in a sibling module that the provider class imports.

- ``_decompress_xz``        — bomb-safe XZ/LZMA decompression (capped at
                              ``_MAX_DECOMPRESSED_SIZE`` bytes).
- ``_extract_episode_number`` — pull the absolute episode number out of
                                a release name using common anime
                                fansub patterns.
- ``_detect_language``      — infer the subtitle language from a
                              filename + optional release title,
                              falling back to well-known fansub-group
                              heuristics.
- ``_ISO639_2_TO_1``         — AnimeTosho attachment ``info.lang`` field
                              uses 3-letter codes; this table maps them
                              to the 2-letter codes Sublarr standardises on.
"""

import logging
import lzma
import re

from archive_utils import _MAX_EXTRACTED_BYTES

logger = logging.getLogger(__name__)

# ISO 639-2b → 2-letter code mapping for AnimeTosho attachment info.lang field
_ISO639_2_TO_1 = {
    "eng": "en",
    "jpn": "ja",
    "deu": "de",
    "ger": "de",
    "fre": "fr",
    "fra": "fr",
    "spa": "es",
    "por": "pt",
    "rus": "ru",
    "zho": "zh",
    "chi": "zh",
    "kor": "ko",
    "ara": "ar",
    "nld": "nl",
    "dut": "nl",
    "pol": "pl",
    "swe": "sv",
    "ces": "cs",
    "cze": "cs",
    "hun": "hu",
    "tur": "tr",
    "ita": "it",
}

_MAX_DECOMPRESSED_SIZE = _MAX_EXTRACTED_BYTES  # aligned with archive extraction limit


def _decompress_xz(data: bytes) -> bytes:
    """Decompress XZ/LZMA compressed data, rejecting bombs larger than 10 MB."""
    try:
        result = lzma.decompress(data)
    except lzma.LZMAError as e:
        logger.warning("AnimeTosho: XZ decompression failed: %s", e)
        raise
    if len(result) > _MAX_DECOMPRESSED_SIZE:
        raise ValueError(
            f"AnimeTosho: decompressed data exceeds {_MAX_DECOMPRESSED_SIZE // (1024 * 1024)} MB limit"
        )
    return result


def _extract_episode_number(text: str) -> int | None:
    """Try to extract episode number from a release name."""
    # Common patterns: " - 01 ", " E01 ", " EP01 ", "_01_", " 01v2 "
    patterns = [
        r"[\s_]-[\s_](\d{2,3})(?:v\d)?[\s_\[\(.]",  # " - 01 " or " - 01v2 "
        r"[Ee][Pp]?(\d{2,3})(?:v\d)?[\s_\[\(.]",  # E01, EP01
        r"[\s_](\d{2,3})(?:v\d)?[\s_]?(?:\[|\(|\.(?:mkv|mp4))",  # " 01 [" or " 01."
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                continue
    return None


def _detect_language(filename: str, release_title: str = "") -> str:
    """Detect language from subtitle filename and release context."""
    name_lower = filename.lower()
    title_lower = release_title.lower()

    # Explicit language tags in filename (check filename first, then title)
    lang_patterns = {
        "ja": [".ja.", ".jpn.", ".japanese.", "_ja_", "_jpn_", "[ja]", "[jpn]"],
        "en": [".en.", ".eng.", ".english.", "_en_", "_eng_", "[en]", "[eng]"],
        "de": [
            ".de.",
            ".deu.",
            ".ger.",
            ".german.",
            "_de_",
            "_deu_",
            "[de]",
            "[deu]",
            "[ger]",
            ".german",
        ],
        "fr": [".fr.", ".fra.", ".fre.", ".french.", "_fr_", "[fr]", "[fra]"],
        "es": [".es.", ".spa.", ".spanish.", "_es_", "[es]", "[spa]"],
        "zh": [".zh.", ".chi.", ".chinese.", "_zh_", "[zh]", "[chi]"],
    }

    # Check filename first
    for lang, patterns in lang_patterns.items():
        if any(p in name_lower for p in patterns):
            return lang

    # Check release title for language tags
    for lang, patterns in lang_patterns.items():
        if any(p in title_lower for p in patterns):
            return lang

    # Check for common German fansub groups
    german_groups = ["kametsu", "anime4you", "anime-loads", "animebase", "animefreakz"]
    if any(group in title_lower for group in german_groups):
        return "de"

    # Check for common English fansub groups
    english_groups = [
        "subsplease",
        "erai-raws",
        "horriblesubs",
        "judas",
        "sallysubs",
        "yameii",
        "ember",
        "yor",
        "commie",
        "gg",
        "coal",
        "doki",
        "fumetsu",
        "utw",
        "asenshi",
    ]
    if any(group in title_lower for group in english_groups):
        return "en"

    # Default assumption for AnimeTosho (most fansubs are English)
    return "en"
