# Standalone ids: stable episode identity and a collision-free id space

Status: proposed for 1.18.0, revised after the Codex design review (see
"Review log"). "Per-gap status" lists what is deferred.

## Problem

Standalone mode (watched folders, no Sonarr/Radarr) reuses the API and the
tables that were built around Sonarr and Radarr ids:

* A standalone **episode** has no row of its own. The series detail hands the
  UI the `wanted_items` id while the episode misses a subtitle and a synthetic
  `-(index + 1)` once it is satisfied. The wanted id changes on every rescan
  (rows are deleted and re-inserted) and the synthetic id is a list position,
  so per-episode routes (tracks, remux, health, combine, upload, the series
  sidecar map) answer 404 for satisfied episodes and cannot key anything
  durable (health findings) by them.
* A standalone **series/movie** id is the `standalone_series.id` /
  `standalone_movies.id` autoincrement. It is written into tables keyed by a
  Sonarr series id or Radarr movie id (`series_language_profiles`,
  `movie_language_profiles`, `series_settings`, `movie_settings`,
  `glossary_entries.series_id`, `fansub_preferences`). Sonarr series 5 and
  standalone series 5 share one row.
* Routes decide "is this id standalone?" by `get_sonarr_client() is None`
  (series) or "standalone row exists first" (movies). With Sonarr and
  standalone configured at the same time (mixed mode) a standalone id is sent
  to Sonarr, and a Radarr movie id is answered with the standalone movie that
  happens to share the number.
* Most profile lookups only know `sonarr_series_id` / `radarr_movie_id`, so a
  standalone title always gets the default profile.

## Design

### 1. Id space: a negative id is a standalone id

Sonarr and Radarr ids are positive (both are database autoincrements starting
at 1; Sonarr/Radarr never hand out 0 or negative ids). Sublarr's own
standalone ids are positive too. On the **wire** and in **Sublarr-owned tables
keyed by a Sonarr/Radarr id**, a standalone object is represented by its
negated id:

| object | wire id / owner key | internal id |
| --- | --- | --- |
| Sonarr series / episode, Radarr movie | `+id` (unchanged) | same |
| standalone series | `-standalone_series.id` | `standalone_series.id` |
| standalone movie | `-standalone_movies.id` | `standalone_movies.id` |
| standalone episode | `-standalone_episodes.id` | `standalone_episodes.id` |

The sign is the source flag: it travels through every URL, query parameter,
JSON body, React Query cache key and DB key without a second field, so two
objects can never share an id. API objects additionally carry
`source: "standalone"` (already present on series/movies, added to episodes)
and the positive `standalone_id` for clients that want the raw row id.

All conversions live in one module, `services/media_ids.py`:

* `standalone_key(internal_id) -> -internal_id`
* `standalone_id_from(wire_id) -> internal_id | None` (None for `wire_id >= 0`)
* `resolve_series_ref(series_id)` / `resolve_movie_ref(movie_id)` return a
  small frozen dataclass (`kind` = `"sonarr"|"radarr"|"standalone"`,
  `arr_id`, `standalone_id`, `key`). Rules:
  * negative id -> standalone (whatever arr is configured);
  * positive id with the arr client configured -> the arr (Sonarr mode is
    unchanged byte for byte);
  * positive id without the arr client -> **legacy** standalone id (clients
    and bookmarks from <= 1.17.x keep working); its owner key is still the
    negated id.
* `owner_key_for_item(wanted_item)` -> `(series_key, movie_key)` for the four
  owner columns of a wanted item.

Routes that take a series/movie/episode id use `<int(signed=True):...>` so a
negative id reaches the handler. Positive ids behave exactly as before.

Werkzeug's default `int` converter rejected negative numbers with 404, so no
existing client can have relied on a negative id meaning anything else; the
only previous negative ids were the 1.17.3 stand-ins, handled below.

### 2. Stable standalone episodes: `standalone_episodes`

New table (model `StandaloneEpisode`, repository
`db/repositories/standalone_episodes.py`):

| column | type | notes |
| --- | --- | --- |
| id | Integer PK, `sqlite_autoincrement=True` | wire id is `-id`; never reused after a delete (SQLite `AUTOINCREMENT`, PostgreSQL sequence) |
| standalone_series_id | Integer NOT NULL, indexed | no FK, like `wanted_items.standalone_series_id`; cleaned up in code |
| file_path | Text NOT NULL, UNIQUE | the identity: one row per video file |
| season, episode | Integer NULL | parsed SxxEyy, display only |
| created_at, updated_at | DateTime(tz) NOT NULL | |

