# Custom HTTP/JSON Provider

The `customapi` provider turns any HTTP endpoint that returns JSON into a
subtitle source — **without writing a plugin**. Point it at a private
subtitle server that implements the small contract below, or adapt an
existing third-party REST API using the mapping settings.

Because it only sends configured HTTP requests and never executes
third-party code, it is the safest way to integrate a custom source.
For anything the mapping can't express (multi-step flows, login sessions,
HTML scraping), write a [plugin](https://sublarr.de/docs/development/plugin-development/) instead.

## Quick start (private server)

1. Implement the three endpoints below on your server.
2. In Sublarr: **Settings → Providers → customapi**, set the **Base URL**
   (e.g. `http://192.168.1.10:9000`) and optionally an **API Key**.
3. Done — results are scored, cached, rate-limited, and circuit-broken
   exactly like every built-in provider.

## The contract

All endpoints are relative to the configured base URL. Paths are
configurable (`Search Path`, `Download Path`); the defaults are shown.

### `GET /search`

Sublarr sends one request per search with the video's metadata as query
parameters. All parameters are optional — use what you need:

| Parameter | Example | Notes |
|---|---|---|
| `title` | `Inception` | Movies only |
| `series_title` | `Frieren` | Episodes only |
| `season` | `1` | Episodes only |
| `episode` | `4` | Episodes only |
| `year` | `2010` | |
| `imdb_id` | `tt1375666` | |
| `tmdb_id` | `27205` | |
| `tvdb_id` | `424536` | |
| `anilist_id` | `154587` | |
| `languages` | `de,en` | Comma-separated ISO 639-1 codes |
| `file_hash` | `8e245d9679d31e12` | OpenSubtitles-style hash |
| `file_size` | `3841923072` | Bytes |
| `release_group` | `SubsPlease` | |
| `resolution` | `1080p` | |
| `source` | `WEB-DL` | |

Respond with `200` and:

```json
{
  "results": [
    {
      "id": "abc123",
      "language": "de",
      "download_url": "/download/abc123",
      "filename": "Frieren.S01E04.de.ass",
      "format": "ass",
      "release": "SubsPlease 1080p",
      "hearing_impaired": false,
      "forced": false,
      "matches": ["series", "season", "episode", "release_group"]
    }
  ]
}
```

Per-item fields:

| Field | Required | Notes |
|---|---|---|
| `id` | ✅ | Unique subtitle id (string or number) |
| `language` | recommended | ISO 639-1. Falls back to the (single) requested language; items whose language doesn't match the request are dropped |
| `download_url` | — | Absolute or relative to the base URL. Omit it to have Sublarr use the download path (`/download/{id}`) |
| `filename` | recommended | Used for format detection |
| `format` | — | `ass` / `ssa` / `srt` / `vtt`; inferred from `filename` when omitted |
| `release` | — | Release/version info shown in the UI |
| `hearing_impaired` | — | Boolean |
| `forced` | — | Boolean |
| `matches` | — | Which query attributes this subtitle matches — this is what drives scoring. Valid values include `hash`, `series`, `title`, `year`, `season`, `episode`, `release_group`, `source`, `resolution`, `video_codec` |

Auth failures should return `401`/`403`; rate limiting `429` (a
`Retry-After` header is honored).

### `GET /download/{id}`

Returns the raw subtitle file (`.ass`/`.srt`/…) or a ZIP archive
containing it (ASS/SSA is preferred when extracting).

### `GET /health` *(optional)*

Return `200` when healthy. Without this endpoint, any non-5xx response
from the base URL counts as healthy.

### Authentication

If an API key is configured, it is sent on every request in the
`X-API-Key` header (configurable). When the header is set to
`Authorization` and the key contains no scheme, `Bearer ` is prefixed
automatically.

## Adapting an existing API

Three settings map a foreign response shape onto the contract:

- **Results Path** — dot-notation path to the result array inside the
  response, e.g. `data.subtitles`. Leave empty for a top-level array.
- **Field Map** (JSON) — maps Sublarr fields to per-item paths
  (dot-notation supported):

  ```json
  {"subtitle_id": "attributes.sid", "download_url": "attributes.file.url", "release_info": "attributes.release"}
  ```

  Mappable fields: `subtitle_id`, `language`, `download_url`, `filename`,
  `format`, `release_info`, `hearing_impaired`, `forced`, `matches`.
- **Extra Query Params** (JSON) — static parameters added to every search
  request, e.g. `{"apikey": "...", "type": "subtitle"}`.

## Multiple instances

Several independent servers can be configured via
**Extra Instances (JSON array)** on the `customapi` provider:

```json
[
  {"name": "Home NAS", "base_url": "http://192.168.1.10:9000", "api_key": "s3cret"},
  {"name": "VPS Mirror", "base_url": "https://subs.example.org", "search_path": "/api/search"}
]
```

Each entry is registered as its own provider named `customapi-<name>`
(e.g. `customapi-home-nas`) with separate statistics, health state,
circuit breaker, and priority. Instance entries accept the same keys as
the main provider settings (without the `customapi_` prefix): `base_url`,
`api_key`, `api_key_header`, `search_path`, `download_path`,
`results_path`, `field_map` (object), `extra_params` (object).

## Security notes

- Only `http`/`https` URLs are accepted. Private LAN addresses are
  allowed (that's the point), but cloud-metadata endpoints and link-local
  addresses are always blocked.
- Downloads are streamed with a 50 MB cap and validated as subtitle
  content before being saved.
- The API key is encrypted at rest like all other provider credentials.
