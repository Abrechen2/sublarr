# Phase 10: Performance & Scalability - Research

**Researched:** 2026-02-16
**Domain:** Database abstraction (SQLAlchemy ORM), optional PostgreSQL, Redis caching/queuing, Prometheus/Grafana monitoring
**Confidence:** MEDIUM (large migration surface, verified libraries, but custom fallback patterns need validation at implementation time)

## Summary

This phase transforms Sublarr's data layer from raw sqlite3 with manual locking (`_db_lock` pattern) to SQLAlchemy ORM with optional PostgreSQL support, adds optional Redis for caching/sessions/job queue, and extends the monitoring stack. The current codebase has **4,167 lines across 15 db module files** with **450 raw SQL operations** and **216 import sites across 54 files**. This is by far the most invasive refactor in the project's history.

The critical architectural challenge is maintaining backward compatibility: SQLite must remain the zero-config default, Redis must be optional with graceful fallback, and all existing tests must continue passing. The migration needs to happen in carefully ordered waves -- ORM models first, then migration tooling, then optional backends, then monitoring.

**Primary recommendation:** Use Flask-SQLAlchemy 3.1 + Alembic (via Flask-Migrate) as the ORM/migration layer, with connection string switching between SQLite and PostgreSQL. For Redis, use the `redis` Python client directly with a custom abstraction layer that falls back to SQLite-backed implementations. For the job queue, implement a custom dual-backend queue manager that uses RQ when Redis is available and an in-process ThreadPoolExecutor queue (the current pattern) when not. Do NOT attempt to migrate all 450 SQL operations at once -- use a Repository pattern with a phased transition.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| SQLAlchemy | 2.0.46 | ORM + database abstraction | Industry standard Python ORM, supports SQLite + PostgreSQL with same models |
| Flask-SQLAlchemy | 3.1.1 | Flask integration for SQLAlchemy | Handles session lifecycle, app context, connection management |
| Flask-Migrate | 4.1.0 | Alembic wrapper for Flask | Standard migration tooling, supports `upgrade()` on startup |
| Alembic | 1.18.4 | Database schema migrations | By SQLAlchemy author, batch mode for SQLite ALTER workarounds |
| psycopg2-binary | 2.9.x | PostgreSQL driver | Standard PostgreSQL adapter for Python |
| redis | 7.1.x | Redis Python client | Official Redis client, sync+async APIs |
| rq | 2.6.x | Redis-based job queue | Simple, Flask-friendly, persistent jobs |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Flask-Limiter | 4.1.1 | Rate limiting with Redis backend | When Redis is available for distributed rate limiting |
| prometheus_client | 0.21.x | Prometheus metrics (already installed) | Extended metrics for PERF-07 |
| fakeredis | 2.x | Redis mock for testing | Unit tests that need Redis without a server |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Flask-SQLAlchemy | Standalone SQLAlchemy 2.0 | More control but more boilerplate; Flask-SQLAlchemy handles session scoping automatically |
| Flask-Migrate | Raw Alembic | More flexible but harder to integrate with Flask app factory; Flask-Migrate wraps it cleanly |
| RQ | Celery | Celery is heavier, requires more config; RQ is simpler for this use case |
| RQ | Huey | Huey supports SQLite queue backend but has smaller ecosystem |
| redis-py | aioredis | App uses threading (gunicorn gthread), not asyncio; sync redis-py is correct |

**Installation:**
```bash
# Core ORM + migrations
pip install SQLAlchemy==2.0.46 Flask-SQLAlchemy==3.1.1 Flask-Migrate==4.1.0 alembic==1.18.4

# Optional PostgreSQL
pip install psycopg2-binary==2.9.10

# Optional Redis + Queue
pip install redis==7.1.0 rq==2.6.1 Flask-Limiter==4.1.1

# Testing
pip install fakeredis==2.26.2
```

## Architecture Patterns

