"""Serving Sublarr under a reverse-proxy path prefix.

The ``base_url`` setting has existed in the UI for a long time without anything
reading it. This module is what reads it.

Convention follows the *arr applications Sublarr sits next to: the application
answers under the prefix itself, so a proxy can forward the path unchanged
(``proxy_pass http://host:5765;`` — no trailing slash). Requests without the
prefix keep working on purpose, because a wrong value in that field would
otherwise lock the user out of the very page that fixes it.

The value is read per request rather than at startup: it is a normal setting,
and changing it must not require restarting the container.
"""

from __future__ import annotations

import html as _html
import json
import logging
import re

logger = logging.getLogger(__name__)

# A path prefix is one or more segments of unreserved URL characters. Anything
# else is not a prefix, and since this value is rendered into an HTML attribute
# and into a JS string literal, it is refused outright rather than escaped and
# served: a quote or an angle bracket here can only be an attempt at something.
_SAFE_PREFIX = re.compile(r"^(/[A-Za-z0-9._~-]+)+$")


def normalize_base_path(raw: str | None) -> str:
    """Return ``""`` or ``"/prefix"`` — never a trailing slash.

    Accepts what a person types: ``sublarr``, ``/sublarr``, ``/sublarr/``.
    A value that is not a path prefix yields ``""`` — serve at the root.
    """
    value = (raw or "").strip()
    if not value or value == "/":
        return ""
    if not value.startswith("/"):
        value = "/" + value
    value = value.rstrip("/")
    if not _SAFE_PREFIX.match(value):
        logger.warning("Ignoring base_url %r: not a path prefix", raw)
        return ""
    return value


def get_base_path() -> str:
    """The configured prefix, or ``""`` when Sublarr is served at the root.

    Reads an *already built* settings singleton and never builds one. That
    distinction is the whole point. This runs inside WSGI middleware, before
    Flask pushes an application context, and ``get_settings()`` builds the
    singleton by merging the database overrides onto the defaults — a read it
    cannot perform without that context. Calling it here would therefore cache
    a Settings object with every stored setting missing, and every later reader
    would get that object: measured, an override of ``wanted_anime_only=False``
    came back ``True`` and stayed ``True`` for the life of the process.

    ``get_config_entry`` is out for the same reason — it needs the context too.
    ``peek_settings`` is the accessor that says so in its own name, rather than
    this module reaching into a private global and degrading silently the day
    somebody renames it.

    An unbuilt singleton means "serve at the root" for that one request. The
    app builds it during startup, so in practice the prefix is available from
    the first request onwards, and ``reload_settings`` swaps it atomically —
    it never passes through None — so a changed value takes effect on the next
    request without a restart and without a window where the prefix is lost.
    """
    from config import peek_settings

    settings = peek_settings()
    if settings is None:
        return ""
    return normalize_base_path(getattr(settings, "base_url", ""))


class PrefixMiddleware:
    """Strip the configured prefix from ``PATH_INFO`` into ``SCRIPT_NAME``.

    Only a whole path segment counts: with the prefix ``/sublarr``, the path
    ``/sublarrX`` is a different location and is left alone, so it never
    reaches ``/X``.
    """

    def __init__(self, wsgi_app, get_prefix=get_base_path):
        self.wsgi_app = wsgi_app
        self._get_prefix = get_prefix

    def __call__(self, environ, start_response):
        prefix = self._get_prefix()
        if prefix:
            path = environ.get("PATH_INFO", "")
            if path == prefix or path.startswith(prefix + "/"):
                environ["SCRIPT_NAME"] = environ.get("SCRIPT_NAME", "") + prefix
                environ["PATH_INFO"] = path[len(prefix) :] or "/"
        return self.wsgi_app(environ, start_response)


def inject_base_into_index(html: str, prefix: str) -> str:
    """Point the shell's ``<base>`` at the prefix and expose it to the bundle.

    The bundle's asset URLs are relative so one build serves any prefix, and
    ``<base>`` is what makes them resolve — without it ``./assets/x.js`` on a
    reloaded ``/wanted/123`` would be looked up under ``/wanted/``. The same
    value reaches the app through ``window.__SUBLARR_BASE__``, which the API
    client and the router basename read.

    The value is normalised and escaped here even though callers normalise it
    too. This renders into two different grammars — an HTML attribute and a JS
    string — and one caller passing an unchecked value must not be able to turn
    either of them into script.
    """
    prefix = normalize_base_path(prefix)
    href = _html.escape(f"{prefix}/" if prefix else "/", quote=True)

    replaced, count = re.subn(
        r'<base\s+href="[^"]*"\s*/?>', f'<base href="{href}" />', html, count=1
    )
    if not count:
        # No base element to rewrite — a shell built before this existed. Put
        # one in rather than serving assets that cannot resolve.
        replaced = re.sub(r"(<head[^>]*>)", rf'\1<base href="{href}" />', html, count=1)

    # json.dumps produces a correctly quoted and escaped JS string literal; the
    # extra "<" escape keeps a "</script" sequence from ending the element.
    literal = json.dumps(prefix).replace("<", "\u003c")
    marker = f"<script>window.__SUBLARR_BASE__ = {literal};</script>"
    return replaced.replace("</head>", f"{marker}</head>", 1)
