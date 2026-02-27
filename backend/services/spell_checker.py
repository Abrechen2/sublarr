"""Spell checking service using Hunspell/PyEnchant.

Provides multi-language spell checking for subtitle files, similar to SubtitleEdit.
Uses pyenchant (Python binding for Hunspell) for spell checking.
"""

import logging
import re

logger = logging.getLogger(__name__)

# Try to import pyenchant, but make it optional
try:
    import enchant
    ENCHANT_AVAILABLE = True
except ImportError:
    ENCHANT_AVAILABLE = False
    logger.warning("pyenchant not available. Spell checking will be disabled.")

# Export ENCHANT_AVAILABLE for use in routes
__all__ = ["SpellChecker", "check_subtitle_file", "get_available_dictionaries", "ENCHANT_AVAILABLE"]


class SpellChecker:
    """Spell checker using PyEnchant/Hunspell."""

    def __init__(self, language: str = "en_US"):
        """Initialize spell checker for a specific language.

        Args:
            language: Language code (e.g., "en_US", "de_DE", "fr_FR")
        """
        if not ENCHANT_AVAILABLE:
            raise RuntimeError("pyenchant not available. Install it to enable spell checking.")

        self.language = language
        try:
            self.dict = enchant.Dict(language)
        except enchant.DictNotFoundError:
            logger.warning("Dictionary not found for %s, trying fallback", language)
            # Try fallback: en_US -> en, de_DE -> de
            fallback = language.split("_")[0]
            try:
                self.dict = enchant.Dict(fallback)
                self.language = fallback
            except enchant.DictNotFoundError:
                raise RuntimeError(f"Dictionary not found for {language} or {fallback}")

        # Custom word list (e.g., from glossary)
        self.custom_words: set[str] = set()

    def add_custom_words(self, words: list[str]):
        """Add custom words to ignore list (e.g., character names, locations).

        Args:
            words: List of words to add to custom dictionary
        """
        self.custom_words.update(word.lower() for word in words)

    def check_word(self, word: str) -> bool:
        """Check if a word is spelled correctly.

        Args:
            word: Word to check

        Returns:
            True if word is correct or in custom dictionary
        """
        if not word:
            return True

        # Clean word (remove punctuation, etc.)
        clean_word = self._clean_word(word)
        if not clean_word:
            return True

        # Check custom words first
        if clean_word.lower() in self.custom_words:
            return True

        # Check with dictionary
        return self.dict.check(clean_word)

    def suggest(self, word: str, max_suggestions: int = 5) -> list[str]:
        """Get spelling suggestions for a word.

        Args:
            word: Misspelled word
            max_suggestions: Maximum number of suggestions

        Returns:
            List of suggested corrections
        """
        if not word:
            return []

        clean_word = self._clean_word(word)
        if not clean_word:
            return []

        try:
            suggestions = self.dict.suggest(clean_word)
            return suggestions[:max_suggestions]
        except Exception as e:
            logger.debug("Failed to get suggestions for %s: %s", word, e)
            return []

    def check_text(self, text: str) -> list[dict]:
        """Check spelling in a text string.

        Args:
            text: Text to check

        Returns:
            List of dicts with "word", "position", "suggestions" keys
        """
        if not ENCHANT_AVAILABLE:
            return []

        errors = []
        words = self._extract_words(text)

        for word, position in words:
            if not self.check_word(word):
                suggestions = self.suggest(word)
                errors.append({
                    "word": word,
                    "position": position,
                    "suggestions": suggestions,
                })

        return errors

    def _clean_word(self, word: str) -> str:
        """Remove punctuation and normalize word for checking.

        Args:
            word: Raw word

        Returns:
            Cleaned word
        """
        # Remove leading/trailing punctuation
        word = word.strip(".,!?;:\"'()[]{}")
        # Remove ASS tags (e.g., {\an8}, {\pos()})
        word = re.sub(r"\{[^}]*\}", "", word)
        # Remove HTML-like tags
        word = re.sub(r"<[^>]+>", "", word)
        # Remove special characters (keep letters, numbers, hyphens, apostrophes)
        word = re.sub(r"[^\w\s'-]", "", word)
        return word.strip()

    def _extract_words(self, text: str) -> list[tuple[str, int]]:
        """Extract words from text with their positions.

        Args:
            text: Text to extract words from

        Returns:
            List of (word, position) tuples
        """
        words = []
        # Remove ASS override tags first
        text_clean = re.sub(r"\{[^}]*\}", " ", text)
        # Split by whitespace
        parts = re.split(r"(\s+)", text_clean)
        position = 0

        for part in parts:
            if not part.strip():
                position += len(part)
                continue

            # Check if it's a word (contains letters)
            if re.search(r"[a-zA-Z]", part):
                words.append((part, position))

            position += len(part)

        return words


def check_subtitle_file(
    file_path: str,
    language: str = "en_US",
    custom_words: list[str] | None = None,
) -> dict:
    """Check spelling in a subtitle file.

    Args:
        file_path: Path to subtitle file
        language: Language code for spell checking
        custom_words: Optional list of custom words (e.g., from glossary)

    Returns:
        Dict with "errors" (list of errors) and "total_words" (int)
    """
    if not ENCHANT_AVAILABLE:
        return {
            "errors": [],
            "total_words": 0,
            "error": "Spell checking not available (pyenchant not installed)",
        }

    try:
        import pysubs2

        # Load subtitle file
        subs = pysubs2.load(file_path)

        # Initialize spell checker
        checker = SpellChecker(language)
        if custom_words:
            checker.add_custom_words(custom_words)

        all_errors = []
        total_words = 0

        # Check each event
        for event in subs.events:
            if event.is_comment:
                continue

            # Extract plain text (remove ASS tags)
            text = event.plaintext
            if not text:
                continue

            # Check spelling
            errors = checker.check_text(text)
            for error in errors:
                all_errors.append({
                    **error,
                    "line": event.index + 1,
                    "text": text,
                    "start_time": event.start,
                    "end_time": event.end,
                })

            # Count words
            words = checker._extract_words(text)
            total_words += len(words)

        return {
            "errors": all_errors,
            "total_words": total_words,
            "error_count": len(all_errors),
        }

    except Exception as e:
        logger.exception("Spell checking failed for %s", file_path)
        return {
            "errors": [],
            "total_words": 0,
            "error": str(e),
        }


def get_available_dictionaries() -> list[str]:
    """Get list of available dictionary languages.

    Returns:
        List of language codes (e.g., ["en_US", "de_DE", "fr_FR"])
    """
    if not ENCHANT_AVAILABLE:
        return []

    try:
        # Get list of available dictionaries
        brokers = enchant.Broker()
        dicts = brokers.list_dicts()
        return [lang for lang, _ in dicts]
    except Exception as e:
        logger.warning("Failed to list dictionaries: %s", e)
        return []
