# Standalone ids: stable episode identity and a collision-free id space

Status: implemented for 1.18.0, revised after the Codex design review (see
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
`owner_key_for_item`; the pre-1.18 fallback of section 4 applies inside it). It replaces the per-module copies in
`services/embedded_extractor.py`, `services/mt_provisional.py`,
`wanted_search/process.py`, `translator/_helpers.py`, the standalone scanner,
`services/standalone_episode.py`, `services/standalone_manager.py` and the
standalone branches of the library list and series detail.

Translation jobs: `arr_context` (persisted with the job) additionally carries
`standalone_series_id` / `standalone_movie_id`, and the translator's backend
selection and glossary lookup derive the owner key from it, so a retried job
keeps its title's profile and glossary.

### 4. Pre-1.18 rows: read where they are, never moved

Existing standalone installs have positive-key rows that belong to standalone
titles (profile assignments from the Library page, the cleanup switch saved by
1.17.3, glossary entries, fansub preferences). Whether a positive key in those
tables belongs to Sonarr/Radarr or to a standalone title cannot be read from
the data: before 1.18.0 it was decided by "is the arr configured" at the
moment of the write.

Decision (maintainer, after the Codex review of the RC): **no row is moved,
rewritten or deleted because of this, at startup or ever.** Absence of
evidence never authorises moving rows. Release candidates of 1.18.0 ran a
one-time startup move; it is removed together with its startup call (no
released version ever moved rows; the `sa2_standalone_owner_keys` marker
those RCs wrote into `untracked_data_repairs` is no longer read or written
and is harmless). Instead (`services/standalone_owner_keys.py`):

* **Readers** look up the owner key (negated id) first. When the table has
  no row under it, they read the legacy positive key (= the standalone row
  id), read-only, when all of these hold (`legacy_key(owner_key, kind)`):
  * the matching arr is **not configured** (Sonarr for series, Radarr for
    movies) — a configured arr owns every positive key, so a standalone
    title then never reads one;
  * **no durable arr evidence** (`arr_evidence(kind)`): a non-empty
    `sonarr_url`/`sonarr_instances_json` (`radarr_url`/`radarr_instances_json`)
    in `config_entries`, a `wanted_items` row with a Sonarr (Radarr) id, a
    translation job whose `arr_context` carries one, for movies an automation
    queue row with a Radarr id. These are `LIMIT 1` probes, cached per
    process (found evidence sticks, "none" is re-checked after 5 minutes).
    Download/upgrade/blacklist/health history is deliberately **not** used:
    a deleted, renamed or re-imported standalone title leaves history that
    looks foreign and would switch the fallback off for standalone-only
    installs, and the scan is not cheap;
  * the title has **not claimed** its rows (`standalone_legacy_claims`, below);
  * the standalone title **exists**.
* One reader per table, so the rule lives in one place:
  `standalone_owner_keys.get_row(model, key)` for the one-row-per-title
  tables (`series_settings`, `movie_settings`, `series_language_profiles`,
  `movie_language_profiles`, `fansub_preferences`) — used by
  `ProfileRepository.get_series_profile/get_movie_profile` (so
  `db.profiles.get_profile_for_item` and every profile consumer),
  `AnidbRepository` (absolute order, series settings), `SeriesAudioRepository`,
  `FansubPreferenceRepository`, `services.series_format`,
  `services.foreign_tracks.policy.resolve_policy`,
  `services.foreign_track_cleanup`, the processing-config readers in
  `routes/subtitle_processor.py`, the overrides/resolved routes and the
  series detail; `glossary_owner_key(series_id)` for `glossary_entries`
  (all four glossary readers in `TranslationRepository`, so the glossary
  page, export, translator and suggestions). Bulk readers (library profile
  map, overrides scope tree, the track-policy sweep) map readable legacy
  rows to their owner key with `legacy_ids_as_owner_keys`; the sweep leaves
  out a legacy row whose title has its own row or claimed, and pauses (marks
  the set incomplete) for a positive row it cannot attribute while the arr
  is not configured, as it did for unknown ids before.
