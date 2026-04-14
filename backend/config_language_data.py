"""Language tag data — ISO 639-1 to all known file/metadata variant mappings.

Extracted from config.py for size management. config.py re-exports everything
from this module for backwards compatibility.
"""

# Language tag mapping (ISO 639-1 -> all known file/metadata variants)
_LANGUAGE_TAGS: dict[str, set[str]] = {
    # Western Europe
    "de": {"de", "deu", "ger", "german"},
    "en": {"en", "eng", "english"},
    "fr": {"fr", "fra", "fre", "french"},
    "es": {"es", "spa", "spanish"},
    "it": {"it", "ita", "italian"},
    "pt": {"pt", "por", "portuguese"},
    "nl": {"nl", "nld", "dut", "dutch"},
    "sv": {"sv", "swe", "swedish"},
    "da": {"da", "dan", "danish"},
    "no": {"no", "nor", "norwegian"},
    "fi": {"fi", "fin", "finnish"},
    "is": {"is", "isl", "ice", "icelandic"},
    "eu": {"eu", "eus", "baq", "basque"},
    "ca": {"ca", "cat", "catalan"},
    "gl": {"gl", "glg", "galician"},
    # Eastern Europe
    "pl": {"pl", "pol", "polish"},
    "cs": {"cs", "ces", "cze", "czech"},
    "sk": {"sk", "slk", "slo", "slovak"},
    "hu": {"hu", "hun", "hungarian"},
    "ro": {"ro", "ron", "rum", "romanian"},
    "bg": {"bg", "bul", "bulgarian"},
    "hr": {"hr", "hrv", "croatian"},
    "sr": {"sr", "srp", "serbian"},
    "sl": {"sl", "slv", "slovenian"},
    "bs": {"bs", "bos", "bosnian"},
    "mk": {"mk", "mkd", "macedonian"},
    "sq": {"sq", "alb", "sqi", "albanian"},
    "lt": {"lt", "lit", "lithuanian"},
    "lv": {"lv", "lav", "latvian"},
    "et": {"et", "est", "estonian"},
    "uk": {"uk", "ukr", "ukrainian"},
    "ru": {"ru", "rus", "russian"},
    # Caucasus / Central Asia
    "hy": {"hy", "hye", "arm", "armenian"},
    "ka": {"ka", "kat", "geo", "georgian"},
    "az": {"az", "aze", "azerbaijani"},
    "kk": {"kk", "kaz", "kazakh"},
    "uz": {"uz", "uzb", "uzbek"},
    # Middle East
    "ar": {"ar", "ara", "arabic"},
    "he": {"he", "heb", "hebrew"},
    "fa": {"fa", "per", "fas", "persian"},
    "tr": {"tr", "tur", "turkish"},
    # South / Southeast Asia
    "hi": {"hi", "hin", "hindi"},
    "bn": {"bn", "ben", "bengali"},
    "ur": {"ur", "urd", "urdu"},
    "ta": {"ta", "tam", "tamil"},
    "te": {"te", "tel", "telugu"},
    "ml": {"ml", "mal", "malayalam"},
    "kn": {"kn", "kan", "kannada"},
    "si": {"si", "sin", "sinhala"},
    "th": {"th", "tha", "thai"},
    "vi": {"vi", "vie", "vietnamese"},
    "id": {"id", "ind", "indonesian"},
    "ms": {"ms", "msa", "may", "malay"},
    "tl": {"tl", "fil", "tagalog", "filipino"},
    # East Asia
    "ja": {"ja", "jpn", "japanese"},
    "ko": {"ko", "kor", "korean"},
    "zh": {"zh", "zho", "chi", "chinese"},
    "zh-hans": {"zh-hans", "zhs", "chs", "chi-sim", "chinese simplified"},
    "zh-hant": {"zh-hant", "zht", "cht", "chi-tra", "chinese traditional"},
    "mn": {"mn", "mon", "mongolian"},
    # Other
    "el": {"el", "ell", "gre", "greek"},
    "af": {"af", "afr", "afrikaans"},
    "sw": {"sw", "swa", "swahili"},
}

