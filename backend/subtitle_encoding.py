"""Turn a subtitle's raw bytes into UTF-8, whatever they were encoded in.

Providers hand Sublarr the bytes as the uploader saved them: UTF-8 mostly, but
plenty of SRTs are still Windows-1250/1251/1252/1253, and the odd one is UTF-16.
The catalog bundles leave the encoding to the host on purpose ("Do not guess an
encoding"), so this is the one place that has to get it right.

It runs before anything parses the text. The sanitizer, the format checks and
the provider-language check all read UTF-8; whatever was not UTF-8 by then has
already lost its umlauts, Cyrillic or Greek to U+FFFD, and no later step can
bring them back.

Order of evidence, strongest first:

1. a byte-order mark (UTF-8/16/32), then UTF-16 recognised by its NUL bytes;
2. strict UTF-8 — legacy text almost never decodes as UTF-8 by accident;
3. an encoding the provider detected itself (``hint``), unless it is the
   "not UTF-8, so latin-1" placeholder several bundles return;
4. the codepages the subtitle's language was written in before UTF-8;
5. chardet, limited to codecs subtitles are really saved in;
6. Windows-1252 with replacement characters.

chardet alone is not enough: on a short file it picks whatever scores best, and
for a three-cue German subtitle that can be Big5 ("Gr晧e"). The language is
almost always known, and is a far better guide. Every candidate except UTF-8 must
also decode without C1 control characters (U+0080–U+009F): real subtitles never
contain them, but a single-byte text read with the wrong codepage nearly always
does.
"""

from __future__ import annotations

import codecs
import logging
import re
from typing import NamedTuple

logger = logging.getLogger(__name__)

_FALLBACK_ENCODING = "windows-1252"

# chardet only needs a sample; a 15 MB typeset ASS would take seconds otherwise.
_CHARDET_SAMPLE_BYTES = 64 * 1024

_C1_CONTROLS = re.compile("[\x80-\x9f]")

# BOMs, longest first: the UTF-32-LE mark begins with the UTF-16-LE one. The
# UTF-8 BOM is not here: editors put it in front of cp1252 text too, so it is
# stripped and the body goes through the same checks as any other.
_BOMS = (
    (codecs.BOM_UTF32_LE, "utf-32-le"),
    (codecs.BOM_UTF32_BE, "utf-32-be"),
    (codecs.BOM_UTF16_LE, "utf-16-le"),
    (codecs.BOM_UTF16_BE, "utf-16-be"),
)

# What bundles report when they only know the body is not UTF-8. Trusting it
# would read Greek, Hebrew or Cyrillic as Latin-1.
_PLACEHOLDER_HINTS = frozenset({"latin-1", "latin1", "iso-8859-1", "iso8859-1", "ascii"})

_WESTERN_LANGUAGES = "af ca da de en es eu fi fo fr ga gl id is it ms nb nl nn no pt sq sv sw"
_CENTRAL_LANGUAGES = "bs cs hr hu pl ro sk sl"
_BALTIC_LANGUAGES = "et lt lv"

# ISO 639-1 -> the legacy codepages subtitles in that language were saved in.
_SINGLE_BYTE_CODECS: dict[str, tuple[str, ...]] = {
    **dict.fromkeys(_WESTERN_LANGUAGES.split(), ("windows-1252",)),
    **dict.fromkeys(_CENTRAL_LANGUAGES.split(), ("windows-1250", "iso-8859-2")),
    **dict.fromkeys(("be", "bg", "mk", "ru", "uk"), ("windows-1251", "koi8-r")),
    "el": ("windows-1253", "iso-8859-7"),
    "tr": ("windows-1254", "iso-8859-9"),
    **dict.fromkeys(("he", "yi"), ("windows-1255", "iso-8859-8")),
    **dict.fromkeys(("ar", "fa", "ur"), ("windows-1256", "iso-8859-6")),
    **dict.fromkeys(_BALTIC_LANGUAGES.split(), ("windows-1257", "iso-8859-13")),
    "vi": ("windows-1258",),
    "th": ("cp874",),
}

# Languages in Latin script. A legacy decode of theirs that is mostly non-ASCII
# letters is not the language but a multi-byte file read one byte at a time
# (GBK read as cp1252 is "ÄãºÃ£¬"); even Vietnamese stays well under half.
_LATIN_SCRIPT_LANGUAGES = frozenset(
    (_WESTERN_LANGUAGES + " " + _CENTRAL_LANGUAGES + " " + _BALTIC_LANGUAGES + " tr vi").split()
)
_MAX_NON_ASCII_LETTER_SHARE = 0.5
_MIN_LETTERS_TO_JUDGE = 20