### Recommended Project Structure
```
backend/
  db/
    __init__.py           # KEPT: init_db(), get_db() -- but now returns SQLAlchemy session
    models/               # NEW: SQLAlchemy ORM models
      __init__.py          # Base model, common mixins
      jobs.py              # Job model
      wanted.py            # WantedItem model
      providers.py         # ProviderCache, ProviderStats, SubtitleDownload models
      profiles.py          # LanguageProfile, SeriesProfile, MovieProfile models
      config.py            # ConfigEntry model
      blacklist.py         # BlacklistEntry model
      hooks.py             # HookConfig, WebhookConfig, HookLog models
      standalone.py        # WatchedFolder, StandaloneSeries, StandaloneMovie models
      translation.py       # TranslationConfigHistory, GlossaryEntry, PromptPreset models
      whisper.py           # WhisperJob model
      scoring.py           # ScoringWeights, ProviderScoreModifier models
    repositories/          # NEW: Repository pattern wrapping ORM queries
      base.py              # BaseRepository with common CRUD
      jobs.py              # JobRepository
      wanted.py            # WantedRepository
      ... (mirror existing db/*.py modules)
    migrations/            # NEW: Alembic migration scripts
      versions/
      env.py
      alembic.ini
    # EXISTING domain modules kept temporarily for transition
    blacklist.py           # Refactored to use repository
    cache.py               # Refactored to use repository
    ...
  cache/                   # NEW: Cache abstraction layer
    __init__.py            # CacheBackend ABC
    redis_cache.py         # Redis implementation
    sqlite_cache.py        # SQLite fallback implementation
  queue/                   # NEW: Job queue abstraction
    __init__.py            # QueueBackend ABC
    rq_queue.py            # Redis+RQ implementation
    memory_queue.py        # In-process ThreadPoolExecutor fallback
  monitoring/              # NEW: Extended monitoring
    dashboards/            # Grafana JSON provisioning files
    metrics.py             # Extended Prometheus metrics
```

### Pattern 1: SQLAlchemy Model Definition (DeclarativeBase)
**What:** Define all 17+ tables as SQLAlchemy ORM models using modern Mapped[] annotations
**When to use:** Every table in the schema
**Example:**
```python
# Source: SQLAlchemy 2.0 official docs
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(8), primary_key=True)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    source_format: Mapped[str] = mapped_column(String(10), default="")
    output_path: Mapped[str] = mapped_column(Text, default="")
    stats_json: Mapped[str] = mapped_column(Text, default="{}")
    error: Mapped[str] = mapped_column(Text, default="")
    force: Mapped[int] = mapped_column(default=0)
    config_hash: Mapped[str] = mapped_column(String(12), default="")
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    completed_at: Mapped[str] = mapped_column(Text, default="")

    __table_args__ = (
        Index("idx_jobs_status", "status"),
        Index("idx_jobs_created", "created_at"),
    )
```

### Pattern 2: Repository Pattern for Query Abstraction
**What:** Wrap all database operations in repository classes that use SQLAlchemy sessions
**When to use:** Every existing `db/*.py` module gets a corresponding repository
**Example:**
```python
# Repository wraps session operations, replaces raw SQL
from db.models import Job
from sqlalchemy import select
from sqlalchemy.orm import Session

class JobRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, job_id: str, file_path: str, force: bool = False) -> Job:
        job = Job(id=job_id, file_path=file_path, force=int(force),
                  created_at=datetime.utcnow().isoformat())
        self.session.add(job)
        self.session.flush()
        return job

    def get_by_id(self, job_id: str) -> Optional[Job]:
        return self.session.get(Job, job_id)

    def get_pending_count(self) -> int:
        stmt = select(func.count()).where(Job.status.in_(["queued", "running"]))
        return self.session.execute(stmt).scalar() or 0
```

