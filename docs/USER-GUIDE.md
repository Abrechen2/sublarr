# Sublarr User Guide

Sublarr is a standalone subtitle manager and translator for anime and media. It automatically finds, downloads, and translates subtitles with ASS format priority -- preserving styles, signs, and songs that other tools destroy.

## Quick Start

### Prerequisites

- **Docker** or Docker Compose (recommended)
- **Media library** accessible on the filesystem
- **(Optional)** Sonarr and/or Radarr for library management
- **(Optional)** Ollama or another translation backend for LLM-based subtitle translation

### Docker Compose (Recommended)

Create a `docker-compose.yml`:

```yaml
services:
  sublarr:
    image: ghcr.io/denniswittke/sublarr:0.9.0-beta
    container_name: sublarr
    ports:
      - "5765:5765"
    volumes:
      - ./config:/config        # Application config and database
      - /path/to/media:/media:rw  # Your media library
    environment:
      - PUID=1000               # User ID for file permissions
      - PGID=1000               # Group ID for file permissions
    restart: unless-stopped
```

Start it:

```bash
docker compose up -d
```

Then open `http://localhost:5765` in your browser. The onboarding wizard will guide you through initial setup.

### Unraid

1. Go to the **Apps** tab in Unraid
2. Search for "Sublarr" in Community Applications
3. Click **Install**
4. Configure the template:
   - **Config Path:** `/mnt/user/appdata/sublarr`
   - **Media Path:** Your media share (e.g., `/mnt/user/media`)
   - **Sonarr/Radarr URLs and API Keys** (optional)
   - **Ollama URL** (if using translation)
5. Click **Apply**

### Environment Variables

All settings use the `SUBLARR_` prefix. Key variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `SUBLARR_PORT` | `5765` | Web UI port |
| `SUBLARR_API_KEY` | *(empty)* | Optional API key for authentication |
| `SUBLARR_MEDIA_PATH` | `/media` | Root media library path |
| `SUBLARR_SONARR_URL` | *(empty)* | Sonarr instance URL |
| `SUBLARR_SONARR_API_KEY` | *(empty)* | Sonarr API key |
| `SUBLARR_RADARR_URL` | *(empty)* | Radarr instance URL |
| `SUBLARR_RADARR_API_KEY` | *(empty)* | Radarr API key |
| `SUBLARR_OLLAMA_URL` | `http://localhost:11434` | Ollama server URL |
| `SUBLARR_OLLAMA_MODEL` | `qwen2.5:14b-instruct` | Ollama model for translation |
| `SUBLARR_SOURCE_LANGUAGE` | `en` | Source subtitle language |
| `SUBLARR_TARGET_LANGUAGE` | `de` | Target translation language |

Most configuration is managed through the web UI after initial setup. Environment variables provide defaults that can be overridden in Settings.

## Setup Scenarios

### Scenario 1: Sonarr + Radarr (Recommended)

The most common setup -- Sublarr monitors your Sonarr/Radarr libraries and handles subtitles automatically.

**Step 1: Configure Sonarr**

1. In Sublarr Settings, go to the **Sonarr** tab
2. Enter your Sonarr URL (e.g., `http://192.168.1.100:8989`)
3. Enter your Sonarr API key (found in Sonarr > Settings > General)
4. Click **Test** to verify connection
5. **Path Mapping:** If Sonarr sees media at a different path than Sublarr (common in Docker), configure path mappings:
   - Remote Path: `/tv` (path in Sonarr)
   - Local Path: `/media/tv` (path in Sublarr)

**Step 2: Configure Radarr** (optional, for movies)

1. Same process as Sonarr in the **Radarr** tab
2. URL, API key, and path mappings

**Step 3: Set Up Webhooks**

Webhooks enable real-time subtitle processing when new media is downloaded.

In **Sonarr:**
1. Go to Settings > Connect
2. Add a new Webhook
3. URL: `http://sublarr:5765/api/v1/webhook/sonarr`
4. Trigger on: Import, Upgrade

In **Radarr:**
1. Go to Settings > Connect
2. Add a new Webhook
3. URL: `http://sublarr:5765/api/v1/webhook/radarr`
4. Trigger on: Import, Upgrade

