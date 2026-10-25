# Sublarr

Subtitle manager for Sonarr and Radarr. It finds, checks and repairs subtitles for your library, with a focus on anime and on getting the right subtitle for the right episode.

![Sublarr tour](https://raw.githubusercontent.com/Abrechen2/sublarr/master/assets/screenshots/tour.gif)

## Features

- **29 built-in providers**, including OpenSubtitles, SubDL, AnimeTosho, Jimaku and Kitsunekko, plus 43 opt-in providers from the Bazarr+ catalog
- **Right episode, every time:** every download is checked for season and episode, and a repair scan finds saved subtitles that belong to another episode
- **Anime-aware matching** with Sonarr's absolute episode numbers, ASS-first scoring
- **Sync** with ffsubsync and alass
- **Encoding repair:** non-UTF-8 subtitles keep their letters, broken characters ("�") are restored
- **Media servers:** refreshes Jellyfin, Plex and Emby after a download
- **Translation (optional, experimental):** Ollama or an OpenAI-compatible API when no subtitle exists in your language
- **Bazarr migration:** imports connections, language profiles and blacklist
- Single container, SQLite by default; amd64 and arm64

## Quick start

```yaml
services:
  sublarr:
    image: abrechen2/sublarr:latest
    container_name: sublarr
    ports:
      - "5765:5765"
    volumes:
      - ./config:/config        # database, backups, logs
      - /path/to/media:/media   # your media library (same path as Jellyfin/Emby sees)
    environment:
      - PUID=1000
      - PGID=1000
      - SUBLARR_MEDIA_PATH=/media
    restart: unless-stopped
```

Then open `http://<host>:5765`. New here? [Your first 10 minutes](https://sublarr.de/docs/getting-started/first-10-minutes/).

## Tags

| Tag | What it is |
|---|---|
| `latest`, `stable` | Current release |
| `X.Y.Z` | A specific release |
| `rc-latest` | Newest release candidate |

The same images are on GHCR: `ghcr.io/abrechen2/sublarr`.

## Links

- Website and docs: https://sublarr.de
- Source and issues: https://github.com/Abrechen2/sublarr
- Changelog: https://github.com/Abrechen2/sublarr/blob/master/CHANGELOG.md
- Discord: https://discord.gg/WjatsKzHXz

License: GPL-3.0 · A project by [`<abrechen2 />`](https://www.abrechen2.de/)