### Pattern 3: Cache Backend Abstraction
**What:** Abstract cache operations behind an interface with Redis and SQLite implementations
**When to use:** Provider cache, session storage, rate limiting data
**Example:**
```python
from abc import ABC, abstractmethod

class CacheBackend(ABC):
    @abstractmethod
    def get(self, key: str) -> Optional[str]: ...

    @abstractmethod
    def set(self, key: str, value: str, ttl_seconds: int = 0) -> None: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...

class RedisCacheBackend(CacheBackend):
    def __init__(self, redis_client):
        self.redis = redis_client

    def get(self, key: str) -> Optional[str]:
        return self.redis.get(key)

    def set(self, key: str, value: str, ttl_seconds: int = 0) -> None:
        if ttl_seconds:
            self.redis.setex(key, ttl_seconds, value)
        else:
            self.redis.set(key, value)

class SQLiteCacheBackend(CacheBackend):
    """Falls back to existing provider_cache table via SQLAlchemy."""
    def __init__(self, session_factory):
        self.session_factory = session_factory
    # ... uses existing provider_cache table
```

### Pattern 4: Database URL Configuration
**What:** Single environment variable switches between SQLite and PostgreSQL
**When to use:** Application startup configuration
**Example:**
```python
# In config.py Settings class
database_url: str = ""  # Empty = use default SQLite at db_path

# In db/__init__.py
def get_database_url(settings) -> str:
    if settings.database_url:
        return settings.database_url  # e.g., "postgresql://user:pass@host/sublarr"
    # Default: SQLite at configured path
    return f"sqlite:///{settings.db_path}"
```

### Pattern 5: Alembic Batch Mode for SQLite Compatibility
**What:** Configure Alembic to use batch migrations so ALTER TABLE works on SQLite
**When to use:** Always -- ensures migrations work on both SQLite and PostgreSQL
**Example:**
```python
# migrations/env.py
def run_migrations_online():
    connectable = current_app.extensions["migrate"].db.engine
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # CRITICAL for SQLite compatibility
        )
        with context.begin_transaction():
            context.run_migrations()
```

### Pattern 6: Graceful Redis Connection with Fallback
**What:** Try connecting to Redis on startup; if unavailable, use SQLite fallback for all Redis-dependent features
**When to use:** Application initialization
**Example:**
```python
def init_cache_and_queue(settings):
    redis_url = getattr(settings, "redis_url", "")
    if redis_url:
        try:
            import redis
            client = redis.from_url(redis_url, socket_connect_timeout=5)
            client.ping()  # Verify connection
            return RedisCacheBackend(client), RQJobQueue(client)
        except Exception as e:
            logger.warning("Redis unavailable (%s), falling back to SQLite", e)
    return SQLiteCacheBackend(session_factory), MemoryJobQueue()
```

### Anti-Patterns to Avoid
- **Big Bang Migration:** Do NOT rewrite all 450 SQL operations at once. Use a phased approach where repositories wrap existing raw SQL first, then convert incrementally.
- **Dual Write:** Do NOT maintain both raw SQL and ORM paths simultaneously in production. Pick one per module.
- **SQLite-specific SQL in ORM code:** Do NOT use SQLite PRAGMAs or SQLite-specific functions in ORM queries. Use SQLAlchemy's dialect-agnostic constructs.
- **Session-per-request without cleanup:** Always use Flask-SQLAlchemy's automatic session scoping via `db.session`. Never create manual sessions in request handlers.
- **Storing datetime as TEXT:** The current schema stores all datetimes as TEXT (ISO strings). The ORM models should use `DateTime` type for proper PostgreSQL compatibility, with migration handling the conversion.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Database connection pooling | Custom pool manager | SQLAlchemy QueuePool (default) | Thread-safe, configurable pool_size/overflow/recycle |
| Schema migrations | Manual ALTER TABLE scripts | Alembic via Flask-Migrate | Versioned, reversible, auto-detects schema changes |
| SQLite ALTER TABLE workarounds | Manual copy-table scripts | Alembic batch mode (`render_as_batch=True`) | Handles the full copy-data-drop-rename workflow |
| Session-scoped connections | Manual threading.Lock | Flask-SQLAlchemy session scoping | Tied to request lifecycle, automatic cleanup |
| Redis connection management | Custom retry/reconnect | `redis.from_url()` with retry config | Built-in connection pooling, auto-reconnect |
| Rate limiting | Custom token bucket | Flask-Limiter with Redis storage | Distributed, multiple strategies, tested |
| Job queue persistence | Custom file/DB queue | RQ with Redis | Proven persistence, dashboard, retries |
| Prometheus metric collection | Custom file format | prometheus_client library (already used) | Standard format, auto-registry |