**Step 4: Create Language Profiles**

1. Go to Settings > Advanced > Language Profiles
2. Create a profile (e.g., "Anime German"):
   - Source Language: English (or Japanese for anime)
   - Target Languages: German
   - Translation Backend: Ollama (or your preferred backend)
   - Forced Preference: Separate (to handle signs/songs)
3. Assign profiles to series in the Library view

**Step 5: Enable Providers**

1. Go to Settings > Providers
2. Enable desired providers and enter API keys where required:
   - AnimeTosho: No API key needed (great for anime)
   - OpenSubtitles: API key required (best general coverage)
   - SubDL: API key required (Subscene successor)
   - Jimaku: API key required (anime-focused)
3. Adjust provider priorities (higher priority = searched first)

### Scenario 2: Standalone Mode (No *arr Apps)

Use Sublarr without Sonarr or Radarr by pointing it at media folders directly.

**Step 1: Configure Library Sources**

1. Go to Settings > Advanced > Library Sources
2. Click **Add Watched Folder**
3. Enter the folder path (must be accessible inside the container, e.g., `/media/anime`)
4. Select content type: TV Shows, Movies, or Mixed
5. Enable auto-scan for automatic file detection

**Step 2: Configure Metadata Providers**

Standalone mode needs metadata providers to identify your media:

1. **AniList** (always available, no API key): Best for anime identification
2. **TMDB** (API key required): Best for general movies and TV shows
   - Get a free API key at https://www.themoviedb.org/settings/api
   - Enter in Settings > Library Sources > TMDB API Key
3. **TVDB** (API key required): Alternative TV show metadata
   - Get an API key at https://thetvdb.com/dashboard/account/apikey

**Step 3: Initial Scan**

1. After configuring watched folders, click **Scan Now** on the Library Sources page
2. Sublarr will:
   - Detect all media files in your folders
   - Parse filenames using `guessit` (anime-aware)
   - Look up metadata from configured providers
   - Group files into series/movies
   - Add items missing subtitles to the Wanted list

**Step 4: Ongoing Monitoring**

The `MediaFileWatcher` continuously monitors your folders for new files. When detected:
1. File stability check (waits for download completion)
2. Filename parsing and metadata lookup
3. Automatic addition to Wanted list
4. Subtitle search and download (if auto-search enabled)

### Scenario 3: Mixed Mode

Run both Sonarr/Radarr integration and standalone mode simultaneously.

1. Configure Sonarr/Radarr as in Scenario 1
2. Add watched folders for media not managed by *arr apps
3. Both sources feed into the same Wanted pipeline
4. Items are tagged with their source (sonarr/radarr/standalone) for clarity

## Configuration

### Language Profiles

Language profiles define how subtitles are handled per series or movie.

**Creating a Profile:**
1. Settings > Advanced > Language Profiles
2. Click **Add Profile**
3. Configure:
   - **Name:** Descriptive name (e.g., "Anime JP->DE")
   - **Source Language:** Language to translate from
   - **Target Languages:** One or more languages to translate to
   - **Translation Backend:** Which backend to use (Ollama, DeepL, etc.)
   - **Fallback Chain:** Ordered list of backup backends
   - **Forced Preference:** How to handle forced/signs subtitles

**Assigning Profiles:**
- In the Library view, click a series
- Select the language profile from the dropdown
- The profile applies to all episodes in that series

### Translation Backends

Sublarr supports multiple translation backends. Configure them in Settings > Translation Backends.

| Backend | Type | Self-Hosted | API Key | Best For |
|---------|------|-------------|---------|----------|
| **Ollama** | LLM | Yes | No | Full control, custom prompts, GPU-accelerated |
| **DeepL** | API | No | Yes | High-quality European languages |
| **LibreTranslate** | API | Yes | Optional | Self-hosted, privacy-focused |
| **OpenAI-compatible** | LLM | Both | Yes | GPT-4, local LLMs with OpenAI API |
| **Google Cloud** | API | No | Yes | Broad language support, fast |