* **Writers** write the owner key, as before. The first write for a title
  whose legacy rows are still readable calls `claim(owner_key, kind)`: in
  the writer's own transaction it records `(kind, standalone_id)` in
  `standalone_legacy_claims` and copies every legacy row of that title that
  has no owner-key counterpart to the owner key (`INSERT ... SELECT`, and
  the glossary entries one by one). So changing one setting keeps the
  others, adding a glossary term keeps the old terms, and a later delete
  under the owner key never brings the legacy row back (the claim switches
  the fallback off for the title). The legacy rows are never changed. A
  glossary edit or delete by entry id that targets a legacy entry still
  being read through the fallback is applied to its copy instead. Writers
  go through `row_for_write(model, key)` / `claim()`; deleting a standalone
  title records a claim too, so a reused row id never inherits the old rows.
  A concurrent first write that loses the claim's primary key rolls back
  and leaves the winner's copy.
* **Sonarr/Radarr ids** (positive keys with the arr configured) behave
  exactly as before: plain primary-key reads, no claim, no copy.
* **1032 case** (Sonarr removed, a standalone series that got the same row
  id): nothing is moved. While nothing durable shows Sonarr was used, the
  standalone series reads that row read-only — accepted: reading is never
  destructive, and the first change gives the title its own rows. A stored
  Sonarr URL or a wanted row / job with a Sonarr id switches the fallback off.
* **Health findings** keyed by wanted ids (1.17.3) are not migrated or
  rekeyed. The next health scan (series scan or nightly sweep) writes each
  standalone episode's findings under its stable negative id, which is what
  the episode pages read. Rows left under an old wanted id are not shown
  there; they stay in the table (and in the report totals) until removed,
  exactly as they were before the upgrade.

New table `standalone_legacy_claims` (`kind`, `standalone_id`, `claimed_at`;
primary key `(kind, standalone_id)`), Alembic revision
`sa2_standalone_legacy_claims` (schema only, created when missing) and
`create_all()` for untracked databases.

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
  against the watched folders, with symlinks resolved, at the moment of use —
  and, independently, against `media_path` (`standalone_library.
  standalone_path_allowed`), because the series or watched folder can itself
  be a symlink out of the media tree, in which case resolving both sides
  makes the folder check pass (Codex review of 1.18.0, finding 2). Callers:
  `episode_path_in_series`, `movie_path_in_watched_folder`, the 1.17.3
  `file_path` fallback, `standalone_series_video_paths` (bulk trash /
  extract / process), the series sidecar map, the health series scan and
  sweep, and the sweep's auto-fix (a standalone finding's target must lie
  next to its video and inside `media_path`). Without `media_path` only the
  folder check applies. With `media_path` set, the scanner does not walk a
  watched folder that resolves outside it (also one turned into a symlink
  after it was added), skips symlinks under a watched folder that resolve
  out of it (one warning per scan), and the watcher's per-file entry point
  (`process_single_file`) skips such files too.
* Enumeration is safe by construction (Codex review of 1.18.0, P2a): one
  enumerator, `standalone_library.allowed_series_files(series)`, serves the
  series page, the bulk actions (`standalone_series_video_paths`), the
  sidecar map and the health scan/sweep (`series_episode_files`). It refuses
  a series folder that resolves outside `media_path` before walking it
  (`series_folder_allowed`), checks every file with `standalone_path_allowed`
  before it is parsed, and checks every `wanted_items` fallback path the
  same way, so nothing outside is inspected for subtitles or gets an
  episode row.
* Stored wanted rows are checked before use (P2b):
  `standalone_library.wanted_item_path_refusal(item)` — a standalone episode
  row against its series folder, a standalone movie (or an untagged
  `instance_name = 'standalone'` row) against the watched folders, both
  against `media_path` — runs before any preflight, ffprobe, sidecar
  detection, provider search, download, extraction, translation or MT
  replacement (`process_wanted_item`, `search_wanted_item`,
  `search_providers_for_item`, `download_specific_for_item`,
  `extract_embedded_sub` (single, batch, drain), the automation drain's
  sidecar translation, retranslation (service and route), the extract route,
  `mt_reseek._replace_original`). A refused row is skipped with status
  `skipped` and a warning; it is not deleted (a rescan drops it). Rows
  without standalone ids keep their existing `media_path` checks unchanged.