# Multi-byte codepages decode almost any byte string strictly, so a strict
# decode proves nothing: for these languages chardet chooses among them first.
_MULTI_BYTE_CODECS: dict[str, tuple[str, ...]] = {
    "zh": ("gb18030", "big5", "big5hkscs", "gbk", "gb2312"),
    "ja": ("cp932", "shift_jis", "euc_jp", "iso2022_jp"),
    "ko": ("cp949", "euc_kr"),
}

# What chardet may answer when the language gives no guidance.
_CHARDET_ALLOWED = frozenset(
    codecs.lookup(name).name
    for name in (
        *{c for group in _SINGLE_BYTE_CODECS.values() for c in group},
        *{c for group in _MULTI_BYTE_CODECS.values() for c in group},
        "iso-8859-15",
        "koi8-u",
        "cp866",
        "utf-8",
        "utf-16",
        "utf-32",
    )
)


def _codec_name(encoding: str | None) -> str | None:
    if not encoding:
        return None
    try:
        return codecs.lookup(encoding).name
    except LookupError:
        return None


def _base_language(language: str | None) -> str:
    """'pt-BR' / 'zh_Hans' / 'ger' / 'DE' -> 'pt' / 'zh' / 'de' / 'de'."""
    from config_language_data import normalize_language_code

    code = normalize_language_code(language or "")
    return re.split(r"[-_]", code, maxsplit=1)[0]


def _bomless_utf16_codec(data: bytes) -> str | None:
    """UTF-16 without a BOM: ASCII-heavy text leaves a NUL in every other byte."""
    head = data[:2048]
    if len(head) < 8:
        return None
    half = len(head) // 2
    odd, even = head[1::2].count(0), head[0::2].count(0)
    if odd > half * 0.4 and even < half * 0.05:
        return "utf-16-le"
    if even > half * 0.4 and odd < half * 0.05:
        return "utf-16-be"
    return None


def is_wide_unicode(data: bytes) -> bool:
    """True for UTF-16/UTF-32 text, with or without a BOM.

    Byte-level checks (NUL counts, binary signatures, ASCII format markers) get
    these wrong, so callers convert them before checking. Everything else is
    checked as it arrived: converting first would let a binary signature such as
    ``\x89PNG`` turn into harmless-looking text before anyone looked at it.
    """
    return any(data.startswith(bom) for bom, _ in _BOMS) or bool(_bomless_utf16_codec(data))


def _strict(data: bytes, encoding: str) -> str | None:
    try:
        text = data.decode(encoding)
    except (UnicodeDecodeError, LookupError):
        return None
    return None if _C1_CONTROLS.search(text) else text


def _plausible_for(text: str, base_language: str) -> bool:
    if base_language not in _LATIN_SCRIPT_LANGUAGES:
        return True
    letters = [c for c in text if c.isalpha()]
    if len(letters) < _MIN_LETTERS_TO_JUDGE:
        return True
    non_ascii = sum(1 for c in letters if not c.isascii())
    return non_ascii / len(letters) <= _MAX_NON_ASCII_LETTER_SHARE


def _chardet_candidates(data: bytes) -> list[str]:
    try:
        import chardet
    except ImportError:
        return []
    names = []
    for guess in chardet.detect_all(data[:_CHARDET_SAMPLE_BYTES]) or []:
        name = _codec_name(guess.get("encoding"))
        if name and name not in names:
            names.append(name)
    return names


class Decoded(NamedTuple):
    """A decode and what it rests on.

    ``basis`` is the evidence that picked ``encoding``: "bom", "utf-8", "hint",
    "language", "chardet" or "fallback". Code that rewrites files on its own
    (the subtitle-health re-encoder) acts only on the first four.
    """

    text: str
    encoding: str
    basis: str


