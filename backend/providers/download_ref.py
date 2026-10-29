"""What a download needs beyond its id — kept so the repair can fetch it again.

Only OpenSubtitles, Podnapisi and SubSource download by id. Every other
provider downloads from the URL its search found, often with a payload next
to it (hub bundles), and neither can be rebuilt from the id: Subf2m's id is
the last segment of a page URL that also carries a slug. So the URL and the
provider data are saved with the download (in its decision log) and handed
back to ``download()`` when the repair re-fetches the file.

Saved data is shown in History and kept in the database, so no credential
goes in: query parameters and fields named like keys, tokens, cookies or
passwords are dropped, and so is anything that is not plain JSON.
"""

from __future__ import annotations

import json
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_SECRET_RE = re.compile(r"key|token|cookie|pass|secret|auth|session|sid$|signature", re.I)
_MAX_BYTES = 16_000
_DROP = object()


def _clean(value):
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if not isinstance(key, str) or _SECRET_RE.search(key):
                continue
            item = _clean(item)
            if item is not _DROP:
                out[key] = item
        return out
    if isinstance(value, list | tuple):
        return [item for item in (_clean(v) for v in value) if item is not _DROP]
    if isinstance(value, str):
        return _clean_url(value) if ("://" in value or "?" in value) else value
    if value is None or isinstance(value, bool | int | float):
        return value
    return _DROP


def _clean_url(url: str) -> str:
    """``url`` without credential query parameters and without ``user:pass@``."""
    parts = urlsplit(url)
    query = parse_qsl(parts.query, keep_blank_values=True)
    kept = [(k, v) for k, v in query if not _SECRET_RE.search(k)]
    netloc = parts.netloc.rpartition("@")[2]
    if len(kept) == len(query) and netloc == parts.netloc:
        return url
    return urlunsplit(parts._replace(netloc=netloc, query=urlencode(kept)))


def download_ref(result) -> dict | None:
    """The credential-free URL and provider data of ``result``; None when there is neither."""
    ref: dict = {}
    url = getattr(result, "download_url", "") or ""
    if isinstance(url, str) and url:
        ref["url"] = _clean_url(url)
    data = _clean(getattr(result, "provider_data", None) or {})
    if data and data is not _DROP and len(json.dumps(data)) <= _MAX_BYTES:
        ref["provider_data"] = data
    return ref or None


def apply_download_ref(result, ref: dict | None) -> None:
    """Put the saved details on the provider's rebuild; the saved ones win.

    They are what the file was downloaded from — the file whose hash the
    repair proves. A rebuild from the id is a guess at it (Custom API's URL
    template, when the search had returned its own URL).
    """
    if not isinstance(ref, dict):
        return
    if isinstance(ref.get("url"), str) and ref["url"]:
        result.download_url = ref["url"]
    data = ref.get("provider_data")
    if isinstance(data, dict):
        result.provider_data = {**(result.provider_data or {}), **data}
