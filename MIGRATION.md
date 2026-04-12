# Migration Guide

This guide covers upgrading Sublarr from any beta version to V1.0.

## General Upgrade Process

1. **Back up your database** before upgrading:
   ```bash
   # Docker: copy the config volume
   docker cp sublarr:/config /path/to/backup/

   # Or use the built-in backup API
   curl -H "X-Api-Key: YOUR_KEY" http://localhost:5765/api/v1/database/backup
   ```

2. **Pull the new image:**
   ```bash
   docker pull ghcr.io/abrechen2/sublarr:latest
   docker compose up -d
   ```

3. **Database migrations run automatically** on startup via Alembic. No manual migration commands are needed.

4. **Check the health endpoint** after upgrade:
   ```bash
   curl http://localhost:5765/api/v1/health
   ```

## Version-Specific Notes

### From < 0.31.0 (Critical Security Fixes)

**Action required:** Versions before 0.31.0 are missing critical security fixes.

- Rate limiting on login and API key endpoints was added
- Minimum password length increased from 4 to 12 characters
- Database credentials are no longer exposed in the config API
- HTTP security headers (X-Frame-Options, X-Content-Type-Options, etc.) are now set

**After upgrading:**
- Change your password if it is shorter than 12 characters
- Set `SUBLARR_API_KEY` to a strong random value if not already set

### From < 0.35.0 (Auth Security)

- Content-Security-Policy and Permissions-Policy headers added
- Webhook URLs are now validated against SSRF (internal IP ranges blocked)
- A startup warning is logged if both API key and UI auth are disabled

### From < 0.37.0 (Timestamp Migration)

- All database timestamp columns are migrated from plain TEXT to `DateTime(timezone=True)`
- Migration runs automatically and reformats existing timestamps
- Session timeout now defaults to 8 hours (was 31 days); configurable via `session_timeout_minutes`

### From < 0.46.0 (Provider Changes)

- Provider visibility now distinguishes "disabled" from "hidden" via the `providers_hidden` config key
- New sidecar discovery and management APIs added

### From < 0.47.0 (Wanted System Change)

- **Behavior change:** Wanted items are now deleted immediately after a subtitle is downloaded. Previously they accumulated with `status="found"`. This is not configurable.

### From < 0.50.0 (PostgreSQL Support)

- Full PostgreSQL support added as an alternative to SQLite
- To switch from SQLite to PostgreSQL, set `SUBLARR_DATABASE_URL` to a PostgreSQL DSN
- Settings navigation restructured (5 groups instead of 7); all settings remain accessible
- `ffmpeg_timeout` moved from General to Automation settings group

## Docker Volume Changes

The Docker container uses two volumes:

| Volume | Purpose | Changed in |
|--------|---------|------------|
| `/config` | Database, backups, logs | Unchanged since v0.11 |
| `/media` | Library root (read-only access sufficient) | Unchanged since v0.11 |

Port `5765` has been the default since v0.11 and has not changed.

### Container Security (since v0.14.0)

- Container runs as non-root user `sublarr` (configurable via `PUID`/`PGID` build args)
- Port binds to `127.0.0.1` by default (use a reverse proxy for external access)
- `read_only: true` filesystem with `tmpfs` for `/tmp`

## Environment Variables

All Sublarr config uses the `SUBLARR_` prefix. Key variables:

| Variable | Default | Notes |
|----------|---------|-------|
| `SUBLARR_API_KEY` | (empty) | **Set this** for production |
| `SUBLARR_DATABASE_URL` | `sqlite:///config/sublarr.db` | PostgreSQL DSN for PG mode |
| `SUBLARR_LOG_LEVEL` | `INFO` | DEBUG, INFO, WARNING, ERROR |
| `SUBLARR_OLLAMA_MODEL` | (none) | Model name for LLM translation |

## Troubleshooting

### Migration fails on startup

Check the container logs:
```bash
docker logs sublarr 2>&1 | grep -i "alembic\|migration\|error"
```

If a migration fails, restore your backup and report the issue.

### Password rejected after upgrade (from < 0.31.0)

Minimum password length is now 12 characters. Reset via:
```bash
docker exec sublarr python -c "
from app import create_app
from db.repositories.config_repository import ConfigRepository
app = create_app()
with app.app_context():
    repo = ConfigRepository()
    repo.delete('ui_auth_password_hash')
    print('Password reset. Visit /setup to set a new one.')
"
```

### Old Docker images filling disk

After each upgrade, clean old images:
```bash
docker system prune -f
```
