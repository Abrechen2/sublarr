"""Custom HTTP/JSON provider — generic, user-configured REST subtitle source.

Talks to any HTTP endpoint that returns subtitle search results as JSON:
a private subtitle server implementing the Sublarr custom-provider contract
(see docs/CUSTOM_PROVIDER_API.md), or an existing third-party API adapted
via the ``results_path`` / ``field_map`` / ``extra_params`` settings.

Additional independent instances (several private servers) are configured
through ``customapi_instances_json`` — each entry is registered as its own
provider named ``customapi-<name>`` with separate stats, circuit breaker,
and rate limiting.

No rate limiting by default: custom endpoints are typically self-hosted.
License: GPL-3.0
"""

import json
import logging
import re
import urllib.parse

from archive_utils import extract_subtitles_from_zip
from providers import _stream_download, register_provider
from providers.base import (
    ProviderAuthError,
    ProviderError,
    ProviderRateLimitError,
    SubtitleFormat,
    SubtitleProvider,
    SubtitleResult,
    VideoQuery,
)
from providers.http_session import create_session
from security_utils import validate_download_url, validate_service_url

logger = logging.getLogger(__name__)

# Maps SubtitleResult fields -> path into each response item (dot-notation).
# Overridable per instance via the ``field_map`` JSON config.
DEFAULT_FIELD_MAP: dict[str, str] = {
    "subtitle_id": "id",
    "language": "language",
    "download_url": "download_url",
    "filename": "filename",
    "format": "format",
    "release_info": "release",
    "hearing_impaired": "hearing_impaired",
    "forced": "forced",
    "matches": "matches",
}

_FORMAT_MAP = {
    ".ass": SubtitleFormat.ASS,
    ".ssa": SubtitleFormat.SSA,
    ".srt": SubtitleFormat.SRT,
    ".vtt": SubtitleFormat.VTT,
}


def _dot_get(obj, path: str):
    """Walk ``obj`` along a dot-separated path ('data.results' / 'items.0.id').

    Returns None when any segment is missing. An empty path returns ``obj``
    unchanged (useful for top-level-array responses).
    """
    if not path:
        return obj
    cur = obj
    for part in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
            cur = cur[int(part)]
        else:
            return None
        if cur is None:
            return None
    return cur


def _parse_json_object(raw, what: str) -> dict:
    """Parse a config value that may be a JSON string or already a dict."""
    if isinstance(raw, dict):
        return raw
    if not raw or not str(raw).strip():
        return {}
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning("customapi: %s is not valid JSON, ignoring: %s", what, e)
        return {}
    if not isinstance(parsed, dict):
        logger.warning("customapi: %s must be a JSON object, ignoring", what)
        return {}
    return parsed


def _format_from_value(value, filename: str) -> SubtitleFormat:
    """Resolve SubtitleFormat from an explicit item value, else the filename."""
    if value:
        try:
            return SubtitleFormat(str(value).lower().lstrip("."))
        except ValueError:
            pass
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return _FORMAT_MAP.get(ext, SubtitleFormat.UNKNOWN)


def _normalize_path(path: str, default: str) -> str:
    path = (path or "").strip() or default
    if not path.startswith("/"):
        path = "/" + path
    return path