* Containment uses `realpath` on both sides, so a `media_path` that is
  itself a symlink, trailing slashes and `.`/`..` segments in stored paths
  are accepted as long as the resolved file lies inside.
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
   history; ambiguous rows stay. (Superseded: the move is removed, see the
   re-review below.)
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
    unambiguous, otherwise left alone. (Superseded: not migrated any more;
    regenerated by the next health scan, section 4.)
11. Fansub, format requirement, absolute order read only `sonarr_series_id`
    — accepted.
12. `series_audio` and `anidb_mapping` settings routes unsigned — accepted.
13. Translation `arr_context` drops standalone ownership — accepted.
14. Frontend maps wanted ids to episode ids — accepted: matched by file path.
15. `/standalone/*` contract undefined — accepted: both id forms accepted.

### Review of the implementation

A second, cold Codex review of `git diff master...HEAD` found four issues,
all fixed:

1. A positive movie id that a configured Radarr does not know fell through
   to the standalone movie of the same number (`movie_video_path`,
   `/standalone/movies/<id>`) — now not found; standalone movies are reached
   by their negative id, or by a positive id only without Radarr.
2. The wanted pipeline passed only `sonarr_series_id` / `radarr_movie_id` to
   `save_subtitle`, so a standalone download ran the post-download pipeline
   and the foreign-track cleanup without the title's settings — the owner
   keys are passed now.
3. The series ZIP export applied the Sonarr remote-path mapping to a
   standalone folder and fell back to a standalone series after a failed
   Sonarr lookup — standalone folders are used as is, Sonarr ids stay
   Sonarr's.
4. The overrides tree named standalone titles by their positive id — it uses
   the owner key now.

### Re-review of the RC (owner keys, media_path)

A further cold Codex review reported three issues; all fixed:

* P1 — the one-time owner-key move rewrote rows on the absence of evidence.
  Decided by the maintainer: removed. Pre-1.18 rows are read where they are
  and copied on a title's first change (section 4).
* P2a — the series page, the wanted-row fallback and the bulk / sidecar /
  health enumerators walked and inspected an escaped series folder before
  the containment check. One safe enumerator now (Security).
* P2b — stored standalone wanted rows whose folder now escapes `media_path`
  were still probed and searched. Checked at every pipeline entry (Security).

Follow-up Codex rounds on the fix:

* Round 1: a stale legacy glossary id could still change the old row after
  the title claimed (now refused: `superseded_legacy`); batch probe, batch
  retranslate, the wanted cleanup and bulk auto-sync bypassed the path
  guard / safe enumerator (now guarded; rows or jobs without ids count as
  standalone when tagged so or lying under a watched folder); the search's
  profile filters read the assignment without the fallback (now
  `get_row`). Not changed: priority override and minimum daily attempts
  are joined on `sonarr_series_id` only, so they never applied to standalone
  wanted rows, before or after 1.18 — a missing feature, not a regression.
* Round 2: the scheduled search's local-sidecar translation split, queued
  translation jobs (rechecked at execution from the job's `arr_context` /
  path) and the standalone glossary suggestions (folder refused, every
  sidecar filtered) now go through the guard; superseded legacy rows are
  left out of the bulk readers (overrides scope tree, sweep). Not changed:
  `/translate/batch` on a directory checks only its root against
  `media_path` and follows file symlinks inside it. That is the generic
  (non-standalone) media policy, unchanged by this work; refusing symlinked
  files there would refuse symlink-farm Sonarr libraries.
* Round 3: the arr evidence counted the automation queue's negative
  `radarr_movie_id` (a standalone movie's owner key) as Radarr use, which
  switched the fallback off for all standalone movies; only positive ids
  count now. The automation drain's foreign-track cleanup and auto-sync
  tasks are rechecked at execution (cleanup rows carry the owner keys;
  auto-sync rows are recognised by lying under a watched folder or a
  standalone series folder).
