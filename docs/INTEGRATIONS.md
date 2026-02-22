# Integrations

Setup guides for connecting Sublarr to Sonarr, Radarr, Jellyfin, Emby, Plex, Kodi, and Ollama.

---

## Sonarr

Sublarr processes new TV episodes automatically when Sonarr sends a webhook.

### Webhook Setup

1. In Sonarr: **Settings → Connect → Add** → **Webhook**
2. Configure:
   - **Name:** Sublarr
   - **URL:** `http://sublarr:5765/api/v1/webhook/sonarr`
   - **Events:** On Import, On Upgrade
3. Click **Test** — Sonarr will send a test payload
4. Save

### Library Scan (Optional)

To have Sublarr scan your Sonarr library for missing subtitles:

```
SUBLARR_SONARR_URL=http://sonarr:8989
SUBLARR_SONARR_API_KEY=your_api_key_here
```

Find the API key at Sonarr → **Settings → General → API Key**.

### Multi-Instance Setup

For multiple Sonarr instances:

```
SUBLARR_SONARR_INSTANCES_JSON=[
  {"name": "Anime", "url": "http://sonarr-anime:8989", "api_key": "abc123"},
  {"name": "Regular", "url": "http://sonarr:8989", "api_key": "xyz789"}
]
```

### Path Mapping

If Sonarr and Sublarr see different file paths:

```
SUBLARR_PATH_MAPPING=/data/media=/mnt/media
```

Multiple mappings separated by semicolons:

```
SUBLARR_PATH_MAPPING=/data/media=/mnt/media;/data/anime=/mnt/anime
```

---

## Radarr

Identical to Sonarr but for movies.

1. In Radarr: **Settings → Connect → Add** → **Webhook**
2. URL: `http://sublarr:5765/api/v1/webhook/radarr`
3. Events: On Import, On Upgrade

```
SUBLARR_RADARR_URL=http://radarr:7878
SUBLARR_RADARR_API_KEY=your_api_key_here
```

---

## Jellyfin

Sublarr triggers a library refresh after each subtitle download so Jellyfin picks up new files immediately.

### Setup

1. In Sublarr: **Settings → Media Servers → Add**
2. Select type: **Jellyfin**
3. Enter:
   - URL: `http://jellyfin:8096`
   - API Key: from Jellyfin → **Dashboard → Advanced → API Keys**

Or via environment variable:

```
SUBLARR_JELLYFIN_URL=http://jellyfin:8096
SUBLARR_JELLYFIN_API_KEY=your_api_key_here
```

---

## Emby

Same process as Jellyfin — use the multi-server JSON format:

```
SUBLARR_MEDIA_SERVERS_JSON=[
  {"type": "emby", "name": "Main", "url": "http://emby:8096", "api_key": "your_key"}
]
```

---

## Plex

Sublarr uses `plexapi` to trigger library scans after subtitle changes.

```
SUBLARR_MEDIA_SERVERS_JSON=[
  {"type": "plex", "name": "Plex", "url": "http://plex:32400", "token": "your_plex_token"}
]
```

Finding your Plex token: Plex Support > Finding an Authentication Token (X-Plex-Token)

---

## Kodi

Sublarr sends a `VideoLibrary.Scan` JSON-RPC call after subtitle changes.

```
SUBLARR_MEDIA_SERVERS_JSON=[
  {"type": "kodi", "name": "Living Room", "url": "http://kodi-host:8080", "username": "kodi", "password": ""}
]
```

Enable JSON-RPC in Kodi: **Settings → Services → Control → Allow programs on other systems to control Kodi**

---

## Ollama (Local LLM)

Sublarr uses Ollama for subtitle translation. No data leaves your network.

### Install Ollama

```bash
# Linux / macOS
curl -fsSL https://ollama.ai/install.sh | sh
ollama pull qwen2.5:14b-instruct
```

### Configure Sublarr

```
SUBLARR_OLLAMA_URL=http://host.docker.internal:11434
SUBLARR_OLLAMA_MODEL=qwen2.5:14b-instruct
```

### Recommended Models

| Model | VRAM | Quality | Speed |
|---|---|---|---|
| `qwen2.5:14b-instruct` | ~9GB | Excellent | Medium |
| `qwen2.5:7b-instruct` | ~5GB | Very Good | Fast |
| `gemma3:12b` | ~8GB | Good | Medium |
| `mistral:7b-instruct` | ~5GB | Good | Fast |

### Other Translation Backends

Sublarr also supports:

- **DeepL** — high-quality machine translation with glossary support
- **LibreTranslate** — self-hosted free translation
- **OpenAI-compatible** — any OpenAI API endpoint
- **Google Cloud Translation** — Google Translate API

Configure in **Settings → Translation → Translation Backends**.

---

## Apprise Notifications

Sublarr can send notifications via Apprise, which supports 80+ services.

```
SUBLARR_NOTIFICATION_URLS_JSON=["pover://UserKey@AppToken", "discord://WebhookID/Token"]
```

Service examples:

```
pover://UserKey@AppToken           # Pushover
discord://WebhookID/WebhookToken   # Discord
tgram://BotToken/ChatID            # Telegram
slack://TokenA/TokenB/TokenC       # Slack
ntfy://ntfy.sh/topic               # ntfy
gotify://hostname/token            # Gotify
```

---

## Standalone Mode (No Sonarr/Radarr)

If you do not use Sonarr or Radarr, Sublarr can watch a folder directly.

```
SUBLARR_STANDALONE_ENABLED=true
SUBLARR_STANDALONE_SCAN_INTERVAL_HOURS=6
SUBLARR_TMDB_API_KEY=your_tmdb_key
```

Sublarr will watch `SUBLARR_MEDIA_PATH`, detect new video files, look up metadata via TMDB/AniList/TVDB, and queue them for subtitle search.
