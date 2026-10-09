"""Language codes between Sublarr (ISO 639-1) and Provider Hub bundles (ISO 639-3).

Sublarr names a language by its two-letter code plus two script variants
(``zh-hans``/``zh-hant``) and folds Brazilian Portuguese into ``pt``. The
bundles speak ``{"alpha3": "por", "country_alpha2": "BR", ...}`` and declare
codes like ``por-BR``, ``zho-Hant`` and ``sr-Cyrl`` in their manifests.

Every conversion goes through Sublarr's own tag table first and babelfish
second, so a language Sublarr knows by a legacy spelling ("ger", "chi")
resolves the same way everywhere, and the long tail (Belarusian, Khmer,
Yoruba, ...) still converts instead of being dropped.
"""

from __future__ import annotations

from config_language_data import normalize_language_code

try:
    import babelfish
except ImportError:  # pragma: no cover — babelfish ships with guessit
    babelfish = None

_SCRIPT_VARIANTS = {"zh-hans": ("zho", "Hans"), "zh-hant": ("zho", "Hant")}
# Bundles follow the Bazarr convention for Chinese: a country, not a script
# (zho-CN Simplified, zho-TW Traditional). Send and read both.
_SCRIPT_COUNTRY = {"zh-hans": "CN", "zh-hant": "TW"}
# Regional variants Sublarr folds into the base language. Asking for both
# spellings lets a bundle that only answers one of them still be heard.
_EXTRA_REQUEST_VARIANTS = {"pt": [{"country_alpha2": "BR"}]}
# Countries that imply a script for Chinese when a bundle sends no script.
_HANT_COUNTRIES = {"TW", "HK", "MO"}
_HANS_COUNTRIES = {"CN", "SG"}


def to_alpha3(code: str) -> str:
    """Three-letter (ISO 639-3) code for a Sublarr language code, or ""."""
    key = normalize_language_code(code or "")
    if key in _SCRIPT_VARIANTS:
        return _SCRIPT_VARIANTS[key][0]
    base = key.split("-", 1)[0]
    if len(base) == 3:
        return base
    if babelfish is not None and len(base) == 2:
        try:
            return babelfish.Language.fromalpha2(base).alpha3
        except (ValueError, babelfish.Error):
            return ""
    return ""


def to_sublarr(alpha3: str) -> str:
    """Sublarr's code for a three-letter code: alpha-2 where one exists."""
    key = (alpha3 or "").strip().lower()
    if not key:
        return ""
    known = normalize_language_code(key)
    if len(known) == 2 or known in _SCRIPT_VARIANTS:
        return known
    if babelfish is not None:
        try:
            return babelfish.Language(key).alpha2
        except (ValueError, babelfish.Error):
            pass
    return key


def request_payloads(codes: list[str]) -> list[dict]:
    """The ``languages`` argument a bundle's ``search`` expects."""
    payloads: list[dict] = []
    for code in codes or []:
        alpha3 = to_alpha3(code)
        if not alpha3:
            continue
        base = {"alpha3": alpha3, "hi": False, "forced": False}
        alpha2 = to_sublarr(alpha3)
        if len(alpha2) == 2:
            base["alpha2"] = alpha2
        key = normalize_language_code(code)
        if key in _SCRIPT_VARIANTS:
            base["script"] = _SCRIPT_VARIANTS[key][1]
            base["country_alpha2"] = _SCRIPT_COUNTRY[key]
        payloads.append(base)
        for extra in _EXTRA_REQUEST_VARIANTS.get(key, []):
            payloads.append({**base, **extra})
    return payloads


# Markers for Traditional Chinese in a file or release name — the same rule the
# built-in zimuku provider applies when a source does not say which script.
_HANT_MARKERS = ("繁", "cht", "big5", "traditional", ".tw.", ".hk.")


def result_language(payload, wanted: list[str], hint: str = "") -> str:
    """Sublarr code for a candidate's language, preferring one the search asked for.

    A Traditional Chinese candidate is ``zh-hant`` when the search asked for
    that, and plain ``zh`` when it asked for Chinese in general — the search
    coordinator drops any result whose language is not one of the query's.
    """
    if isinstance(payload, str):
        payload = {"alpha3": payload}
    if not isinstance(payload, dict):
        return ""
    raw = str(payload.get("alpha3") or payload.get("alpha2") or "").strip()
    script = str(payload.get("script") or "").strip()
    country = str(payload.get("country_alpha2") or payload.get("country") or "").strip().upper()
    if "-" in raw:
        raw, suffix = raw.split("-", 1)
        if len(suffix) == 4:
            script = script or suffix
        else:
            country = country or suffix.upper()
    base = to_sublarr(raw)
    if not base:
        return ""

    candidates = []
    if base == "zh":
        if script.lower() == "hant" or (not script and country in _HANT_COUNTRIES):
            candidates.append("zh-hant")
        elif script.lower() == "hans" or (not script and country in _HANS_COUNTRIES):
            candidates.append("zh-hans")
        elif not script and not country:
            # Unspecified: Traditional only when the name says so, else Simplified.
            lowered = (hint or "").lower()
            candidates.append("zh-hant" if any(m in lowered for m in _HANT_MARKERS) else "zh-hans")
    candidates.append(base)

    wanted_set = {normalize_language_code(c) for c in wanted or []}
    for candidate in candidates:
        if candidate in wanted_set:
            return candidate
    return candidates[0]


def manifest_languages(codes: list[str]) -> set[str]:
    """Sublarr codes a bundle serves, from the manifest's ``languages`` list."""
    served: set[str] = set()
    for code in codes or []:
        primary = result_language({"alpha3": code}, [])
        if primary:
            served.add(primary)
            # A bundle that serves Chinese answers searches for either script;
            # the result's own country/script decides which one it is.
            if primary == "zh" or primary.startswith("zh-"):
                served |= {"zh", "zh-hans", "zh-hant"}
    return served