def detect_encoding(data: bytes, language: str | None = None, hint: str | None = None) -> Decoded:
    """Decode subtitle bytes; never raises, never returns mojibake knowingly.

    Args:
        data: The raw file bytes.
        language: The subtitle's language ("de", "pt-BR", "ger", ...), if known.
        hint: An encoding the provider detected itself, if any.
    """
    # The encodings reported for BOM files are the ones that write the BOM back
    # ("utf-8-sig", "utf-16"), so a caller saving in the source encoding keeps it.
    for bom, encoding in _BOMS:
        if data.startswith(bom):
            text = data[len(bom) :].decode(encoding, errors="replace")
            return Decoded(text, encoding[:6], "bom")
    utf8_bom = data.startswith(codecs.BOM_UTF8)
    if utf8_bom:
        data = data[len(codecs.BOM_UTF8) :]
    codec = _bomless_utf16_codec(data)
    if codec:
        return Decoded(data.decode(codec, errors="replace"), codec, "bom")
    try:
        text = data.decode("utf-8")
        return Decoded(text, "utf-8-sig", "bom") if utf8_bom else Decoded(text, "utf-8", "utf-8")
    except UnicodeDecodeError:
        pass

    hint_name = _codec_name(hint)
    if hint_name and hint.strip().lower() not in _PLACEHOLDER_HINTS:
        text = _strict(data, hint_name)
        if text is not None:
            return Decoded(text, hint_name, "hint")

    base = _base_language(language)
    for encoding in _SINGLE_BYTE_CODECS.get(base, ()):
        text = _strict(data, encoding)
        if text is not None and _plausible_for(text, base):
            return Decoded(text, codecs.lookup(encoding).name, "language")

    candidates = _chardet_candidates(data)
    family = _MULTI_BYTE_CODECS.get(base)
    if family:
        wanted = {_codec_name(c) for c in family}
        ordered = [c for c in candidates if c in wanted]
        ordered += [_codec_name(c) for c in family if _codec_name(c) not in ordered]
    else:
        ordered = [c for c in candidates if c in _CHARDET_ALLOWED]
    for encoding in ordered:
        text = _strict(data, encoding)
        if text is not None:
            return Decoded(text, encoding, "language" if family else "chardet")

    logger.debug(
        "No encoding fits (language=%r, chardet=%s); reading as %s",
        language,
        candidates[:3],
        _FALLBACK_ENCODING,
    )
    return Decoded(
        data.decode(_FALLBACK_ENCODING, errors="replace"),
        codecs.lookup(_FALLBACK_ENCODING).name,
        "fallback",
    )


def decode_subtitle_bytes(data: bytes, language: str | None = None, hint: str | None = None) -> str:
    """Decode subtitle bytes to str (see :func:`detect_encoding`)."""
    return detect_encoding(data, language=language, hint=hint).text


def ensure_utf8(data: bytes, language: str | None = None, hint: str | None = None) -> bytes:
    """Return ``data`` as UTF-8 bytes; valid UTF-8 comes back as the same object.

    Leaving valid UTF-8 (BOM included) byte-for-byte alone keeps the hashes of
    everything already on disk stable: only content that was being mangled
    changes. A UTF-16/32 BOM is dropped with the conversion — it described the
    old encoding, not the new one.
    """
    if not data:
        return data
    # ASCII-only UTF-16 is valid UTF-8 — with a NUL after every character.
    if b"\x00" not in data[:2048]:
        try:
            data.decode("utf-8")
            return data
        except UnicodeDecodeError:
            pass
    return decode_subtitle_bytes(data, language=language, hint=hint).encode("utf-8")


def read_subtitle_text(path: str, *, universal_newlines: bool = True) -> Decoded:
    """Read a subtitle file as text, using the language in its file name.

    ``universal_newlines`` mirrors ``open(..., "r")``: CRLF and CR become LF,
    which is what the editor and the preview always received.
    """
    from subtitle_filename import parse_subtitle_filename

    with open(path, "rb") as fh:
        raw = fh.read()
    parsed = parse_subtitle_filename(path)
    decoded = detect_encoding(raw, language=parsed.language if parsed else None)
    if universal_newlines:
        text = decoded.text.replace("\r\n", "\n").replace("\r", "\n")
        decoded = decoded._replace(text=text)
    return decoded


def load_subtitle_file(path: str, format_: str | None = None, fps: float | None = None, **kwargs):
    """``pysubs2.load`` for files Sublarr did not write itself.

    ``pysubs2.load`` reads UTF-8 only and raises on a cp1252 umlaut; existing
    sidecars (from Bazarr, a user, an old download) are often legacy-encoded.
    Saved again, they come out as UTF-8.
    """
    import pysubs2

    text = read_subtitle_text(path).text
    return pysubs2.SSAFile.from_string(text, format_=format_, fps=fps, **kwargs)