**Key insight:** The biggest risk in this phase is not choosing the wrong library -- it is managing the transition from 450 raw SQL operations to ORM without breaking anything. The Repository pattern provides the seam between old and new, allowing incremental migration.

## Common Pitfalls

### Pitfall 1: SQLite DateTime vs PostgreSQL DateTime
**What goes wrong:** Current schema stores all timestamps as TEXT (ISO 8601 strings). PostgreSQL has native TIMESTAMP type. If models use `DateTime`, SQLAlchemy handles this differently per dialect.
**Why it happens:** SQLite has no real datetime type; everything is stored as text.
**How to avoid:** Use `String` type for datetime columns in ORM models initially, with a follow-up migration that converts to proper `DateTime` type. Or use SQLAlchemy's `TypeDecorator` to handle conversion transparently.
**Warning signs:** Tests pass on SQLite but fail on PostgreSQL, or vice versa.

### Pitfall 2: SQLite Batch Migration Foreign Key Issues
**What goes wrong:** Alembic batch migrations temporarily drop and recreate tables. If foreign keys have `ON DELETE CASCADE` and `PRAGMA FOREIGN_KEYS` is enabled, data can be lost.
**Why it happens:** SQLite enforces foreign keys per-connection via PRAGMA, and batch mode drops the original table.
**How to avoid:** Alembic automatically disables PRAGMA FOREIGN_KEYS during batch operations. Verify this behavior in tests. Never enable foreign key enforcement in migration context.
**Warning signs:** Data disappears after migration on SQLite, but not PostgreSQL.

### Pitfall 3: _db_lock Threading Removal Timing
**What goes wrong:** Removing the global `_db_lock` too early breaks thread safety. Removing it too late means two locking systems (SQLAlchemy pool + _db_lock) compete.
**Why it happens:** The current codebase uses a global threading.Lock for ALL database access. SQLAlchemy's connection pool is inherently thread-safe.
**How to avoid:** Remove `_db_lock` only AFTER all raw SQL in a module is converted to use SQLAlchemy sessions. Never mix the two patterns in the same module.
**Warning signs:** Deadlocks, "database is locked" errors during transition.

### Pitfall 4: RQ Requires Redis Even in Sync Mode
**What goes wrong:** Attempting to use RQ's `is_async=False` mode without Redis still fails because RQ stores job state in Redis.
**Why it happens:** RQ is fundamentally Redis-dependent. The `is_async=False` flag only controls WHERE the job runs (same process), not WHERE state is stored.
**How to avoid:** Implement a completely separate in-process queue (ThreadPoolExecutor-based) for the no-Redis fallback. Do NOT try to make RQ work without Redis.
**Warning signs:** `ConnectionError` when Redis is down, even with `is_async=False`.

### Pitfall 5: Initial Alembic Migration with Existing Data
**What goes wrong:** Running `alembic revision --autogenerate` against an existing SQLite database creates a migration that tries to recreate all tables, losing data.
**Why it happens:** Alembic doesn't know the database already has the correct schema.
**How to avoid:** Create the initial migration as an empty migration (`alembic stamp head`) that marks the current schema as "revision 1" without running any DDL. All subsequent revisions then build on that baseline.
**Warning signs:** `Table already exists` errors on startup with existing databases.

