"""Shared secret redaction for log records, the log viewer and the support bundle.

Two layers, applied in this order:

1. **Value pass** — every configured secret is replaced wherever it appears,
   whatever surrounds it: each non-default setting whose name
   ``is_sensitive_config_key()`` flags, the passwords inside ``database_url`` /
   ``redis_url`` and any other URL with userinfo, the tokens inside Apprise
   notification URLs, and the credentials nested in the ``*_json`` instance
   lists. A secret the regex layer cannot recognise (a password in an exception
   text, a key echoed back by a provider) is still caught here.
2. **Regex layer** — shapes that are secrets regardless of configuration: DSN
   passwords (``://user:pass@``), ``Bearer``/``Basic`` credentials, Discord and
   Slack webhook tokens, Telegram bot tokens, and ``key=value`` / ``key: value``
   pairs whose key names a credential, at any length and with any characters.

The regex layer replaced a deny-list that required 16+ characters from
``[A-Za-z0-9+/=_-]`` — which let ``password=hunter2pass``, DSN passwords,
bearer tokens and dotted keys straight into support bundles.

Cost: the value set is built once per settings object and cached; a settings
reload swaps the singleton, which the cache notices by identity, so the set
follows config changes without a DB read per record. A single prefilter regex
keeps the common log line (no trigger word) to one scan.

Failure policy: redaction must never cost a log record. The logging filter
fails open for the record and writes one warning to stderr (not through
logging, which would recurse); a failure while collecting values degrades to
the regex layer only.
"""

from __future__ import annotations

import json
import logging
import re
import sys
import threading
from collections.abc import Iterable
from urllib.parse import unquote, urlsplit

REDACTED = "***REDACTED***"

# Shorter configured values are not replaced by the value pass: a short PIN or a
# weak password that is also an ordinary word ("anime", "admin") would blank that
# word in every line of an anime library's log. The regex layer still catches
# them next to their key name (``password=anime``).
_MIN_VALUE_LEN = 6

# Values that say "nothing configured" — redacting them hides a useful fact
# (``api_key=None`` means the key is missing) and protects nothing.
_PLACEHOLDER_VALUES = frozenset({"none", "null", "undefined", "***", REDACTED.lower()})

# One cheap scan decides whether the regex layer has anything to look at.
_TRIGGER_RE = re.compile(
    r"(?i)pass|pwd|pin|token|secret|key|credential|bearer|basic|://|webhook|hooks\.slack|bot\d|\d{5,}:"
)

_DSN_RE = re.compile(r"(?i)(\b[a-z][a-z0-9+.\-]*://[^\s:/@'\"]*:)([^\s@'\"/]+)(@)")
_AUTH_SCHEME_RE = re.compile(r"(?i)\b(bearer|basic)(\s+)([A-Za-z0-9\-._~+/]{8,}=*)")
_DISCORD_WEBHOOK_RE = re.compile(r"(?i)(/api/webhooks/\d+/)([\w\-]+)")
_SLACK_WEBHOOK_RE = re.compile(r"(?i)(hooks\.slack\.com/services/)([\w/]+)")
_TELEGRAM_BOT_RE = re.compile(r"\b((?:bot)?\d{5,}:)([\w\-]{30,})")

