# Phase 27-01: Tag-Based Profile Assignment — Backend

## Status: Complete

## Objective

Implement automatic language profile assignment based on Sonarr/Radarr tags when
new media arrives via webhook. Allows operators to configure tag → profile rules
once and have profiles applied automatically without manual library-by-library setup.

## Files Changed

| File | Change |
|------|--------|
| `backend/db/models/core.py` | Added `TagProfileMapping` ORM model |
| `backend/db/models/__init__.py` | Exported `TagProfileMapping` |
| `backend/db/repositories/profiles.py` | Added `TagProfileMapping` import and 5 new methods |
| `backend/db/profiles.py` | Added facade functions for tag rule CRUD + lookup |
| `backend/routes/profiles.py` | Added 4 new API endpoints under `/language-profiles/tag-rules` |
| `backend/routes/webhooks.py` | Added tag resolution helpers + auto-assign calls in Sonarr/Radarr handlers |

## DB Schema

New table `tag_profile_mappings` (created automatically by `sa_db.create_all()`):

```sql
CREATE TABLE tag_profile_mappings (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    tag_label  TEXT NOT NULL UNIQUE,          -- lowercased Arr tag label
    profile_id INTEGER NOT NULL
               REFERENCES language_profiles(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL
);
```

No explicit migration script needed — Flask-SQLAlchemy's `create_all()` in `app.py`
creates the table on first startup for both SQLite (dev) and PostgreSQL (production).
For production (Alembic), generate with: `flask db migrate -m "add tag_profile_mappings"`.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/language-profiles/tag-rules` | List all rules |
| `POST` | `/api/v1/language-profiles/tag-rules` | Create rule `{tag_label, profile_id}` |
| `PUT` | `/api/v1/language-profiles/tag-rules/<id>` | Update rule |
| `DELETE` | `/api/v1/language-profiles/tag-rules/<id>` | Delete rule |

All endpoints validate that the referenced `profile_id` exists and return structured
JSON errors. UNIQUE constraint violations on `tag_label` return HTTP 409.

## Repository Methods (ProfileRepository)

- `list_tag_rules()` — ordered by `tag_label ASC`
- `create_tag_rule(tag_label, profile_id)` — normalises label to lowercase before save
- `update_tag_rule(id, tag_label=None, profile_id=None)` — partial update
- `delete_tag_rule(id)` — returns False if not found
- `get_profile_id_for_tags(tag_labels: list)` — case-insensitive match, first rule wins

## Webhook Integration

Two private helpers added to `routes/webhooks.py`:

- `_resolve_tag_labels_for_series(series_id)` — calls Sonarr `GET /series/{id}` + `GET /tag`, returns list of lowercase labels
- `_resolve_tag_labels_for_movie(movie_id)` — same for Radarr
- `_apply_tag_profile(series_id=None, movie_id=None)` — orchestrates lookup + assignment

Both `webhook_sonarr` and `webhook_radarr` handlers call `_apply_tag_profile()` in
the **request thread** (synchronously, before spawning the background pipeline thread).
This ensures the profile is assigned before the wanted scanner and search pipeline run.

**Fallback behaviour:** If no Arr client is configured, tags cannot be fetched, or no
rule matches, the existing default-profile logic is used unchanged.

## Design Decisions

1. **First-match wins**: `get_profile_id_for_tags` returns the first matching rule
   ordered alphabetically. This is deterministic and simple to reason about.
2. **Case-insensitive normalisation**: All tag labels are stored and compared in lowercase
   to avoid spurious mismatches between Sonarr and Sublarr configurations.
3. **CASCADE delete**: Deleting a language profile automatically removes its tag rules
   via the FK constraint, preventing orphan rules.
4. **No Alembic migration file**: `create_all()` handles table creation for fresh installs.
   Existing installs on PostgreSQL will need `flask db migrate && flask db upgrade`.
5. **Tag resolution is non-blocking for the pipeline**: Failures (Sonarr offline, tag
   API errors) are logged as warnings and fall through to the default profile.

## Testing Checklist (manual)

- [ ] `POST /api/v1/language-profiles/tag-rules` with valid `tag_label` + `profile_id` → 201
- [ ] Duplicate `tag_label` → 409
- [ ] `PUT` to change `profile_id` → 200
- [ ] `DELETE` → 200; second `DELETE` same ID → 404
- [ ] Sonarr webhook with a series tagged "anime" + existing rule → profile auto-assigned in DB
- [ ] Sonarr webhook with no matching tag rule → default profile used
- [ ] Sonarr offline during webhook → warning logged, pipeline continues normally