### Pitfall 6: JSON Fields in PostgreSQL
**What goes wrong:** Current schema stores JSON as TEXT columns. PostgreSQL has native JSONB type which is much more efficient for querying.
**Why it happens:** SQLite has no JSON type, so TEXT is used everywhere.
**How to avoid:** Use SQLAlchemy's `JSON` type which automatically maps to TEXT on SQLite and JSONB on PostgreSQL. Or use a custom type that provides transparent handling.
**Warning signs:** Performance degradation on PostgreSQL when querying JSON-stored data that should use JSONB operators.

### Pitfall 7: Connection Pool Exhaustion
**What goes wrong:** Long-running translation jobs hold database connections for minutes, exhausting the pool.
**Why it happens:** Default QueuePool has 5 connections + 10 overflow. Background jobs that hold connections for extended periods block new requests.
**How to avoid:** Use short-lived sessions (get, process, release). For long-running background tasks, create dedicated sessions that are committed/closed frequently. Configure `pool_size=10, max_overflow=20` for production.
**Warning signs:** `TimeoutError: QueuePool limit ... reached` in logs.

## Code Examples

Verified patterns from official sources:

### Flask-SQLAlchemy App Factory Setup
```python
# Source: Flask-SQLAlchemy 3.1 docs
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

db = SQLAlchemy()
migrate = Migrate()

def create_app():
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = get_database_url(settings)
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_size": 10,
        "max_overflow": 20,
        "pool_recycle": 3600,
        "pool_pre_ping": True,  # Verify connections are alive
    }
    db.init_app(app)
    migrate.init_app(app, db, render_as_batch=True)

    # Run migrations on startup
    with app.app_context():
        from flask_migrate import upgrade
        upgrade()

    return app
```

### SQLAlchemy Model with JSON Field (Dialect-Aware)
```python
# Source: SQLAlchemy 2.0 docs
from sqlalchemy import JSON, String, Integer
from sqlalchemy.orm import Mapped, mapped_column

class WantedItem(Base):
    __tablename__ = "wanted_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    item_type: Mapped[str] = mapped_column(String(20), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    missing_languages: Mapped[dict] = mapped_column(JSON, default=list)
    # JSON type auto-maps to TEXT on SQLite, JSONB on PostgreSQL
```

### Redis + Fallback Initialization
```python
# Verified pattern: try Redis, fallback to local
import logging

logger = logging.getLogger(__name__)

def create_cache_backend(settings):
    """Create cache backend: Redis if available, SQLite fallback."""
    redis_url = getattr(settings, "redis_url", "")
    if redis_url:
        try:
            import redis as redis_lib
            client = redis_lib.from_url(
                redis_url,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
            )
            client.ping()
            logger.info("Redis cache connected: %s", redis_url)
            return RedisCacheBackend(client)
        except ImportError:
            logger.info("redis package not installed, using SQLite cache")
        except Exception as e:
            logger.warning("Redis unavailable (%s), using SQLite cache", e)
    return SQLiteCacheBackend()
```

### RQ Job Queue with Fallback
```python
# Source: RQ docs + custom fallback pattern
from concurrent.futures import ThreadPoolExecutor

class MemoryJobQueue:
    """In-process fallback when Redis is unavailable."""
    def __init__(self, max_workers=2):
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._jobs = {}

    def enqueue(self, func, *args, **kwargs):
        job_id = str(uuid.uuid4())[:8]
        future = self._executor.submit(func, *args, **kwargs)
        self._jobs[job_id] = future
        return job_id

class RQJobQueue:
    """Redis-backed persistent queue using RQ."""
    def __init__(self, redis_client):
        from rq import Queue
        self.queue = Queue(connection=redis_client)

    def enqueue(self, func, *args, **kwargs):
        job = self.queue.enqueue(func, *args, **kwargs)
        return job.id
```

