# Frequently Asked Questions

---

## General

### What is Sublarr?

Sublarr is a self-hosted subtitle manager for anime and media libraries. It searches subtitle providers, scores and downloads the best match (ASS-first for anime), and translates subtitles into your target language using a local LLM — all without sending your data to third-party services.

### Does Sublarr replace Bazarr?

Sublarr is a Bazarr alternative, not a drop-in replacement. Key differences:

- Sublarr is anime-first (ASS format preferred, fansub scoring, AniDB integration)
- Sublarr includes LLM translation (Bazarr does not)
- Sublarr has fewer providers than Bazarr, but they are the most important ones for anime
- Bazarr supports more obscure providers and languages

For anime-heavy libraries with a focus on translation quality, Sublarr is the better choice.

### Is Sublarr free?

Yes. Sublarr is open source under GPL-3.0. The only paid components are third-party services you may optionally use (e.g., DeepL API, OpenSubtitles VIP, OpenAI API). Ollama itself (used for local LLM translation) is also free.

---

## Setup

### What is the minimum setup?

1. Set `SUBLARR_MEDIA_PATH` to your media directory
2. Set `SUBLARR_OLLAMA_URL` if Ollama is not on localhost
3. Add at least one provider API key (or use AnimeTosho which requires no key)

That is enough to get started. Everything else has sensible defaults.

### Do I need Sonarr or Radarr?

No. Enable standalone mode with `SUBLARR_STANDALONE_ENABLED=true` and Sublarr will watch your media directory directly. However, Sonarr/Radarr integration gives you better episode metadata and automatic webhook triggers.

### What model should I use for translation?

For Japanese to English/German anime translation, `qwen2.5:14b-instruct` gives the best quality. If you have limited VRAM (under 8GB), use `qwen2.5:7b-instruct`. Both significantly outperform basic machine translation for anime dialogue.

### Why is my translation slow?

LLM translation is CPU/GPU-bound. Factors affecting speed:

- **Model size**: 14B is ~2x slower than 7B
- **Batch size**: Smaller batches (`SUBLARR_BATCH_SIZE=10`) are safer but slower
- **Hardware**: GPU with sufficient VRAM is much faster than CPU
- **Context length**: Longer subtitles take more time per batch

For faster throughput, use a 7B model on GPU and set `SUBLARR_BATCH_SIZE=20`.

---

## Subtitles

### ASS vs SRT — what should I use?

For anime, always prefer ASS. ASS files from fansub groups include:
- Styled dialogue (fonts, colors, positioning)
- Typesetting for signs and overlays
- Karaoke effects

SRT is plain text only. Sublarr scores ASS +150 points above SRT and will never downgrade from ASS to SRT during upgrades.

### Why is Sublarr not downloading subtitles?

Common causes:

1. **No matching provider found** — check which providers are enabled and have API keys
2. **Provider circuit breaker OPEN** — a provider failed too many times; wait for cooldown or reset in Settings
3. **Item not in Wanted queue** — check the Wanted page to see if the file was scanned
4. **Path mapping wrong** — if Sonarr and Sublarr use different mount paths, set `SUBLARR_PATH_MAPPING`
5. **Language profile not set** — the series needs a language profile assigned in Library

Check **Queue** and **Activity** pages for error details.

### Why are subtitles not appearing in Jellyfin after download?

Sublarr triggers a library refresh automatically after each download. If subtitles do not appear:

1. Verify the media server is configured in Settings → Media Servers
2. Check that the API key is correct (use the Test button)
3. Make sure Sublarr and Jellyfin see the same file paths (check path mapping)
4. Manually trigger a library scan in Jellyfin

### Can Sublarr translate existing subtitles?

Yes. Go to **Library → Series → Episode** and click the translate button on any existing subtitle. You can also re-translate if the model or prompt changes.

### What subtitle formats are supported?

- **Download:** ASS, SSA, SRT, VTT (provider-dependent)
- **Translation:** ASS and SRT
- **Conversion:** ASS ↔ SRT ↔ SSA ↔ VTT via the Format Conversion tool
- **OCR:** PGS and VobSub image-based tracks via Tesseract

---

## Translation

### What languages are supported?

Any language pair supported by your chosen LLM or translation backend. Ollama models are particularly good at:
- Japanese → English
- Japanese → German
- Chinese → English
- Korean → English

For European language pairs, DeepL or LibreTranslate may give better results than Ollama.

### Can I use a custom translation prompt?

Yes. In **Settings → Translation → Prompt Presets**, create a custom preset or use one of the 5 built-in templates (Anime, Documentary, Casual, Literal, Dubbed). The prompt supports `{source_language}` and `{target_language}` placeholders.

### What is Translation Memory?

Translation Memory caches previous translations. When the same (or very similar) subtitle line appears again, Sublarr reuses the cached translation instead of calling the LLM. This significantly speeds up re-translation of series with consistent dialogue patterns.

Cache matching uses:
- **SHA-256 exact match** — identical lines are reused immediately
- **difflib similarity** — lines above 90% similarity threshold reuse the cached translation

---

## Performance

### Sublarr uses a lot of CPU during scanning

The wanted scanner runs ffprobe on every video file to detect existing embedded subtitles. On large libraries this can be CPU-intensive. Reduce the impact by:

- Setting `SUBLARR_SCAN_METADATA_MAX_WORKERS=2` (default is 4)
- Enabling incremental scanning (only changed files are rescanned)
- Increasing the scan interval: `SUBLARR_WANTED_SCAN_INTERVAL_HOURS=12`

### Can I use PostgreSQL instead of SQLite?

Yes. Set `SUBLARR_DATABASE_URL=postgresql://user:pass@host:5432/sublarr`. PostgreSQL is recommended for libraries with 1000+ series or concurrent access from multiple processes.

---

## Updates & Backup

### How do I update Sublarr?

```bash
docker pull ghcr.io/abrechen2/sublarr:latest
docker compose up -d
```

Check CHANGELOG.md for breaking changes before updating.

### How do I backup my configuration?

**Settings → System → Backup** creates a ZIP containing the database and config. Automatic backups run on a configurable schedule. Backup files are stored at `SUBLARR_BACKUP_DIR` (default: `/config/backups`).

### How do I restore a backup?

**Settings → System → Restore** → upload your backup ZIP file. This replaces the current database and config. Sublarr restarts automatically after restore.
