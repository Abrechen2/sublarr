# PostgreSQL Setup Guide

Sublarr uses SQLite by default. Switching to PostgreSQL makes sense for larger libraries,
multi-container setups, or when you need connection pooling and richer tooling.

---

## Requirements

- PostgreSQL 14 or later (16 recommended)
- `pg_trgm` extension available (bundled with standard Postgres)
- Superuser or `CREATEEXTENSION` privilege for the first run (needed to install `pg_trgm`)

---

## Quick Start — Fresh Installation

### 1. Start with the bundled compose file

```bash
POSTGRES_PASSWORD=changeme docker compose -f docker-compose.postgres.yml up -d
```

Sublarr runs Alembic migrations and installs `pg_trgm` automatically on first boot.
No manual schema setup required.

### 2. Configure via environment variable

If you use your own PostgreSQL instance, set:

```env
SUBLARR_DATABASE_URL=postgresql://user:password@host:5432/sublarr
```

All other `SUBLARR_` settings remain the same.

---

## Connection Pool Tuning

The following environment variables control the SQLAlchemy connection pool
(ignored when using SQLite):

| Variable | Default | Description |
|----------|---------|-------------|
| `SUBLARR_DB_POOL_SIZE` | `5` | Number of persistent connections |
| `SUBLARR_DB_POOL_MAX_OVERFLOW` | `10` | Extra connections allowed under load |
| `SUBLARR_DB_POOL_RECYCLE` | `3600` | Recycle connections after N seconds |

For a single-user homelab installation the defaults are fine.
For higher concurrency (multiple users, heavy API usage) increase `SUBLARR_DB_POOL_SIZE`.

---

## Migrating from SQLite

### 1. Stop Sublarr

```bash
docker compose stop sublarr
```

### 2. Dump the SQLite database to SQL

```bash
# On the host where the config volume is mounted
sqlite3 /path/to/config/sublarr.db .dump > sublarr_export.sql
```

### 3. Prepare the PostgreSQL database

```bash
# Connect to your PostgreSQL instance
psql -U postgres -c "CREATE DATABASE sublarr;"
psql -U postgres -c "CREATE USER sublarr WITH PASSWORD 'changeme';"
psql -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE sublarr TO sublarr;"
psql -U postgres sublarr -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;"
```

### 4. Convert and import the dump

SQLite and PostgreSQL SQL dialects differ. The easiest approach is to let Sublarr
recreate the schema via Alembic, then import only the data.

```bash
# Start Sublarr against the empty PostgreSQL database (schema only, no data yet)
SUBLARR_DATABASE_URL=postgresql://sublarr:changeme@localhost/sublarr \
  docker compose -f docker-compose.postgres.yml up -d

# Wait for migrations to complete, then stop
docker compose -f docker-compose.postgres.yml stop sublarr
```

### 5. Import data with pgloader (recommended)

[pgloader](https://pgloader.io) handles type coercion automatically:

```bash
pgloader sqlite:///path/to/config/sublarr.db postgresql://sublarr:changeme@localhost/sublarr
```

### 6. Restart Sublarr

```bash
docker compose -f docker-compose.postgres.yml up -d sublarr
```

Verify the import at `http://localhost:5765/api/v1/database/health`.

---

## Managed PostgreSQL (Supabase, RDS, etc.)

When using a managed provider, you may not have superuser access to run
`CREATE EXTENSION`. Install `pg_trgm` manually before starting Sublarr:

```sql
-- Run as a superuser on your provider's console
CREATE EXTENSION IF NOT EXISTS pg_trgm;
```

If the extension cannot be installed, full-text search falls back to unindexed
`LIKE` queries. Everything still works, but global search may be slower on
large libraries.

---

## Backup and Restore

The built-in backup system supports both backends:

- **SQLite:** file copy via the Python `sqlite3` backup API
- **PostgreSQL:** `pg_dump` (custom format) / `pg_restore`

`pg_dump` must be available in the Sublarr container. The official image includes it.
The `VACUUM` endpoint is SQLite-only; use `VACUUM ANALYZE` on the database server directly.

---

## Checking the Active Backend

```bash
curl http://localhost:5765/api/v1/database/health | jq .backend
# "sqlite" or "postgresql"
```

The `/api/v1/health/detailed` response also includes a `backend` field under `database`.

---

## Reverting to SQLite

Remove `SUBLARR_DATABASE_URL` from your environment (or set it to an empty string).
Sublarr will use `sqlite:///config/sublarr.db` on the next start.