### Alembic Initial Stamp for Existing Databases
```python
# Handle existing databases that predate Alembic
# In migrations/env.py or app startup:
from alembic import command
from alembic.config import Config

def stamp_existing_db_if_needed(app):
    """Stamp existing databases as 'head' to skip initial migration."""
    migrations_dir = os.path.join(app.root_path, "db", "migrations")
    alembic_cfg = Config(os.path.join(migrations_dir, "alembic.ini"))
    alembic_cfg.set_main_option("script_location", migrations_dir)

    # Check if alembic_version table exists
    with db.engine.connect() as conn:
        inspector = sqlalchemy.inspect(conn)
        if "alembic_version" not in inspector.get_table_names():
            # Existing DB without Alembic -- stamp as current
            if inspector.get_table_names():  # Has tables = existing DB
                command.stamp(alembic_cfg, "head")
                logger.info("Stamped existing database at head revision")
```

### Extended Prometheus Metrics
```python
# Source: prometheus_client docs
from prometheus_client import Counter, Histogram, Gauge, Info

# Request metrics (add to existing metrics.py)
HTTP_REQUEST_DURATION = Histogram(
    "sublarr_http_request_duration_seconds",
    "HTTP request duration",
    ["method", "endpoint", "status"],
    buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 10.0),
)

DB_QUERY_DURATION = Histogram(
    "sublarr_db_query_duration_seconds",
    "Database query duration",
    ["operation", "table"],
    buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5),
)

CACHE_HIT_TOTAL = Counter(
    "sublarr_cache_hits_total",
    "Cache hit/miss counter",
    ["backend", "result"],  # backend=redis|sqlite, result=hit|miss
)

REDIS_CONNECTION_STATUS = Gauge(
    "sublarr_redis_connected",
    "Redis connection status (1=connected, 0=disconnected)",
)

DB_POOL_SIZE = Gauge(
    "sublarr_db_pool_size",
    "Database connection pool current size",
)

DB_POOL_OVERFLOW = Gauge(
    "sublarr_db_pool_overflow",
    "Database connection pool overflow count",
)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| declarative_base() function | DeclarativeBase class | SQLAlchemy 2.0 (2023) | Better type checking, PEP 484 compliance |
| Query.filter() | select().where() | SQLAlchemy 2.0 (2023) | Unified Core + ORM query syntax |
| db.session.query(Model) | db.session.execute(select(Model)) | SQLAlchemy 2.0 (2023) | Modern API, will be only option in 3.0 |
| Flask-Script for CLI | flask db commands (Click) | Flask-Migrate 4.x | Built-in Flask CLI integration |
| redis-py 4.x | redis-py 7.x | 2024 | Redis 7+ features, async support |
| RQ 1.x | RQ 2.x | 2024 | Python 3.9+ only, improved job handling |

**Deprecated/outdated:**
- `declarative_base()` function: Superseded by `DeclarativeBase` class in SQLAlchemy 2.0
- `Query.filter()` ORM pattern: Still works but deprecated, use `select().where()` instead
- `SQLAlchemy-Migrate` (sqlalchemy-migrate package): Dead project, replaced by Alembic years ago
- Flask-RQ2: Last updated 2020, use `pallets-eco/Flask-RQ` instead (actively maintained by Pallets team)

## Migration Scope Analysis

### Current State (what must be migrated)
| Component | Count | Complexity |
|-----------|-------|------------|
| Database tables | 25+ (in SCHEMA constant) | HIGH -- many have JSON TEXT columns |
| DB module files | 15 files, 4,167 lines | HIGH -- every file uses raw sqlite3 |
| Import sites | 216 across 54 files | HIGH -- widespread coupling |
| Raw SQL operations | ~450 execute/fetchone/fetchall | HIGH -- each needs ORM equivalent |
| Indexes | 25+ explicit indexes | MEDIUM -- translates to model __table_args__ |
| Manual migrations | _run_migrations() ~200 lines | MEDIUM -- replaced by Alembic |
| Transaction manager | 1 module (sqlite3-specific) | LOW -- replaced by SQLAlchemy sessions |
| Database backup | 1 module (SQLite backup API) | MEDIUM -- needs PostgreSQL pg_dump equivalent |
| Database health | 1 module (SQLite PRAGMAs) | MEDIUM -- needs dialect-specific health checks |

### Migration Risk Assessment
| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Data loss during schema migration | LOW | CRITICAL | Alembic stamp for existing DBs, backup before migration |
| Thread safety regression | MEDIUM | HIGH | Remove _db_lock only after full ORM conversion per module |
| SQLite vs PostgreSQL query incompatibility | MEDIUM | MEDIUM | Use only SQLAlchemy constructs, never raw SQL |
| Redis dependency creep | MEDIUM | HIGH | Strict fallback testing, no Redis in critical path |
| Performance regression from ORM overhead | LOW | MEDIUM | Benchmark before/after, use bulk operations for batch queries |

## Configuration Design

### New Settings Fields
```python
# Added to config.py Settings class:
# Database
database_url: str = ""  # Empty = use SQLite at db_path. Set to postgresql://... for PG.

