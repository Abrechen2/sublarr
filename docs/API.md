# API Reference

Sublarr exposes a RESTful API for all operations. All endpoints are prefixed with `/api/v1/`.

## Table of Contents

- [Authentication](#authentication)
- [Response Format](#response-format)
- [Health & Status](#health--status)
- [Translation](#translation)
- [Configuration](#configuration)
- [Library](#library)
- [Wanted](#wanted)
- [Providers](#providers)
- [Language Profiles](#language-profiles)
- [Webhooks](#webhooks)
- [Notifications](#notifications)
- [History & Blacklist](#history--blacklist)
- [Glossary](#glossary)
- [Prompt Presets](#prompt-presets)
- [Logs](#logs)
- [WebSocket Events](#websocket-events)

## Authentication

Sublarr supports optional API key authentication. If `SUBLARR_API_KEY` is set, all endpoints (except `/health` and webhooks) require authentication.

**Methods**

1. **Header**
   ```
   X-Api-Key: your-api-key-here
   ```

2. **Query Parameter**
   ```
   GET /api/v1/jobs?apikey=your-api-key-here
   ```

**Exempt Endpoints**
- `GET /api/v1/health`
- `POST /api/v1/webhook/sonarr`
- `POST /api/v1/webhook/radarr`

**Error Response (401 Unauthorized)**
```json
{
  "error": "Unauthorized",
  "details": "Invalid or missing API key"
}
```

## Response Format

**Success Response**
```json
{
  "success": true,
  "data": {
    // Response data here
  }
}
```

**Error Response**
```json
{
  "error": "Error message",
  "details": {
    // Additional error context
  }
}
```

**HTTP Status Codes**
- `200 OK` - Request successful
- `201 Created` - Resource created
- `400 Bad Request` - Invalid request parameters
- `401 Unauthorized` - Missing or invalid API key
- `404 Not Found` - Resource not found
- `500 Internal Server Error` - Server error

## Health & Status

### GET /health

Health check endpoint. Returns status of all services and providers.

**Authentication**: None required

**Response**
```json
{
  "status": "healthy",
  "database": "ok",
  "ollama": "ok",
  "providers": {
    "animetosho": "ok",
    "jimaku": "ok",
    "opensubtitles": "ok",
    "subdl": "ok"
  }
}
```

### GET /stats

Get overall system statistics.

**Response**
```json
{
  "jobs": {
    "total": 1234,
    "completed": 1100,
    "failed": 34,
    "pending": 100
  },
  "subtitles": {
    "ass": 800,
    "srt": 300,
    "total": 1100
  },
  "providers": {
    "animetosho": {
      "searches": 500,
      "downloads": 300,
      "success_rate": 0.60
    },
    "jimaku": {
      "searches": 400,
      "downloads": 250,
      "success_rate": 0.63
    }
  },
  "daily": [
    {
      "date": "2024-01-15",
      "jobs_completed": 45,
      "jobs_failed": 2
    }
  ]
}
```

## Translation

### POST /translate

Start an asynchronous translation job.

**Request Body**
```json
{
  "file_path": "/media/anime/episode.mkv",
  "source_language": "en",
  "target_language": "de",
  "force": false
}
```

**Parameters**
- `file_path` (string, required): Absolute path to video file
- `source_language` (string, optional): Source subtitle language (defaults to config)
- `target_language` (string, optional): Target subtitle language (defaults to config)
- `force` (boolean, optional): Force re-translation if target exists (default: false)

**Response**
```json
{
  "success": true,
  "data": {
    "job_id": "abc123",
    "status": "pending"
  }
}
```

### POST /translate/sync

Translate a single file. When a job queue is configured, the request returns immediately with **202** and a `job_id`; poll `GET /status/<job_id>` or use WebSocket `job_update` for the result. When no queue is available, the request blocks and returns **200** with the translation result.

**Request Body**: Same as `/translate`

**Response (200 – no queue, ran in request)**
```json
{
  "success": true,
  "output_path": "/media/anime/episode.de.ass",
  "stats": { ... }
}
```

**Response (202 – queued)**
```json
{
  "job_id": "abc123",
  "status": "queued",
  "file_path": "/media/anime/episode.mkv"
}
```
Use `GET /status/<job_id>` or WebSocket to get the final result.

### GET /status/:job_id

Get the status of a translation job.

**Response**
```json
{
  "job_id": "abc123",
  "status": "completed",
  "file_path": "/media/anime/episode.mkv",
  "created_at": "2024-01-15T10:30:00Z",
  "completed_at": "2024-01-15T10:30:15Z",
  "error": null,
  "stats": {
    "lines_translated": 350,
    "duration_seconds": 12.5
  }
}
```

**Status Values**
- `pending` - Job queued
- `processing` - Translation in progress
- `completed` - Successfully completed
- `failed` - Error occurred

### GET /jobs

Get paginated list of translation jobs.

**Query Parameters**
- `page` (integer, default: 1): Page number
- `limit` (integer, default: 50): Jobs per page
- `status` (string, optional): Filter by status (pending/processing/completed/failed)
- `sort` (string, default: "created_at"): Sort field
- `order` (string, default: "desc"): Sort order (asc/desc)

**Response**
```json
{
  "jobs": [
    {
      "job_id": "abc123",
      "status": "completed",
      "file_path": "/media/anime/episode.mkv",
      "created_at": "2024-01-15T10:30:00Z",
      "completed_at": "2024-01-15T10:30:15Z"
    }
  ],
  "total": 1234,
  "page": 1,
  "pages": 25
}
```

### POST /batch

Process multiple files in batch.

**Request Body**
```json
{
  "file_paths": [
    "/media/anime/s01e01.mkv",
    "/media/anime/s01e02.mkv"
  ],
  "source_language": "en",
  "target_language": "de",
  "force": false,
  "dry_run": false
}
```

**Parameters**
- `file_paths` (array, required): List of video file paths
- `source_language` (string, optional): Source language
- `target_language` (string, optional): Target language
- `force` (boolean, optional): Force re-translation
- `dry_run` (boolean, optional): Only check status, don't translate

**Response**
```json
{
  "batch_id": "batch_xyz",
  "queued": 2,
  "skipped": 0,
  "jobs": [
    {
      "file_path": "/media/anime/s01e01.mkv",
      "job_id": "job1",
      "status": "pending"
    },
    {
      "file_path": "/media/anime/s01e02.mkv",
      "job_id": "job2",
      "status": "pending"
    }
  ]
}
```

### GET /batch/status

Get batch processing status.

**Query Parameters**
- `batch_id` (string, required): Batch ID from POST /batch

**Response**
```json
{
  "batch_id": "batch_xyz",
  "total": 2,
  "completed": 1,
  "failed": 0,
  "pending": 1,
  "progress": 50
}
```

## Configuration

### GET /config

Get current configuration (secrets redacted).

**Response**
```json
{
  "source_language": "en",
  "target_language": "de",
  "ollama_host": "http://localhost:11434",
  "ollama_model": "llama3.1",
  "providers_enabled": ["animetosho", "jimaku", "opensubtitles", "subdl"],
  "provider_priorities": ["animetosho", "jimaku", "opensubtitles", "subdl"],
  "sonarr_enabled": true,
  "sonarr_url": "http://localhost:8989",
  "radarr_enabled": true,
  "radarr_url": "http://localhost:7878",
  "auto_search_wanted": true,
  "upgrade_window_days": 7
}
```

### PUT /config

Update configuration. Changes are saved to database and applied immediately.

**Request Body**
```json
{
  "source_language": "en",
  "target_language": "de",
  "ollama_model": "llama3.1",
  "auto_search_wanted": true
}
```

**Response**
```json
{
  "success": true,
  "message": "Configuration updated",
  "config": {
    // Updated config here
  }
}
```

### GET /config/export

Export configuration as JSON file for backup.

**Response**: JSON file download with current config

### POST /config/import

Import configuration from JSON file.

**Request**: Multipart form data with JSON file

**Response**
```json
{
  "success": true,
  "message": "Configuration imported",
  "updated_keys": 15
}
```

## Library

### GET /library

Get all series and movies with subtitle status.

**Query Parameters**
- `page` (integer, default: 1): Page number
- `limit` (integer, default: 50): Items per page
- `type` (string, optional): Filter by type (series/movie)
- `missing_subs` (boolean, optional): Only show items with missing subtitles

**Response**
```json
{
  "items": [
    {
      "id": 123,
      "type": "series",
      "title": "Attack on Titan",
      "year": 2013,
      "path": "/media/anime/Attack on Titan",
      "seasons": [
        {
          "season": 1,
          "episodes": [
            {
              "episode": 1,
              "file_path": "/media/anime/s01e01.mkv",
              "has_target_sub": true,
              "has_source_sub": true,
              "subtitle_format": "ass"
            }
          ]
        }
      ],
      "subtitles": {
        "total_episodes": 75,
        "with_target": 60,
        "with_source": 70,
        "missing": 5
      }
    }
  ],
  "total": 100,
  "page": 1,
  "pages": 2
}
```

### GET /library/series/:id

Get detailed information for a specific series.

**Path Parameters**
- `id` (integer): Sonarr series ID

**Response**
```json
{
  "id": 123,
  "title": "Attack on Titan",
  "year": 2013,
  "tvdb_id": 267440,
  "path": "/media/anime/Attack on Titan",
  "language_profile_id": 2,
  "seasons": [
    // Full season/episode details
  ]
}
```

## Wanted

### GET /wanted

Get list of missing subtitles (wanted items).

**Query Parameters**
- `page` (integer, default: 1): Page number
- `limit` (integer, default: 50): Items per page
- `status` (string, optional): Filter by status (pending/searching/completed/failed)
- `type` (string, optional): Filter by type (series/movie)
- `language` (string, optional): Filter by target language

**Response**
```json
{
  "items": [
    {
      "id": 1,
      "type": "series",
      "series_id": 123,
      "series_title": "Attack on Titan",
      "season": 1,
      "episode": 1,
      "file_path": "/media/anime/s01e01.mkv",
      "target_language": "de",
      "status": "pending",
      "created_at": "2024-01-15T10:00:00Z",
      "last_search": null,
      "attempts": 0
    }
  ],
  "total": 50,
  "page": 1,
  "pages": 1
}
```

### GET /wanted/summary

Get summary statistics for wanted items.

**Response**
```json
{
  "total": 50,
  "pending": 30,
  "searching": 5,
  "completed": 10,
  "failed": 5,
  "by_language": {
    "de": 25,
    "fr": 15,
    "es": 10
  },
  "by_type": {
    "series": 40,
    "movie": 10
  }
}
```

### POST /wanted/refresh

Trigger a full wanted scan (checks all series/movies for missing subtitles).

**Request Body**
```json
{
  "force": false
}
```

**Parameters**
- `force` (boolean, optional): Force scan even if recently scanned

**Response**
```json
{
  "success": true,
  "message": "Scan started",
  "job_id": "scan_abc"
}
```

### PUT /wanted/:id/status

Manually update status of a wanted item.

**Path Parameters**
- `id` (integer): Wanted item ID

**Request Body**
```json
{
  "status": "failed"
}
```

**Status Values**: `pending`, `searching`, `completed`, `failed`

**Response**
```json
{
  "success": true,
  "message": "Status updated"
}
```

### DELETE /wanted/:id

Remove a wanted item (e.g., if subtitle found manually).

**Path Parameters**
- `id` (integer): Wanted item ID

**Response**
```json
{
  "success": true,
  "message": "Wanted item removed"
}
```

### POST /wanted/:id/search

Search providers for a specific wanted item.

**Path Parameters**
- `id` (integer): Wanted item ID

**Response**
```json
{
  "target_results": [
    {
      "provider": "jimaku",
      "language": "de",
      "format": "ass",
      "score": 200,
      "download_url": "https://..."
    }
  ],
  "source_results": [
    {
      "provider": "animetosho",
      "language": "en",
      "format": "ass",
      "score": 250
    }
  ]
}
```

### POST /wanted/:id/process

Download and process (translate) a wanted item.

**Path Parameters**
- `id` (integer): Wanted item ID

**Request Body**
```json
{
  "use_source": false
}
```

**Parameters**
- `use_source` (boolean, optional): Download source sub and translate (default: false, tries target first)

**Response**
```json
{
  "success": true,
  "job_id": "job_xyz",
  "message": "Processing started"
}
```

### POST /wanted/:id/extract

Extract embedded subtitles from video file.

**Path Parameters**
- `id` (integer): Wanted item ID

**Response**
```json
{
  "success": true,
  "extracted": [
    {
      "language": "en",
      "format": "ass",
      "file_path": "/media/anime/s01e01.en.ass"
    }
  ]
}
```

### POST /wanted/batch-search

Search providers for all wanted items in batch.

**Request Body**
```json
{
  "limit": 50,
  "language": "de"
}
```

**Parameters**
- `limit` (integer, optional): Max items to process (default: 50)
- `language` (string, optional): Filter by target language

**Response**
```json
{
  "success": true,
  "batch_id": "batch_wanted_xyz",
  "queued": 50,
  "message": "Batch search started"
}
```

**WebSocket Event**: `wanted_batch_progress` for live updates

### GET /wanted/batch-search/status

Get status of batch wanted search.

**Query Parameters**
- `batch_id` (string, required): Batch ID from POST /wanted/batch-search

**Response**
```json
{
  "batch_id": "batch_wanted_xyz",
  "total": 50,
  "processed": 25,
  "found": 20,
  "not_found": 5,
  "progress": 50
}
```

### POST /wanted/search-all

Alternative endpoint for batch search (alias).

**Request Body**: Same as `/wanted/batch-search`

**Response**: Same as `/wanted/batch-search`

## Providers

### GET /providers

Get status of all subtitle providers.

**Response**
```json
{
  "providers": [
    {
      "name": "animetosho",
      "enabled": true,
      "healthy": true,
      "priority": 1,
      "requires_auth": false
    },
    {
      "name": "jimaku",
      "enabled": true,
      "healthy": true,
      "priority": 2,
      "requires_auth": true
    },
    {
      "name": "opensubtitles",
      "enabled": true,
      "healthy": false,
      "priority": 3,
      "requires_auth": true,
      "error": "Invalid API key"
    },
    {
      "name": "subdl",
      "enabled": false,
      "healthy": false,
      "priority": 4,
      "requires_auth": true
    }
  ]
}
```

### POST /providers/test/:name

Test connectivity and authentication for a provider.

**Path Parameters**
- `name` (string): Provider name (animetosho/jimaku/opensubtitles/subdl)

**Response**
```json
{
  "provider": "jimaku",
  "healthy": true,
  "message": "Provider is working correctly"
}
```

### GET /providers/stats

Get provider usage statistics.

**Response**
```json
{
  "animetosho": {
    "searches": 500,
    "downloads": 300,
    "success_rate": 0.60,
    "avg_score": 180,
    "last_used": "2024-01-15T10:30:00Z"
  },
  "jimaku": {
    "searches": 400,
    "downloads": 250,
    "success_rate": 0.63,
    "avg_score": 190,
    "last_used": "2024-01-15T10:25:00Z"
  }
}
```

### POST /providers/cache/clear

Clear provider cache (force fresh searches).

**Response**
```json
{
  "success": true,
  "message": "Cache cleared",
  "entries_removed": 150
}
```

## Language Profiles

### GET /language-profiles

List all language profiles.

**Response**
```json
{
  "profiles": [
    {
      "id": 1,
      "name": "Default",
      "source_language": "en",
      "target_languages": ["de"],
      "is_default": true
    },
    {
      "id": 2,
      "name": "Multi-Language Anime",
      "source_language": "ja",
      "target_languages": ["en", "de", "fr"],
      "is_default": false
    }
  ]
}
```

### POST /language-profiles

Create a new language profile.

**Request Body**
```json
{
  "name": "Spanish Anime",
  "source_language": "ja",
  "target_languages": ["es", "es-419"]
}
```

**Response**
```json
{
  "success": true,
  "profile": {
    "id": 3,
    "name": "Spanish Anime",
    "source_language": "ja",
    "target_languages": ["es", "es-419"],
    "is_default": false
  }
}
```

### PUT /language-profiles/:id

Update an existing language profile.

**Path Parameters**
- `id` (integer): Profile ID

**Request Body**
```json
{
  "name": "Updated Name",
  "target_languages": ["de", "fr"]
}
```

**Response**
```json
{
  "success": true,
  "profile": {
    // Updated profile
  }
}
```

### DELETE /language-profiles/:id

Delete a language profile (cannot delete default profile).

**Path Parameters**
- `id` (integer): Profile ID

**Response**
```json
{
  "success": true,
  "message": "Profile deleted"
}
```

### PUT /language-profiles/assign

Assign a language profile to series/movies.

**Request Body**
```json
{
  "profile_id": 2,
  "series_ids": [123, 456],
  "movie_ids": [789]
}
```

**Response**
```json
{
  "success": true,
  "message": "Profile assigned",
  "series_updated": 2,
  "movies_updated": 1
}
```

## Webhooks

### POST /webhook/sonarr

Sonarr webhook endpoint (OnDownload event).

**Authentication**: None required

**Request Body**: Sonarr webhook payload (automatic)

**Response**
```json
{
  "success": true,
  "message": "Webhook received"
}
```

### POST /webhook/radarr

Radarr webhook endpoint (OnDownload event).

**Authentication**: None required

**Request Body**: Radarr webhook payload (automatic)

**Response**
```json
{
  "success": true,
  "message": "Webhook received"
}
```

## Notifications

### POST /notifications/test

Send a test notification to configured notification services.

**Request Body**
```json
{
  "service": "pushover",
  "message": "Test notification from Sublarr"
}
```

**Response**
```json
{
  "success": true,
  "message": "Notification sent"
}
```

### GET /notifications/status

Get status of notification services.

**Response**
```json
{
  "pushover": {
    "enabled": true,
    "configured": true,
    "healthy": true
  },
  "discord": {
    "enabled": false,
    "configured": false,
    "healthy": false
  }
}
```

## History & Blacklist

### GET /history

Get subtitle download history.

**Query Parameters**
- `page` (integer, default: 1): Page number
- `limit` (integer, default: 50): Items per page
- `provider` (string, optional): Filter by provider
- `language` (string, optional): Filter by language

**Response**
```json
{
  "items": [
    {
      "id": 1,
      "file_path": "/media/anime/s01e01.mkv",
      "provider": "jimaku",
      "language": "de",
      "format": "ass",
      "downloaded_at": "2024-01-15T10:30:00Z",
      "translated": true
    }
  ],
  "total": 500,
  "page": 1,
  "pages": 10
}
```

### GET /history/stats

Get download history statistics.

**Response**
```json
{
  "total_downloads": 500,
  "by_provider": {
    "jimaku": 200,
    "animetosho": 150,
    "opensubtitles": 150
  },
  "by_language": {
    "de": 300,
    "fr": 150,
    "es": 50
  },
  "by_format": {
    "ass": 350,
    "srt": 150
  }
}
```

### GET /blacklist

Get blacklisted subtitles.

**Query Parameters**
- `page` (integer, default: 1): Page number
- `limit` (integer, default: 50): Items per page

**Response**
```json
{
  "items": [
    {
      "id": 1,
      "provider": "opensubtitles",
      "subtitle_hash": "abc123",
      "reason": "Low quality translation",
      "blacklisted_at": "2024-01-15T10:30:00Z"
    }
  ],
  "total": 10,
  "page": 1,
  "pages": 1
}
```

### POST /blacklist

Add a subtitle to the blacklist.

**Request Body**
```json
{
  "provider": "opensubtitles",
  "subtitle_hash": "abc123",
  "reason": "Incorrect timing"
}
```

**Response**
```json
{
  "success": true,
  "message": "Subtitle blacklisted"
}
```

### DELETE /blacklist/:id

Remove a subtitle from the blacklist.

**Path Parameters**
- `id` (integer): Blacklist entry ID

**Response**
```json
{
  "success": true,
  "message": "Blacklist entry removed"
}
```

## Glossary

### GET /glossary

Get all glossary entries.

**Response**
```json
{
  "entries": [
    {
      "id": 1,
      "source_term": "nakama",
      "target_term": "friend",
      "language_pair": "ja-en",
      "created_at": "2024-01-15T10:30:00Z"
    }
  ]
}
```

### POST /glossary

Add a new glossary entry.

**Request Body**
```json
{
  "source_term": "senpai",
  "target_term": "senior",
  "language_pair": "ja-en"
}
```

**Response**
```json
{
  "success": true,
  "entry": {
    "id": 2,
    "source_term": "senpai",
    "target_term": "senior",
    "language_pair": "ja-en"
  }
}
```

### PUT /glossary/:id

Update a glossary entry.

**Path Parameters**
- `id` (integer): Glossary entry ID

**Request Body**
```json
{
  "target_term": "upperclassman"
}
```

**Response**
```json
{
  "success": true,
  "entry": {
    // Updated entry
  }
}
```

### DELETE /glossary/:id

Delete a glossary entry.

**Path Parameters**
- `id` (integer): Glossary entry ID

**Response**
```json
{
  "success": true,
  "message": "Glossary entry deleted"
}
```

## Prompt Presets

### GET /prompt-presets

Get all saved prompt presets.

**Response**
```json
{
  "presets": [
    {
      "id": 1,
      "name": "Formal Translation",
      "prompt_template": "Translate the following subtitles in a formal style...",
      "created_at": "2024-01-15T10:30:00Z"
    }
  ]
}
```

### GET /prompt-presets/default

Get the default/active prompt template.

**Response**
```json
{
  "template": "You are a subtitle translator...",
  "preset_id": 1
}
```

### POST /prompt-presets

Create a new prompt preset.

**Request Body**
```json
{
  "name": "Casual Translation",
  "prompt_template": "Translate subtitles in a casual, conversational style..."
}
```

**Response**
```json
{
  "success": true,
  "preset": {
    "id": 2,
    "name": "Casual Translation",
    "prompt_template": "..."
  }
}
```

### PUT /prompt-presets/:id

Update a prompt preset.

**Path Parameters**
- `id` (integer): Preset ID

**Request Body**
```json
{
  "name": "Updated Name",
  "prompt_template": "Updated template..."
}
```

**Response**
```json
{
  "success": true,
  "preset": {
    // Updated preset
  }
}
```

### DELETE /prompt-presets/:id

Delete a prompt preset.

**Path Parameters**
- `id` (integer): Preset ID

**Response**
```json
{
  "success": true,
  "message": "Prompt preset deleted"
}
```

## Logs

### GET /logs

Get paginated system logs.

**Query Parameters**
- `page` (integer, default: 1): Page number
- `limit` (integer, default: 100): Logs per page
- `level` (string, optional): Filter by level (DEBUG/INFO/WARNING/ERROR)
- `search` (string, optional): Search in log messages

**Response**
```json
{
  "logs": [
    {
      "timestamp": "2024-01-15T10:30:00Z",
      "level": "INFO",
      "module": "translator",
      "message": "Translation completed successfully"
    }
  ],
  "total": 10000,
  "page": 1,
  "pages": 100
}
```

## WebSocket Events

Sublarr uses Socket.IO for real-time updates. Connect to `/socket.io/` to receive events.

**Connection Example**
```javascript
import io from 'socket.io-client';

const socket = io('http://localhost:5765', {
  auth: {
    apikey: 'your-api-key'
  }
});

socket.on('connect', () => {
  console.log('Connected to Sublarr');
});
```

### Events

**job_update**

Emitted when a translation job status changes.

```json
{
  "job_id": "abc123",
  "status": "completed",
  "progress": 100,
  "file_path": "/media/anime/episode.mkv"
}
```

**batch_progress**

Emitted during batch translation operations.

```json
{
  "batch_id": "batch_xyz",
  "total": 10,
  "completed": 5,
  "failed": 0,
  "progress": 50
}
```

**wanted_batch_progress**

Emitted during batch wanted search operations.

```json
{
  "batch_id": "batch_wanted_xyz",
  "total": 50,
  "processed": 25,
  "found": 20,
  "not_found": 5,
  "progress": 50
}
```

**scan_progress**

Emitted during library scan operations.

```json
{
  "scan_id": "scan_abc",
  "total_items": 100,
  "processed": 50,
  "found_missing": 15,
  "progress": 50
}
```

**config_updated**

Emitted when configuration is changed.

```json
{
  "updated_keys": ["source_language", "target_language"]
}
```