# Ordered list of supported languages for the UI language picker
SUPPORTED_LANGUAGES: list[dict] = [
    {"code": "af", "name": "Afrikaans"},
    {"code": "sq", "name": "Albanian"},
    {"code": "ar", "name": "Arabic"},
    {"code": "hy", "name": "Armenian"},
    {"code": "az", "name": "Azerbaijani"},
    {"code": "eu", "name": "Basque"},
    {"code": "bn", "name": "Bengali"},
    {"code": "bs", "name": "Bosnian"},
    {"code": "bg", "name": "Bulgarian"},
    {"code": "ca", "name": "Catalan"},
    {"code": "zh", "name": "Chinese"},
    {"code": "zh-hans", "name": "Chinese (Simplified)"},
    {"code": "zh-hant", "name": "Chinese (Traditional)"},
    {"code": "hr", "name": "Croatian"},
    {"code": "cs", "name": "Czech"},
    {"code": "da", "name": "Danish"},
    {"code": "nl", "name": "Dutch"},
    {"code": "en", "name": "English"},
    {"code": "et", "name": "Estonian"},
    {"code": "tl", "name": "Filipino"},
    {"code": "fi", "name": "Finnish"},
    {"code": "fr", "name": "French"},
    {"code": "gl", "name": "Galician"},
    {"code": "ka", "name": "Georgian"},
    {"code": "de", "name": "German"},
    {"code": "el", "name": "Greek"},
    {"code": "he", "name": "Hebrew"},
    {"code": "hi", "name": "Hindi"},
    {"code": "hu", "name": "Hungarian"},
    {"code": "is", "name": "Icelandic"},
    {"code": "id", "name": "Indonesian"},
    {"code": "it", "name": "Italian"},
    {"code": "ja", "name": "Japanese"},
    {"code": "kn", "name": "Kannada"},
    {"code": "kk", "name": "Kazakh"},
    {"code": "ko", "name": "Korean"},
    {"code": "lv", "name": "Latvian"},
    {"code": "lt", "name": "Lithuanian"},
    {"code": "mk", "name": "Macedonian"},
    {"code": "ms", "name": "Malay"},
    {"code": "ml", "name": "Malayalam"},
    {"code": "mn", "name": "Mongolian"},
    {"code": "no", "name": "Norwegian"},
    {"code": "fa", "name": "Persian"},
    {"code": "pl", "name": "Polish"},
    {"code": "pt", "name": "Portuguese"},
    {"code": "ro", "name": "Romanian"},
    {"code": "ru", "name": "Russian"},
    {"code": "sr", "name": "Serbian"},
    {"code": "si", "name": "Sinhala"},
    {"code": "sk", "name": "Slovak"},
    {"code": "sl", "name": "Slovenian"},
    {"code": "es", "name": "Spanish"},
    {"code": "sw", "name": "Swahili"},
    {"code": "sv", "name": "Swedish"},
    {"code": "ta", "name": "Tamil"},
    {"code": "te", "name": "Telugu"},
    {"code": "th", "name": "Thai"},
    {"code": "tr", "name": "Turkish"},
    {"code": "uk", "name": "Ukrainian"},
    {"code": "ur", "name": "Urdu"},
    {"code": "uz", "name": "Uzbek"},
    {"code": "vi", "name": "Vietnamese"},
]


def _get_language_tags(lang_code: str) -> set[str]:
    """Get all known tags for a language code."""
    return _LANGUAGE_TAGS.get(lang_code, {lang_code})


# Reverse lookup: any known tag -> canonical ISO 639-1 code.
# Built lazily/deterministically at module import time so callers get O(1) lookup.
_REVERSE_LANGUAGE_TAGS: dict[str, str] = {
    tag: code for code, tags in _LANGUAGE_TAGS.items() for tag in tags
}


def normalize_language_code(raw: str) -> str:
    """Map any known language tag to its canonical ISO 639-1 code.

    Examples:
      'ger', 'deu', 'german', 'DE' -> 'de'
      'eng', 'english' -> 'en'
      'jpn', 'japanese' -> 'ja'

    Unknown tags (including empty strings and 'und') are returned in
    lower-case/stripped form unchanged — callers decide whether to treat
    an unknown tag as "keep" (safer) or "discard" (stricter).
    """
    if not raw:
        return ""
    key = raw.lower().strip()
    return _REVERSE_LANGUAGE_TAGS.get(key, key)