Rows are written by `upsert_episode(series_id, file_path, season, episode)`
(look up by `file_path`, insert or move to the new series; an insert that
loses a race on the unique `file_path` rolls back and re-reads the winner,
the pattern `upsert_standalone_movie` already uses): by the standalone
scanner for every episode file of a series group, and by the series detail for
every file it enumerates (so an install that has not rescanned since the
upgrade still gets ids). The id therefore survives subtitle downloads,
rescans and wanted-row churn; it changes only when the file is renamed (a new
file is a new episode, which is correct for subtitles keyed by path).

Rows are removed with their series (`delete_series_cascade`) and by the
scanner's stale cleanup when the file is gone (same reachability guard as the
wanted cleanup: nothing is deleted while a watched root is unreachable).

Resolution (`services/standalone_episode.py`, `services/episode_video_path.py`):

* negative id -> `standalone_episodes` row -> its `file_path`.
* Every standalone path, new or legacy, goes through one check before use:
  an existing video file that resolves (`is_safe_path`, symlinks and `..`
  resolved) inside the folder of the standalone series that owns it. This
  includes the legacy positive wanted-row branch, which used to trust the
  stored path. Standalone movie files must resolve inside a watched folder.
* `file_path` query parameter (1.17.3 clients): if the id row's path differs
  from the given path, or the id is unknown, fall back to the 1.17.3
  path-based lookup (path must resolve inside a known standalone series folder
  and be a video file). The old `-(index + 1)` stand-ins therefore keep
  working from a stale browser tab.
* positive id without Sonarr -> legacy wanted-row id (unchanged).
* positive id with Sonarr -> Sonarr (unchanged).

The search/interactive/download/history routes keep needing a wanted row; the
existing resolver finds or creates it from the episode's `file_path`, now with
the series' own profile language instead of the default profile's.

### 3. Owner keys in Sublarr tables

`series_language_profiles.sonarr_series_id`, `series_settings.sonarr_series_id`,
`fansub_preferences.sonarr_series_id`, `glossary_entries.series_id`,
`movie_language_profiles.radarr_movie_id`, `movie_settings.radarr_movie_id`
store `-standalone_id` for standalone titles. No schema change: the columns
are plain integers without foreign keys. Because the wire id of a standalone
series equals its owner key, the routes that write these tables
(`/profiles-overrides/series/<id>`, `/series/<id>/fansub-prefs`, glossary
`series_id`, profile assignment `arr_id`, ...) store the right key without
translation; legacy positive ids in standalone-only installs are translated by
`resolve_series_ref` before the write.

`series_settings` also carries the AniDB `absolute_order` flag, the audio
track preference, the subtitle format requirement and the processing config,
so those readers (`metadata_enrichers`, `series_format`, `series_audio`,
`anidb_mapping` routes) use the owner key too; fansub scoring reads
`fansub_preferences` by the owner key.

Readers use one resolver, `db.profiles.get_profile_for_item(item)`
(series -> movie -> default, with the standalone columns mapped through
`owner_key_for_item`). It replaces the per-module copies in
`services/embedded_extractor.py`, `services/mt_provisional.py`,
`wanted_search/process.py`, `translator/_helpers.py`, the standalone scanner,
`services/standalone_episode.py`, `services/standalone_manager.py` and the
standalone branches of the library list and series detail.

Translation jobs: `arr_context` (persisted with the job) additionally carries
`standalone_series_id` / `standalone_movie_id`, and the translator's backend
selection and glossary lookup derive the owner key from it, so a retried job
keeps its title's profile and glossary.

### 4. Moving existing standalone rows to their owner key

Existing standalone installs have positive-key rows that belong to standalone
titles (profile assignments from the Library page, the cleanup switch saved by
1.17.3, glossary entries, fansub preferences). Whether a positive key in those
tables belongs to Sonarr or to a standalone series cannot be read from the
data: before 1.18.0 it was decided by "is a Sonarr client configured" at the
moment of the write.

So the move is a **one-shot startup repair**, not an Alembic data migration:
it needs the effective configuration (environment plus `config_entries`
overlay), which Alembic's `env.py` does not load.
`services/standalone_owner_keys.py::migrate_legacy_owner_keys()` runs once per
database after the settings overlay is loaded, for tracked and untracked
databases alike, recorded by a marker row (`sa2_standalone_owner_keys`) in the
existing `untracked_data_repairs` marker table, in one transaction with the
data change (same contract as the untracked repairs: a failure leaves no
marker and is retried next start, never blocks startup):