# Redis (all optional)
redis_url: str = ""  # Empty = no Redis. e.g., redis://localhost:6379/0
redis_cache_enabled: bool = True   # Use Redis for provider cache (if redis_url set)
redis_session_enabled: bool = True  # Use Redis for sessions (if redis_url set)
redis_queue_enabled: bool = True    # Use Redis+RQ for job queue (if redis_url set)

# Connection pooling
db_pool_size: int = 5          # SQLAlchemy pool_size
db_pool_max_overflow: int = 10  # SQLAlchemy max_overflow
db_pool_recycle: int = 3600     # Recycle connections after N seconds
```

### Docker Compose Example (with optional PostgreSQL + Redis)
```yaml
services:
  sublarr:
    image: sublarr:latest
    environment:
      - SUBLARR_DATABASE_URL=postgresql://sublarr:secret@db:5432/sublarr
      - SUBLARR_REDIS_URL=redis://redis:6379/0
    depends_on:
      - db
      - redis

  db:  # Optional
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: sublarr
      POSTGRES_USER: sublarr
      POSTGRES_PASSWORD: secret
    volumes:
      - pgdata:/var/lib/postgresql/data

  redis:  # Optional
    image: redis:7-alpine
    volumes:
      - redisdata:/data
```

## Open Questions

1. **Datetime Type Strategy**
   - What we know: Current schema uses TEXT for all timestamps. PostgreSQL has native TIMESTAMP.
   - What's unclear: Should we migrate existing TEXT timestamps to proper DateTime in the ORM models? This would require data migration for existing SQLite databases.
   - Recommendation: Use `String` type initially for backward compatibility, then add a migration in a follow-up that converts to `DateTime` type with proper handling for both dialects.

2. **Database Backup for PostgreSQL**
   - What we know: Current backup uses SQLite's `backup()` API. This does not work with PostgreSQL.
   - What's unclear: Should we call `pg_dump` from Python, or use a different approach?
   - Recommendation: Implement a dialect-aware backup strategy: SQLite backup API for SQLite, `pg_dump` subprocess for PostgreSQL. The backup module already has a clean interface.

3. **Existing Tests and SQLite Dependency**
   - What we know: All tests use `temp_db` fixture that creates SQLite files.
   - What's unclear: Should tests also run against PostgreSQL? This requires a test PostgreSQL instance.
   - Recommendation: Keep SQLite as default test backend. Add optional PostgreSQL CI test matrix that runs the same tests against PostgreSQL when `TEST_DATABASE_URL` is set.

4. **Grafana Dashboard Provisioning Format**
   - What we know: Grafana supports JSON dashboard provisioning via YAML config pointing to JSON files.
   - What's unclear: Should dashboards be shipped in the Docker image or as a separate download/repo?
   - Recommendation: Ship dashboard JSON files in a `monitoring/grafana/` directory within the repo, with a docker-compose example that mounts them. Also provide standalone JSON downloads.

5. **RQ Worker Deployment**
   - What we know: RQ requires a separate worker process (`rq worker`).
   - What's unclear: Should the Docker image run both Flask and RQ worker, or should they be separate containers?
   - Recommendation: Single container with supervisord or Python multiprocessing to run both Flask and RQ worker. Keep it simple for the zero-config ethos. When Redis is not configured, the in-process queue handles everything in the Flask process.

## Sources

### Primary (HIGH confidence)
- [SQLAlchemy 2.0 Official Docs - Engine Configuration](https://docs.sqlalchemy.org/en/20/core/engines.html) - connection strings, pooling
- [SQLAlchemy 2.0 Official Docs - Connection Pooling](https://docs.sqlalchemy.org/en/20/core/pooling.html) - QueuePool, NullPool
- [SQLAlchemy 2.0 Official Docs - DeclarativeBase](https://docs.sqlalchemy.org/en/20/orm/declarative_tables.html) - modern model definitions
- [Alembic Official Docs - Batch Migrations](https://alembic.sqlalchemy.org/en/latest/batch.html) - SQLite compatibility, render_as_batch
- [Flask-SQLAlchemy 3.1 Docs](https://flask-sqlalchemy.readthedocs.io/en/stable/) - Flask integration, session management
- [Flask-Migrate Docs](https://flask-migrate.readthedocs.io/) - Alembic wrapper, programmatic upgrade()
- [RQ Official Docs](https://python-rq.org/docs/) - job queuing, is_async, persistence
- [Flask Official Docs - SQLAlchemy Patterns](https://flask.palletsprojects.com/en/stable/patterns/sqlalchemy/) - Flask integration patterns
- [prometheus_client Docs](https://prometheus.io/docs/instrumenting/writing_clientlibs/) - metric types, best practices

### Secondary (MEDIUM confidence)
- [Flask-Limiter 4.1.1](https://flask-limiter.readthedocs.io/) - rate limiting with Redis storage
- [Grafana Dashboard Provisioning](https://www.56k.cloud/en/blog/provisioning-grafana-datasources-and-dashboards-automagically) - JSON provisioning in Docker
- [Grafana Flask Dashboard Example](https://github.com/pilosus/prometheus-client-python-app-grafana-dashboard) - pre-built Flask metrics dashboard
- [redis-py Official Docs](https://redis.io/docs/latest/develop/clients/redis-py/) - Python Redis client
- [Redis Rate Limiting Patterns](https://redis.io/learn/howtos/ratelimiting) - algorithm comparison

### Tertiary (LOW confidence)
- [Flask + RQ Integration](https://testdriven.io/blog/asynchronous-tasks-with-flask-and-redis-queue/) - tutorial pattern (may be dated)
- [RQ GitHub Discussions on Reliability](https://github.com/rq/rq/discussions/1756) - community experience with RQ reliability
- [RQ is_async=False Limitations](https://github.com/rq/rq/issues/769) - confirms Redis still required in sync mode

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All libraries are well-established, version-verified on PyPI
- Architecture (ORM models, Repository pattern): HIGH - Standard patterns, well-documented
- Architecture (cache/queue fallback): MEDIUM - Custom abstraction layer needs implementation validation
- Migration strategy (existing data): MEDIUM - Alembic stamp approach is documented but needs careful testing
- Pitfalls: HIGH - Identified from official docs and community experience
- Grafana dashboards: MEDIUM - Standard provisioning, but custom dashboard JSON needs creation

**Research date:** 2026-02-16
**Valid until:** 2026-03-16 (30 days -- libraries are stable, versions pinned)