_KV_KEYS = (
    r"(?:api[_-]?key|apikey|access[_-]?token|refresh[_-]?token|auth[_-]?token|"
    r"client[_-]?secret|token|secret|password|passwd|pwd|pin|credentials?)"
)
# A bare value runs to whitespace, a quote, `&` or `;` — not to `,`/`)`/`]`,
# which let `password=abc,def` keep `,def`. Prose like `credentials: missing`
# is redacted too: safety over readability.
_KV_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9])(?P<key>" + _KV_KEYS + r"[\"']?\s*[:=]\s*)"
    r"(?:\"(?P<dq>[^\"]*)\"|'(?P<sq>[^']*)'|(?P<bare>[^\s\"'&;]+))"
)

# Settings whose value is a list of notification URLs (Apprise), where nearly
# every URL component is a credential.
_NOTIFICATION_FIELDS = frozenset({"notification_urls_json"})
# Dict keys inside JSON blobs that hold a credential, beyond what
# is_sensitive_config_key() recognises (camelCase from the *arr APIs).
_NESTED_CREDENTIAL_KEYS = frozenset({"apikey", "api_key", "password", "token", "secret", "pin"})
# Apprise URL components shorter than this are ids/flags, not tokens.
_MIN_URL_COMPONENT_LEN = 8


# ─── Regex layer ──────────────────────────────────────────────────────────────


def _kv_replacement(match: re.Match) -> str:
    value = match.group("dq")
    quote = '"'
    if value is None:
        value = match.group("sq")
        quote = "'"
    if value is None:
        value = match.group("bare")
        quote = ""
    if not value or value.lower() in _PLACEHOLDER_VALUES or value.startswith("***"):
        return match.group(0)
    return f"{match.group('key')}{quote}{REDACTED}{quote}"


def _redact_patterns(text: str) -> str:
    if not _TRIGGER_RE.search(text):
        return text
    text = _DSN_RE.sub(lambda m: f"{m.group(1)}{REDACTED}{m.group(3)}", text)
    text = _AUTH_SCHEME_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}", text)
    text = _DISCORD_WEBHOOK_RE.sub(lambda m: f"{m.group(1)}{REDACTED}", text)
    text = _SLACK_WEBHOOK_RE.sub(lambda m: f"{m.group(1)}{REDACTED}", text)
    text = _TELEGRAM_BOT_RE.sub(lambda m: f"{m.group(1)}{REDACTED}", text)
    return _KV_RE.sub(_kv_replacement, text)


# ─── Value collection ─────────────────────────────────────────────────────────


def _url_userinfo_secrets(text: str) -> set[str]:
    """Passwords embedded as ``scheme://user:pass@`` anywhere in ``text``."""
    found: set[str] = set()
    for match in _DSN_RE.finditer(text):
        password = match.group(2)
        found.add(password)
        found.add(unquote(password))
    return found


def _notification_url_secrets(raw: str) -> set[str]:
    """Every token-like component of every Apprise URL in ``raw``."""
    try:
        parsed = json.loads(raw)
        urls = [u for u in parsed if isinstance(u, str)] if isinstance(parsed, list) else []
    except ValueError:
        urls = [line.strip() for line in raw.splitlines() if line.strip()]

    found: set[str] = set()
    for url in urls:
        found.add(url)
        try:
            parts = urlsplit(url)
        except ValueError:
            continue
        components = [parts.username or "", parts.password or ""]
        host = parts.hostname or ""
        # A host with a dot is a real server name; a dotless "host" in an
        # Apprise URL is usually the first token (discord://<id>/<token>).
        if "." not in host:
            components.append(host)
        components.extend(parts.path.split("/"))
        components.extend(v for pair in parts.query.split("&") for v in pair.split("=")[1:])
        # Telegram tokens are ``<digits>:<secret>`` — the netloc holds both.
        components.append(parts.netloc.rpartition("@")[2])
        found.update(c for c in components if len(c) >= _MIN_URL_COMPONENT_LEN)
    return found


def _nested_json_secrets(raw: str, is_sensitive) -> set[str]:
    """Credential values nested anywhere in a JSON settings blob."""
    try:
        parsed = json.loads(raw)
    except ValueError:
        return set()

    found: set[str] = set()
    stack = [parsed]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            for key, value in node.items():
                if isinstance(value, (dict, list)):
                    stack.append(value)
                elif isinstance(value, str) and value.strip():
                    name = str(key).lower()
                    if name in _NESTED_CREDENTIAL_KEYS or is_sensitive(name):
                        found.add(value.strip())
                    found |= _url_userinfo_secrets(value)
        elif isinstance(node, list):
            stack.extend(node)
    return found


def collect_secret_values(settings) -> frozenset[str]:
    """All configured secret strings, for the value pass. Never logs."""
    from config_settings import BootSettings, UISettings, is_sensitive_config_key

    defaults = {
        name: field.default
        for model in (BootSettings, UISettings)
        for name, field in model.model_fields.items()
    }
    found: set[str] = set()
    for key, value in settings.model_dump().items():
        if not isinstance(value, str) or not value.strip():
            continue
        value = value.strip()
        if is_sensitive_config_key(key) and value != defaults.get(key):
            found.add(value)
        if "://" in value:
            found |= _url_userinfo_secrets(value)
        if key in _NOTIFICATION_FIELDS:
            found |= _notification_url_secrets(value)
        elif value[:1] in ("[", "{"):
            found |= _nested_json_secrets(value, is_sensitive_config_key)
    return frozenset(
        v for v in found if len(v) >= _MIN_VALUE_LEN and v.lower() not in _PLACEHOLDER_VALUES
    )