@register_provider
class CustomApiProvider(SubtitleProvider):
    """Generic user-configured HTTP/JSON subtitle provider.

    Sends one GET request per search with the video's metadata as query
    parameters and maps the JSON response onto SubtitleResult via a
    configurable field map. Runs no third-party code — adapting an API is
    pure configuration, which keeps this path safer than a Python plugin.
    """

    name = "customapi"
    languages: set[str] = set()  # Determined by the configured endpoint

    config_fields = [
        {
            "key": "customapi_base_url",
            "label": "Base URL",
            "type": "text",
            "required": True,
            "default": "",
        },
        {
            "key": "customapi_api_key",
            "label": "API Key",
            "type": "password",
            "required": False,
            "default": "",
        },
        {
            "key": "customapi_api_key_header",
            "label": "API Key Header",
            "type": "text",
            "required": False,
            "default": "X-API-Key",
        },
        {
            "key": "customapi_search_path",
            "label": "Search Path",
            "type": "text",
            "required": False,
            "default": "/search",
        },
        {
            "key": "customapi_download_path",
            "label": "Download Path ({id} placeholder)",
            "type": "text",
            "required": False,
            "default": "/download/{id}",
        },
        {
            "key": "customapi_results_path",
            "label": "Results Path (dot-notation into JSON)",
            "type": "text",
            "required": False,
            "default": "results",
        },
        {
            "key": "customapi_field_map",
            "label": "Field Map (JSON, advanced)",
            "type": "text",
            "required": False,
            "default": "",
        },
        {
            "key": "customapi_extra_params",
            "label": "Extra Query Params (JSON, advanced)",
            "type": "text",
            "required": False,
            "default": "",
        },
        {
            "key": "customapi_instances_json",
            "label": "Extra Instances (JSON array, advanced)",
            "type": "text",
            "required": False,
            "default": "",
        },
    ]

    rate_limit = (0, 0)
    timeout = 20
    max_retries = 2

    # Self-hosted endpoints: keep the provider-budget gate effectively open.
    rate_limits = {"free": {"second": 10, "hour": 3600, "day": 50000}}

    # Set by sync_instances() on dynamically registered instance subclasses.
    _instance_config: dict | None = None

    def __init__(self, **config):
        super().__init__(**config)
        self.session = None
        self._base = ""
        self._search_path = "/search"
        self._download_path = "/download/{id}"
        self._results_path = "results"
        self._field_map: dict[str, str] = dict(DEFAULT_FIELD_MAP)
        self._extra_params: dict = {}

    def _effective_config(self) -> dict:
        """Constructor kwargs merged with the per-instance config (if any)."""
        cfg = dict(self.config)
        inst = type(self)._instance_config
        if inst:
            for key, value in inst.items():
                if key != "name":
                    cfg[key] = value
        return cfg

    def initialize(self):
        cfg = self._effective_config()

        base_url = str(cfg.get("base_url") or "").strip().rstrip("/")
        if not base_url:
            logger.info("%s: no base URL configured, provider will be disabled", self.name)
            return

        url_ok, url_err = validate_service_url(base_url)
        if not url_ok:
            logger.error("%s: base URL rejected: %s", self.name, url_err)
            return

        self._base = base_url
        self._search_path = _normalize_path(str(cfg.get("search_path") or ""), "/search")
        self._download_path = _normalize_path(str(cfg.get("download_path") or ""), "/download/{id}")
        results_path = cfg.get("results_path")
        self._results_path = "results" if results_path is None else str(results_path).strip()
        self._field_map = {
            **DEFAULT_FIELD_MAP,
            **{k: str(v) for k, v in _parse_json_object(cfg.get("field_map"), "field_map").items()},
        }
        self._extra_params = _parse_json_object(cfg.get("extra_params"), "extra_params")

        self.session = create_session(timeout=self.timeout)
        self.session.headers.update({"Accept": "application/json"})

        api_key = str(cfg.get("api_key") or "").strip()
        if api_key:
            header = str(cfg.get("api_key_header") or "").strip() or "X-API-Key"
            value = api_key
            # Ergonomics: a bare token in an Authorization header almost
            # certainly wants the Bearer scheme.
            if header.lower() == "authorization" and " " not in api_key:
                value = f"Bearer {api_key}"
            self.session.headers[header] = value

    def terminate(self):
        if self.session:
            self.session.close()
            self.session = None

    def health_check(self) -> tuple[bool, str]:
        if not self._base:
            return False, "Base URL not configured"
        if not self.session:
            return False, "Not initialized"
        try:
            resp = self.session.get(f"{self._base}/health", timeout=5)
            if resp.status_code == 200:
                return True, "OK"
            if resp.status_code == 404:
                # No /health endpoint — any non-server-error answer from the
                # base URL counts as reachable.
                resp = self.session.get(self._base, timeout=5)
                if resp.status_code < 500:
                    return True, "OK (no /health endpoint)"
            if resp.status_code in (401, 403):
                return False, "Authentication failed"
            return False, f"HTTP {resp.status_code}"
        except Exception as e:
            return False, str(e)

    # ─── Search ──────────────────────────────────────────────────────────

    def _build_params(self, query: VideoQuery) -> dict:
        params: dict = {}
        if query.is_episode:
            params["series_title"] = query.series_title or query.title
            params["season"] = query.season
            params["episode"] = query.episode
        else:
            params["title"] = query.title
        if query.year:
            params["year"] = query.year
        if query.imdb_id:
            params["imdb_id"] = query.imdb_id
        if query.tmdb_id:
            params["tmdb_id"] = query.tmdb_id
        if query.tvdb_id:
            params["tvdb_id"] = query.tvdb_id
        if query.anilist_id:
            params["anilist_id"] = query.anilist_id
        if query.languages:
            params["languages"] = ",".join(query.languages)
        if query.file_hash:
            params["file_hash"] = query.file_hash
        if query.file_size:
            params["file_size"] = query.file_size
        if query.release_group:
            params["release_group"] = query.release_group
        if query.resolution:
            params["resolution"] = query.resolution
        if query.source:
            params["source"] = query.source
        for key, value in self._extra_params.items():
            params[key] = value
        return params

    def _download_url_for_id(self, subtitle_id: str) -> str:
        quoted = urllib.parse.quote(str(subtitle_id), safe="")
        return self._base + self._download_path.replace("{id}", quoted)

    def search(self, query: VideoQuery) -> list[SubtitleResult]:
        if not self.session or not self._base:
            return []

        params = self._build_params(query)
        try:
            resp = self.session.get(
                self._base + self._search_path, params=params, timeout=self.timeout
            )
        except Exception as e:
            logger.warning("%s: search request failed: %s", self.name, e)
            return []

        if resp.status_code in (401, 403):
            raise ProviderAuthError(f"{self.name}: authentication failed (HTTP {resp.status_code})")
        if resp.status_code == 429:
            retry_after = 60
            try:
                retry_after = int(resp.headers.get("Retry-After", "60"))
            except ValueError:
                pass
            raise ProviderRateLimitError(
                f"{self.name}: rate limited (HTTP 429)", retry_after=retry_after
            )
        if resp.status_code != 200:
            logger.warning(
                "%s: search failed: HTTP %d, response: %s",
                self.name,
                resp.status_code,
                resp.text[:200],
            )
            return []

        try:
            data = resp.json()
        except ValueError as e:
            logger.warning("%s: search response is not JSON: %s", self.name, e)
            return []

        items = _dot_get(data, self._results_path)
        if items is None and isinstance(data, list):
            # Endpoint returns a top-level array — accept it even when a
            # results_path is configured (default 'results' won't match).
            items = data
        if not isinstance(items, list):
            logger.warning(
                "%s: no result list at path %r in search response", self.name, self._results_path
            )
            return []

        results: list[SubtitleResult] = []
        fmap = self._field_map
        for item in items:
            if not isinstance(item, dict):
                continue

            subtitle_id = _dot_get(item, fmap["subtitle_id"])
            if subtitle_id is None or str(subtitle_id) == "":
                continue
            subtitle_id = str(subtitle_id)

            download_url = str(_dot_get(item, fmap["download_url"]) or "")
            if download_url and not download_url.startswith(("http://", "https://")):
                download_url = self._base + "/" + download_url.lstrip("/")
            if not download_url:
                download_url = self._download_url_for_id(subtitle_id)

            language = str(_dot_get(item, fmap["language"]) or "").lower()
            if not language and len(query.languages) == 1:
                language = query.languages[0]
            if language and query.languages and language not in query.languages:
                continue

            filename = str(_dot_get(item, fmap["filename"]) or "")
            raw_matches = _dot_get(item, fmap["matches"])
            matches = (
                {str(m) for m in raw_matches} if isinstance(raw_matches, (list, set)) else set()
            )

            results.append(
                SubtitleResult(
                    provider_name=self.name,
                    subtitle_id=subtitle_id,
                    language=language,
                    format=_format_from_value(_dot_get(item, fmap["format"]), filename),
                    filename=filename,
                    download_url=download_url,
                    release_info=str(_dot_get(item, fmap["release_info"]) or ""),
                    hearing_impaired=bool(_dot_get(item, fmap["hearing_impaired"])),
                    forced=bool(_dot_get(item, fmap["forced"])),
                    matches=matches,
                    provider_data={"item": item},
                )
            )

        logger.info("%s: found %d results", self.name, len(results))
        return results

    # ─── Download ────────────────────────────────────────────────────────

    def result_for_download(self, subtitle_id: str, language: str = "") -> SubtitleResult:
        """Rebuild a downloadable result from a stored id via the download path."""
        return SubtitleResult(
            provider_name=self.name,
            subtitle_id=subtitle_id,
            language=language,
            download_url=self._download_url_for_id(subtitle_id),
        )

    def download(self, result: SubtitleResult) -> bytes:
        if not self.session:
            raise ProviderError(f"{self.name}: not initialized")

        url = result.download_url
        if not url:
            url = self._download_url_for_id(result.subtitle_id)

        url_ok, url_err = validate_download_url(url, self.name)
        if not url_ok:
            raise ProviderError(f"{self.name}: download URL rejected: {url_err}")

        try:
            content = _stream_download(self.session, url, timeout=60, provider_name=self.name)
        except Exception as e:
            raise ProviderError(f"{self.name}: download failed: {e}") from e

        # ZIP archives: extract the best subtitle file (prefer ASS/SSA).
        if content[:4] == b"PK\x03\x04":
            try:
                files = extract_subtitles_from_zip(content)
            except Exception as e:
                raise ProviderError(f"{self.name}: failed to extract archive: {e}") from e
            if not files:
                raise ProviderError(f"{self.name}: no subtitle file found in archive")
            files.sort(key=lambda f: 0 if f[0].lower().endswith((".ass", ".ssa")) else 1)
            filename, content = files[0]
            ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
            result.format = _FORMAT_MAP.get(ext, SubtitleFormat.UNKNOWN)
        elif result.format == SubtitleFormat.UNKNOWN and result.filename:
            result.format = _format_from_value(None, result.filename)

        result.content = content
        logger.info("%s: downloaded %s (%d bytes)", self.name, result.subtitle_id, len(content))
        return content