* series side, only when **no Sonarr instance is configured and the data
  shows no Sonarr history** (no `wanted_items` row with a `sonarr_series_id`,
  no `search_series` row): each row whose
  positive key `K` is an existing `standalone_series.id` and that has no
  `-K` row yet is rewritten to `-K` (`UPDATE ... SET key = -K`). Rows that
  would collide stay where they are.
* movie side, only when **no Radarr instance is configured and no
  `wanted_items` row has a `radarr_movie_id`**: same for
  `standalone_movies.id`.
* health findings (series side, same condition): a finding whose
  `episode_id` is a standalone wanted row id and whose target is that video
  or a sidecar next to it (same folder, file name starts with the video's
  stem) is rekeyed to the episode's negative id; anything else is left as is.
* With the arr configured, or any sign it was used, nothing is moved: the
  rows may be the arr's, and an ambiguous row is kept where it is rather than
  guessed (logged once with the count).
* The marker table is created for tracked databases as well, and the marker
  row is inserted in the same transaction as the moves before they run; a
  concurrent second starter fails on the marker's primary key and rolls back.

No row is deleted and no value is changed besides the key, so nothing is lost;
an install that had a Sonarr period keeps its positive rows and its standalone
titles start on the inherited defaults (logged once).

### 5. Migration `sa1_standalone_episodes` (Alembic)

* `revision = "sa1_standalone_episodes"`, `down_revision =
  "tvp1_track_variant_policy"` (current head).
* `upgrade()`: create `standalone_episodes` and its two indexes when the table
  is missing (`sa.inspect(...).has_table`); then `backfill_episodes(conn)`.
* `backfill_episodes(conn)` (also registered in `db/untracked_data_repairs.py`
  for untracked databases, where `create_all()` creates the table): select
  `wanted_items` rows with `item_type = 'episode'`, a non-empty `file_path`
  and a `standalone_series_id` that exists in `standalone_series`; one row per
  `file_path` (lowest series id wins when two disagree); season/episode parsed
  from `season_episode` (`S01E02`) in Python; insert only paths not yet in
  `standalone_episodes`. Plain SQL with bound parameters; no
  dialect-specific `INSERT OR IGNORE` / `ON CONFLICT`, so it runs on SQLite and
  PostgreSQL, and a second run inserts nothing (idempotent).
* `downgrade()`: delete health findings keyed by a negative episode id (they
  would point at ids a later upgrade hands out again), then drop the indexes
  and the table. Owner-key rows stay; a downgraded build simply does not read
  them.
* `env.py` takes `pg_advisory_xact_lock` instead of the session lock it
  released before the commit, so a second migrator waits until the first one
  has committed (Codex finding 5).
* PostgreSQL: the migration runs under the advisory lock `env.py` already
  takes; the timestamp columns use `DateTime(timezone=True)` like every other
  table.

Episodes whose wanted rows were already drained (fully subtitled before the
upgrade) are not in `wanted_items`; they get their row from the next scan or
the first series detail view. Their old `-(index + 1)` ids keep resolving via
the `file_path` fallback, so nothing breaks in between.

## API compatibility

* Sonarr/Radarr mode: every positive id resolves exactly as before; no
  response field changes (`source` is only added to standalone objects). The
  `int(signed=True)` converters accept a superset of the old URLs.
* Standalone mode, old clients: positive standalone ids keep working on every
  route (legacy branch). Responses now carry the negative id in `id` and the
  row id in `standalone_id`. Documented in the changelog under "Changed".
* Mixed mode: the negative id is unambiguous on every route; positive ids go
  to the configured arr. The movie routes' old "standalone row first" lookup
  for a positive id is replaced by "Radarr when configured, else standalone"
  — the old order answered a Radarr movie with an unrelated standalone movie.
* `/api/v1/standalone/*` (standalone-only namespace) accepts both the
  positive row id and the negative wire id for a series/movie and returns the
  row as before plus `standalone_id`; poster URLs keep the positive row id.
* Which titles the library list shows is unchanged (standalone series only
  when Sonarr returns none, standalone movies only when Radarr returns none).
  Listing both at once is now safe id-wise but is a product decision.

## Security

* Paths still come only from our own records (`standalone_episodes.file_path`,
  `standalone_series.folder_path`, `standalone_movies.file_path`) or, for the
  1.17.3 `file_path` parameter, from a client path that must resolve
  (`security_utils.is_safe_path`, symlinks and `..` resolved) inside a known
  standalone series folder and be an existing video file.
