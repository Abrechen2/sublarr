"""Whether a subtitle's words are in the language it claims.

The script check (``subtitle_script``) catches Chinese under ``.de``; it cannot
tell Indonesian from English, both Latin. Prod 2026-11 held 131 downloaded
``.de``/``.en`` files in another Latin-script language — Indonesian,
Vietnamese, Catalan, Spanish, English under ``.de`` — taken on a provider's or
an attachment's word.

This module reads the dialogue and asks a language detector. It is built to
stay silent unless the case is gross: only languages from a fixed set are
judged, the text must be long enough, and a verdict needs the detector to be
sure of another language *and* to give the claimed one almost no chance. The
detector runs in low-accuracy mode (trigrams only): on a few thousand
characters of dialogue it reads as well as the full models, at a fraction of
their memory — this runs on Raspberry Pis too.
"""

from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)

#: Languages the detector knows. A claimed language outside this set is not
#: judged; one inside it is compared against all of them. The set covers what
#: providers actually mislabel (measured on prod 2026-11-08).
_LANGUAGE_NAMES = (
    "ARABIC", "CATALAN", "CHINESE", "CZECH", "DUTCH", "ENGLISH", "FRENCH", "GERMAN",
    "GREEK", "HEBREW", "HUNGARIAN", "INDONESIAN", "ITALIAN", "JAPANESE", "KOREAN",
    "MALAY", "POLISH", "PORTUGUESE", "ROMANIAN", "RUSSIAN", "SPANISH", "SWEDISH",
    "THAI", "TURKISH", "VIETNAMESE",
)  # fmt: skip

#: Fewer characters of dialogue than this give no verdict.
MIN_CHARS = 1500
#: The middle of the file is sampled, up to this many characters: openings
#: and endings carry credits, song lyrics and staff notes in other languages.
_SAMPLE_CHARS = 6000
#: A mismatch needs the detected language above DETECTED_MIN and the claimed
#: one below CLAIMED_MAX. On prod these bars flagged no correctly labelled file.
DETECTED_MIN = 0.5
CLAIMED_MAX = 0.2

_detector = None
_codes: dict = {}
_lock = threading.Lock()


def _get_detector():
    global _detector
    with _lock:
        if _detector is None:
            from lingua import Language, LanguageDetectorBuilder

            languages = [getattr(Language, name) for name in _LANGUAGE_NAMES]
            _codes.update({lang: lang.iso_code_639_1.name.lower() for lang in languages})
            _detector = (
                LanguageDetectorBuilder.from_languages(*languages).with_low_accuracy_mode().build()
            )
    return _detector


def _dialogue_sample(content: bytes) -> str:
    """Up to _SAMPLE_CHARS of dialogue from the middle of the file; "" if unreadable."""
    from subtitle_dialogue import _parse, _visible_events

    parsed = _parse(content)
    if parsed is None:
        return ""
    subs, is_ass = parsed
    dialog_styles = None
    if is_ass:
        from ass_utils import classify_styles

        dialog_styles, _signs = classify_styles(subs)
    lines = [
        plain.replace("\n", " ")
        for _event, plain, is_dialogue in _visible_events(subs, dialog_styles)
        if is_dialogue
    ]
    # Drawings and \pos-placed typesetting survive _plain as short fragments.
    lines = [line for line in lines if len(line) > 3]
    if not lines:
        return ""
    middle = len(lines) // 2
    sample: list[str] = []
    size = 0
    for line in lines[middle:] + lines[:middle]:
        sample.append(line)
        size += len(line) + 1
        if size >= _SAMPLE_CHARS:
            break
    # One oversized line must not carry the whole file to the detector.
    return " ".join(sample)[:_SAMPLE_CHARS]


def language_mismatch(content: bytes, claimed: str) -> str | None:
    """Why ``content`` is not in the ``claimed`` language, or None.

    None also when the language is not judged, the text is too short, or the
    check cannot run — this guards against the gross case and must never
    block a download on its own failure.
    """
    from config_language_data import normalize_language_code

    want = normalize_language_code(claimed or "").split("-", 1)[0]
    if not want or not content:
        return None
    try:
        detector = _get_detector()
        if want not in _codes.values():
            return None
        sample = _dialogue_sample(content)
        if len(sample) < MIN_CHARS:
            return None
        values = {
            _codes[v.language]: v.value for v in detector.compute_language_confidence_values(sample)
        }
    except Exception as exc:  # noqa: BLE001 — no verdict rather than a failed download
        logger.debug("Content language check skipped: %s", exc)
        return None
    if not values:
        return None
    top = max(values, key=values.get)
    if top == want or values[top] < DETECTED_MIN or values.get(want, 0.0) >= CLAIMED_MAX:
        return None
    return (
        f"the dialogue reads as {top} ({values[top]:.2f}), not {want} ({values.get(want, 0.0):.2f})"
    )