**Configuring Ollama (Default):**
1. Install Ollama on your server
2. Pull a model: `ollama pull qwen2.5:14b-instruct`
3. In Sublarr: Settings > Translation Backends > Ollama
4. Enter your Ollama URL and model name
5. Click Test to verify

**Fallback Chains:**
Configure backup backends in case your primary fails. Example:
1. Primary: Ollama (local, fast, free)
2. Fallback 1: DeepL (cloud, high quality)
3. Fallback 2: LibreTranslate (self-hosted backup)

### Subtitle Providers

Providers are searched in priority order. Results are scored and the best match is downloaded.

| Provider | Auth | Coverage | Format Priority |
|----------|------|----------|-----------------|
| AnimeTosho | None | Anime | ASS (fansub quality) |
| Jimaku | API Key | Anime | ASS/SRT |
| OpenSubtitles | API Key + Login | All media | SRT/ASS |
| SubDL | API Key | All media | SRT/ASS |
| Gestdown | None | TV Shows | SRT |
| Podnapisi | None | Multilingual | SRT |
| Kitsunekko | None | Japanese anime | ASS/SRT |
| Napisy24 | None | Polish | SRT |
| Titrari | None | Romanian | SRT |
| LegendasDivx | Login | Portuguese | SRT |

Custom providers can be installed as plugins in `/config/plugins/`.

### Webhooks (Sonarr/Radarr)

Webhooks allow Sonarr and Radarr to notify Sublarr when new media is downloaded.

**Sonarr Webhook URL:** `http://<sublarr-host>:5765/api/v1/webhook/sonarr`
**Radarr Webhook URL:** `http://<sublarr-host>:5765/api/v1/webhook/radarr`

When triggered, Sublarr automatically:
1. Scans the new item for existing subtitles
2. Searches providers for missing subtitles
3. Downloads the best match
4. Translates if configured in the language profile
5. Notifies media servers to refresh the library

## Features

### Wanted System

The Wanted system tracks media items missing subtitles.

**How it works:**
1. **Scan:** Periodically checks Sonarr/Radarr libraries (or standalone folders) for items without target-language subtitles
2. **Incremental scan:** Only checks items modified since the last scan (full scan every 6th cycle)
3. **Search:** Queries all enabled providers for matching subtitles
4. **Download:** Downloads the highest-scored result
5. **Translate:** Sends through the translation pipeline if needed

**Manual actions:**
- Click **Search** on any Wanted item to trigger an immediate search
- Click **Process** to download and translate the best available result
- Use **Batch Search** to search multiple items at once

### Subtitle Scoring

Sublarr scores each subtitle result to pick the best match.

**Default Weights:**

| Match Type | Score | Description |
|------------|-------|-------------|
| File Hash | 359 | Exact file hash match (OpenSubtitles) |
| Series/Movie | 180 | Title match |
| Year | 90 | Release year match |
| Season | 30 | Season number match |
| Episode | 30 | Episode number match |
| Release Group | 14 | Release group match |
| Source | 7 | Video source (BluRay, WEB, etc.) |
| Resolution | 2 | Resolution (1080p, 720p, etc.) |
| **ASS Bonus** | **50** | ASS format preference |

Customize weights in Settings > Scoring. Per-provider modifiers (-100 to +100) let you boost or penalize specific providers.

### Forced Subtitles

Forced subtitles contain translations for foreign-language signs, songs, and dialogue that aren't in the main language.

**Per-series preference:**
- **Disabled:** No forced subtitle handling
- **Separate:** Search and manage forced subs as separate tracks
- **Auto:** Automatically detect and handle forced subs

Configure in language profiles under "Forced Preference."

### Backup and Restore

**Creating a Backup:**
1. Settings > Advanced > Backup
2. Click **Create Backup**
3. Downloads a ZIP containing config and database

**Scheduled Backups:**
1. Enable automatic backups in Backup settings
2. Set interval (e.g., daily)
3. Configure retention count
4. Backups are stored in `/config/backups/`

**Restoring:**
1. Settings > Advanced > Backup > Restore
2. Upload a backup ZIP file
3. Review the import summary
4. Confirm restoration

### Event Hooks

Extend Sublarr with custom automation.