* A negative id cannot be used to reach a Sonarr/Radarr path, and a positive
  id never reaches a standalone record while the arr is configured.
* The scanner follows directory symlinks, so a recorded path is not trusted
  by itself: the resolver re-checks every standalone episode path (new and
  legacy branch) against its series folder and every standalone movie path
  against the watched folders, with symlinks resolved, at the moment of use.
* No path-handling rule is widened (see item 6).

## Per-gap status

| # | gap | resolution |
| --- | --- | --- |
| 1 | stand-in ids on per-episode routes | stable `-standalone_episodes.id`; tracks, remux, health, combine, upload, sidecar list and the series sidecar map resolve it; signed route converters |
| 2 | standalone per-series/per-movie profiles | owner keys + `get_profile_for_item`; target languages (scanner, detail, episode resolver), provider/scoring/cutoff filters, translation backend, glossary, MT keep-seeking, embedded extraction follow the assigned profile; profile assignment accepts the negative id |
| 3 | health series scan and sweep | series scan of a standalone series walks its episodes with their negative ids; the sweep also covers standalone series (findings keyed by the negative id) |
| 4 | wrong-episode audit false positives | standalone series title/aliases and AniDB absolute number (when the AniDB mapping knows it) feed the gate like Sonarr's; for anime series without an absolute number a bare number past the episode's own is left alone, like `_may_be_absolute` already does for `S01E<n>` |
| 5 | single-title wanted scan | `scan_series(-id)` / `scan_movie(-id)` run the standalone scanner for that title; positive ids unchanged |
| 6 | watched folders outside `media_path` | **deferred, product decision** — see below |
| 7 | mixed mode | negative ids + `resolve_series_ref` / `resolve_movie_ref` replace the "no Sonarr client" signal in the routes and services that branched on it (series detail, sidecar map, settings/overrides, NFO, export, batch extract/delete/process, video sync bulk, wanted list/search filters, foreign-track settings ids and override paths) |

### Item 6: deferred

About 60 file endpoints check `is_safe_path(path, settings.media_path)` (some
also `extra_media_paths`) with no shared helper. Making enabled watched
folders count as allowed roots means touching each of those security checks
and widens what a UI-editable setting (a watched folder can be added from the
settings page) can make Sublarr read, write and move to the trash. The
per-episode and per-movie resolvers already return standalone paths from our
own records without a `media_path` check, so episode and movie actions work;
what stays refused is path-parameter endpoints (e.g. the health fix endpoint,
subtitle editor saves) for watched folders outside `media_path`.

Recommendation: introduce `security_utils.allowed_media_roots()` (media path,
extra media paths, enabled watched folders, each `realpath`'d and rejected if
it is `/` or a system directory) and `is_in_media_roots(path)`, then migrate the
call sites one route group at a time with a test per group. Until then the
documented workaround is to put watched folders under `media_path` or list
them in `extra_media_paths`.

## Review log

Codex (`codex exec --sandbox read-only`) reviewed the first draft against the
code. Disposition:

1. Doc claimed "implemented" — accepted, status changed.
2. Startup move could hand a former Sonarr period's rows to standalone titles
   — accepted: the move also requires the data to show no Sonarr/Radarr
   history; ambiguous rows stay.
3. SQLite may reuse autoincrement ids — accepted: `sqlite_autoincrement=True`.
4. Downgrade drops identities that health findings still reference —
   accepted: downgrade deletes negative-id findings first.
5. PostgreSQL advisory lock released before commit — accepted:
   `pg_advisory_xact_lock`.
6. Lookup-then-insert races on `file_path` — accepted: IntegrityError
   rollback and re-read. Serialising the untracked startup repairs is not
   done: untracked databases are SQLite (single writer) in practice and the
   backfill is idempotent.
7. Marker table only exists for untracked databases, check outside the
   transaction — accepted (see section 4).
8. Scanner follows symlinks, movie resolver only checks `isfile` — accepted:
   containment re-checked at use for episodes and movies.
9. Legacy positive-id branch trusts stored paths — accepted: same check.
10. Existing health findings keyed by wanted ids — accepted: rekeyed when
    unambiguous (section 4), otherwise left alone.
11. Fansub, format requirement, absolute order read only `sonarr_series_id`
    — accepted.
12. `series_audio` and `anidb_mapping` settings routes unsigned — accepted.
13. Translation `arr_context` drops standalone ownership — accepted.
14. Frontend maps wanted ids to episode ids — accepted: matched by file path.
15. `/standalone/*` contract undefined — accepted: both id forms accepted.