# ─── Live value cache ─────────────────────────────────────────────────────────

# Reentrant, plus a per-thread "collecting" flag: collection runs inside a
# logging filter, and anything it logs re-enters redact() on the same thread.
# A plain Lock deadlocked there; an RLock alone would recurse into collection.
_cache_lock = threading.RLock()
_collecting = threading.local()
_cached_settings: object | None = None
_cached_values: tuple[str, ...] = ()
_warned = False


def _warn_once(what: str, exc: BaseException) -> None:
    """One stderr line per process. Not through logging: that would recurse."""
    global _warned
    if _warned:
        return
    _warned = True
    try:
        sys.stderr.write(
            f"sublarr: secret redaction {what} ({type(exc).__name__}); "
            "continuing without it for this record\n"
        )
    except Exception:  # noqa: BLE001 — stderr itself is gone; nothing left to tell
        pass


def _current_values() -> tuple[str, ...]:
    """The value set for the active settings object, rebuilt when it changes.

    Uses ``peek_settings`` so a record logged before the singleton exists (or
    outside an app context) never builds it here.
    """
    global _cached_settings, _cached_values
    from config_singleton import peek_settings

    settings = peek_settings()
    if settings is None:
        return ()
    if settings is _cached_settings:
        return _cached_values
    if getattr(_collecting, "active", False):
        # A record logged by the collection itself: use what we have so far.
        return _cached_values
    with _cache_lock:
        if settings is not _cached_settings:
            _collecting.active = True
            try:
                values = collect_secret_values(settings)
            except Exception as exc:  # noqa: BLE001 — degrade to the regex layer
                _warn_once("could not collect configured secrets", exc)
                values = frozenset()
            finally:
                _collecting.active = False
            _cached_values = tuple(sorted(values, key=len, reverse=True))
            _cached_settings = settings
        return _cached_values


# ─── Public API ───────────────────────────────────────────────────────────────


def redact(text: str, values: Iterable[str] | None = None) -> str:
    """Return ``text`` with every configured secret and secret shape replaced.

    Args:
        text: Any string. Non-strings and empty strings are returned unchanged.
        values: Explicit secret values (tests, callers with their own set).
            ``None`` uses the cached set for the active settings.
    """
    if not text or not isinstance(text, str):
        return text
    ordered = (
        _current_values()
        if values is None
        else tuple(sorted((v for v in values if v), key=len, reverse=True))
    )
    for value in ordered:
        if value in text:
            text = text.replace(value, REDACTED)
    return _redact_patterns(text)


def scrub_tree(value, scrub=None):
    """Return a copy of a JSON-like structure with ``scrub`` applied to every string leaf.

    Walks the structure instead of redacting its JSON text: on JSON text an
    escaped quote inside a value broke the round trip (the section was lost)
    and a non-ASCII secret, escaped by ``json.dumps``, no longer matched the
    value pass. Dict keys are field names and left alone.
    """
    if scrub is None:
        scrub = redact
    if isinstance(value, str):
        return scrub(value)
    if isinstance(value, dict):
        return {k: scrub_tree(v, scrub) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [scrub_tree(v, scrub) for v in value]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    # Anything else (datetime, Decimal, …) ships as text — scrubbed like text.
    return scrub(str(value))


class SecretRedactionFilter(logging.Filter):
    """Redact a record's message, traceback and stack before any handler writes it.

    Attached to every root handler (file, console, live WebSocket stream), so
    the log file, the viewer and the support bundle are scrubbed at write
    time. A record is processed once even when it passes several handlers.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if getattr(record, "_sublarr_redacted", False):
            return True
        try:
            _redact_record(record)
        except Exception as exc:  # noqa: BLE001 — never drop a record over redaction
            _warn_once("failed", exc)
        record._sublarr_redacted = True
        return True


def _redact_record(record: logging.LogRecord) -> None:
    # Looked up through the module so a patched/replaced redact() is honoured.
    scrub = sys.modules[__name__].redact
    message = record.getMessage()
    cleaned = scrub(message)
    if cleaned != message:
        record.msg = cleaned
        record.args = None
    if record.exc_info and not record.exc_text:
        # Pre-render the traceback so the formatter reuses the redacted text
        # instead of rendering the raw exception (which may quote a DSN).
        record.exc_text = logging.Formatter().formatException(record.exc_info)
    if record.exc_text:
        record.exc_text = scrub(record.exc_text)
    if record.stack_info:
        record.stack_info = scrub(record.stack_info)