# ─── Multi-instance support ──────────────────────────────────────────────


def _slugify(name: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]", "-", name.lower())).strip("-")


def sync_instances() -> None:
    """(Re)register provider classes for entries in ``customapi_instances_json``.

    Called from ``import_builtin_providers()`` so every ProviderManager
    (re)initialization picks up config changes: new instances are registered
    as ``customapi-<name>``, removed ones are dropped from the registry.
    Each instance gets its own stats, circuit breaker, and health state.
    """
    from providers.registry import _PROVIDER_CLASSES

    raw = ""
    try:
        from config import get_settings

        raw = getattr(get_settings(), "customapi_instances_json", "") or ""
    except Exception as e:
        logger.debug("customapi: settings unavailable, skipping instance sync: %s", e)

    instances: list[dict] = []
    if raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                instances = [
                    i for i in parsed if isinstance(i, dict) and i.get("name") and i.get("base_url")
                ]
                dropped = len(parsed) - len(instances)
                if dropped:
                    logger.warning(
                        "customapi: %d instance entr%s missing 'name'/'base_url', skipped",
                        dropped,
                        "y is" if dropped == 1 else "ies are",
                    )
            else:
                logger.warning("customapi: customapi_instances_json must be a JSON array")
        except json.JSONDecodeError as e:
            logger.warning("customapi: customapi_instances_json is not valid JSON: %s", e)

    desired: dict[str, dict] = {}
    for inst in instances:
        slug = _slugify(str(inst["name"]))
        if not slug:
            continue
        provider_name = f"customapi-{slug}"
        if provider_name in desired:
            logger.warning("customapi: duplicate instance name %r, skipping", inst["name"])
            continue
        desired[provider_name] = inst

    # Drop registrations for instances that no longer exist in the config.
    for existing in [n for n in _PROVIDER_CLASSES if n.startswith("customapi-")]:
        if existing not in desired:
            del _PROVIDER_CLASSES[existing]
            logger.info("customapi: instance %s removed from registry", existing)

    for provider_name, inst in desired.items():
        cls = type(
            f"CustomApiInstance_{provider_name.replace('-', '_')}",
            (CustomApiProvider,),
            {
                "name": provider_name,
                "config_fields": [],
                "_instance_config": dict(inst),
            },
        )
        # Assign directly (not register_provider) so config edits overwrite
        # the previous registration instead of being skipped as a collision.
        _PROVIDER_CLASSES[provider_name] = cls
        logger.debug("customapi: registered instance %s", provider_name)