**Shell Hooks:**
- Place shell scripts in `/config/hooks/`
- Configure which events trigger which scripts
- Event data is passed as environment variables

**Outgoing Webhooks:**
- Configure HTTP POST endpoints for events
- JSON payload with event data
- Automatic retry on failure

Available events include: `subtitle_downloaded`, `translation_complete`, `provider_failed`, `wanted_item_added`, `config_updated`, and more.

## Troubleshooting

### Common Issues

**Sonarr/Radarr connection failed**
- Verify the URL is correct and accessible from the Sublarr container
- Check the API key (found in Sonarr/Radarr > Settings > General)
- Ensure network connectivity between containers (use container names on the same Docker network)
- Check path mappings if Sonarr sees different paths than Sublarr

**Provider search returns no results**
- Verify API keys are entered correctly for providers that require them
- Enable more providers for broader coverage
- Check if the series/movie name matches what providers expect
- Try a manual search with different terms
- Check provider health in Settings > Providers (auto-disabled providers need cooldown)

**Translation quality is poor**
- Try a different Ollama model (e.g., `qwen2.5:14b-instruct` is recommended for anime)
- Adjust prompt presets in Settings > Translation > Prompt Presets
- Create a glossary for the series with frequently mistranslated terms
- Try a different translation backend (DeepL often produces better results for European languages)

**Subtitles not detected in media files**
- Ensure `ffprobe` is installed (included in the Docker image)
- Check file permissions (Sublarr needs read access to media files)
- Verify the media path mapping is correct
- Check container logs for ffprobe errors

**Standalone mode not detecting files**
- Verify the watched folder path is accessible inside the container
- Check that file extensions are supported (.mkv, .mp4, .avi, etc.)
- Wait for file stability check (files still downloading are skipped)
- Check that at least one metadata provider is configured (AniList works without API key)

**Whisper transcription fails**
- Ensure Whisper is enabled in Settings > Whisper
- For faster-whisper: check GPU availability and model download
- For Subgen: verify the Subgen API URL is accessible
- Check container logs for audio extraction errors

### FAQ

**Q: Does Sublarr replace Bazarr?**
A: Yes. Sublarr is designed as a standalone replacement for Bazarr with integrated LLM translation and ASS format priority. It does not depend on subliminal.

**Q: What subtitle formats are supported?**
A: ASS (Advanced SubStation Alpha) and SRT (SubRip). ASS is preferred for anime because it preserves styling, positioning, and typesetting. Sublarr gives ASS a +50 scoring bonus.

**Q: Can I use Sublarr without translation?**
A: Absolutely. Sublarr works as a pure subtitle downloader. Just configure providers and language profiles without a translation backend.

**Q: How does Sublarr handle signs and songs in anime?**
A: ASS subtitles have style classifications. Sublarr detects dialog styles (which get translated) and signs/songs styles (which are preserved in the original language). This prevents destroying carefully positioned typesetting.

**Q: What happens if my Ollama server is down?**
A: If you have a fallback chain configured, Sublarr automatically tries the next backend. Otherwise, the translation is queued and retried when the server comes back.

**Q: Can I install custom subtitle providers?**
A: Yes. Drop a Python plugin file into `/config/plugins/` and it will be loaded on startup (or via hot-reload if enabled). See [PROVIDERS.md](PROVIDERS.md) for the development guide.

**Q: Does Sublarr work on ARM devices (Raspberry Pi)?**
A: Yes. Docker images are built for both `linux/amd64` and `linux/arm64`. Note that LLM translation with Ollama requires significant compute resources.

**Q: How do I access the API documentation?**
A: Open `http://your-host:5765/api/docs` for the interactive Swagger UI. The OpenAPI specification is available at `/api/v1/openapi.json`.

**Q: Can I run multiple Sonarr/Radarr instances?**
A: Yes. Sublarr supports multi-instance configuration for both Sonarr and Radarr. Add additional instances in Settings.

**Q: How does the incremental scan work?**
A: Sublarr tracks timestamps and only rescans items that have been modified since the last scan. A full scan is forced every 6th cycle as a safety net. You can trigger a full scan manually from the Wanted page.
