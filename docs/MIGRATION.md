# Migration Guide: v1.0.0-beta to v0.9.0-beta

## Version Renumbering

Sublarr has adopted standard pre-release versioning. The initial v1.0.0-beta was premature -- v1.0.0 is now reserved for the final stable release after community testing. The version sequence is:

```
v1.0.0-beta (old) -> v0.9.0-beta (this release) -> v1.0.0 (stable)
```

This is not a downgrade. The software has significantly more features and stability than the original v1.0.0-beta. The version number change reflects proper Semantic Versioning where 1.0.0 signifies production-ready software.

## What's New

v0.9.0-beta is a massive feature release adding plugin extensibility, multi-backend translation (DeepL, LibreTranslate, OpenAI-compatible, Google), Whisper speech-to-text, standalone mode without Sonarr/Radarr, Plex/Kodi support, forced subtitle management, event hooks, UI internationalization (EN/DE), dark/light theming, backup/restore, statistics, OpenAPI documentation, and significant performance improvements. See [CHANGELOG.md](../CHANGELOG.md) for the complete list.

## Upgrade Steps

### Docker (Recommended)

1. **Pull the new image:**
   ```bash
   docker pull ghcr.io/abrechen2/sublarr:0.12.0-beta
   ```

2. **Stop the existing container:**
   ```bash
   docker stop sublarr
   ```

3. **Back up your data** (recommended):
   ```bash
   cp -r /path/to/appdata/sublarr /path/to/appdata/sublarr.backup
   ```

4. **Update your docker-compose.yml** (if using version tags):
   ```yaml
   services:
     sublarr:
       image: ghcr.io/abrechen2/sublarr:0.12.0-beta
       # ... rest of config unchanged
   ```

5. **Start with new image:**
   ```bash
   docker compose up -d
   ```

6. **Database migrations run automatically on startup.** No manual steps required.

### Unraid

1. Go to Docker tab in Unraid
2. Click the Sublarr container icon and select "Edit"
3. Update the Repository field to `ghcr.io/abrechen2/sublarr:0.12.0-beta`
4. Click Apply
5. The container will re-pull and restart automatically

### Configuration Changes

#### New Environment Variables

No new required environment variables. All new features are configured through the web UI Settings page.

Optional variables added for advanced use:

| Variable | Default | Purpose |
|----------|---------|---------|
| `SUBLARR_PLUGIN_HOT_RELOAD` | `false` | Enable watchdog-based plugin hot-reload |
| `SUBLARR_WHISPER_ENABLED` | `false` | Enable Whisper speech-to-text fallback |
| `SUBLARR_WHISPER_BACKEND` | `subgen` | Active Whisper backend (subgen or faster_whisper) |
| `SUBLARR_MAX_CONCURRENT_WHISPER` | `1` | Maximum concurrent Whisper jobs |

#### Removed Variables

None. All existing v1.0.0-beta environment variables continue to work.

#### Changed Defaults

None. All defaults remain the same.

### Breaking Changes

#### API Changes

No breaking API changes. All v1.0.0-beta endpoints continue to work at the same paths with the same request/response formats.

**New endpoints added** (non-breaking):
- `GET /api/v1/openapi.json` -- OpenAPI specification
- `GET /api/docs/` -- Swagger UI
- `GET /api/v1/health/detailed` -- Extended health with 11 subsystem categories
- `GET /api/v1/tasks` -- Background scheduler status
- Provider, translation, media server, whisper, standalone, hooks, and scoring management endpoints

#### Architecture Changes

The backend was refactored from a monolithic `server.py` into 15 Flask Blueprints using the Application Factory pattern. **This does not affect the public API** -- all endpoints remain at the same paths.

If you referenced internal Python modules (e.g., in custom scripts), update imports:
- `from server import app` becomes `from app import create_app`
- `from database import ...` becomes `from db.xxx import ...` (split into domain modules)

### Plugin System

Custom provider plugins can now be installed in the `/config/plugins/` directory (mapped as a Docker volume). Each plugin is a Python file implementing the `SubtitleProvider` ABC.

See [docs/PROVIDERS.md](PROVIDERS.md) for the plugin development guide.

### New Features Requiring Configuration

All new features work out of the box with sensible defaults. Optional configuration through the Settings UI:

| Feature | Where to Configure | Notes |
|---------|-------------------|-------|
| Translation backends | Settings > Translation Backends | Ollama is the default; add DeepL, LibreTranslate, etc. |
| Media servers | Settings > Media Servers | Plex, Kodi alongside existing Jellyfin/Emby |
| Whisper | Settings > Whisper | Enable and configure faster-whisper or Subgen |
| Standalone mode | Settings > Library Sources | Add watched folders for non-Sonarr/Radarr media |
| Forced subtitles | Language Profiles > Forced Preference | Per-profile forced sub handling |
| Event hooks | Settings > Events & Hooks | Shell scripts and outgoing webhooks |
| Custom scoring | Settings > Scoring | Adjust weights and per-provider modifiers |
| Language | UI header > Language switcher | Toggle between English and German |
| Theme | UI header > Theme toggle | Dark, light, or system preference |
| Backup schedule | Settings > Backup | Configure automatic backup interval |

## Troubleshooting

### Database Migration Issues

Database migrations run automatically on startup. If you encounter issues:

1. **Check container logs:**
   ```bash
   docker logs sublarr
   ```

2. **Restore from backup:**
   ```bash
   docker stop sublarr
   cp /path/to/appdata/sublarr.backup/sublarr.db /path/to/appdata/sublarr/sublarr.db
   docker start sublarr
   ```

3. **Use the built-in backup/restore:** If you created a backup via the UI before upgrading, you can restore it from Settings > Backup > Restore.

### Plugin Loading Errors

Common plugin issues and solutions:

| Problem | Solution |
|---------|----------|
| Plugin not appearing | Check file is in `/config/plugins/` with `.py` extension |
| Import errors | Ensure all dependencies are installed in the container |
| Name collision | Built-in providers always win; rename your plugin class |
| Config not saving | Check plugin `config_fields` match the expected format |
| Hot-reload not working | Enable `SUBLARR_PLUGIN_HOT_RELOAD=true` and ensure `watchdog` is installed |

### Jellyfin/Emby Migration

If you had Jellyfin/Emby configured via the old `SUBLARR_JELLYFIN_URL` / `SUBLARR_JELLYFIN_API_KEY` environment variables, these are **automatically migrated** to the new media server system on first startup. No action required.

To verify: Go to Settings > Media Servers and confirm your Jellyfin/Emby instance appears in the list.

### Performance Issues After Upgrade

The incremental wanted scan is enabled by default. If you notice missing items:

1. Trigger a manual full scan from the Wanted page
2. The system automatically runs a full scan every 6th cycle
3. Check `/api/v1/health/detailed` for subsystem status

### API Key Authentication

If you use the `SUBLARR_API_KEY` setting, all existing authenticated endpoints continue to work with the `X-Api-Key` header. New endpoints follow the same authentication pattern.

## Questions or Issues?

- Open a [GitHub Issue](https://github.com/Abrechen2/sublarr/issues) for bugs or feature requests
- Check the [User Guide](USER-GUIDE.md) for setup instructions
- Browse the [API documentation](http://localhost:5765/api/docs) via Swagger UI
