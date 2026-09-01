# Sublarr Release Workflow — 3-Tier (Prod / RC / Beta)

Sublarr runs three isolated tiers, all on Cardinal (Unraid, `192.168.178.36`),
each its own Docker Compose project. Modelled on the TravStats 3-tier workflow,
adapted to Sublarr's media-locality (the library is local to Cardinal).

> Supersedes the earlier "RC-Server to provision" draft — the RC tier now exists
> and this describes the implemented system (established 2026-07-09).

## Tiers

| Tier | Port | Compose project | Path | Image | DB | Media |
|---|---|---|---|---|---|---|
| **Prod** | 5765 | `sublarr` | `/mnt/user/appdata/sublarr` | `:X.Y.Z` / `:latest` / `:stable` | real | local library (rw) |
| **RC** | 5766 | `sublarr-rc` | `/mnt/user/appdata/sublarr-rc` | `:X.Y.Z-rc.N` | **prod mirror** (re-cloned each round) | `/mnt/user/Sublarr-RC-Media` (rw) |
| **Beta** | 5767 | `sublarr-beta` | `/mnt/user/appdata/sublarr-beta` | rolling `:beta` (+ `:beta-<shortsha>`) | own seed | `/mnt/user/Sublarr-Beta-Media` (rw) |

- **Prod** is only ever deployed **promoted final tags**, never `-rc.N` or `:beta`.
- **RC** is a **prod-data mirror**, re-cloned from prod each RC round (see below).
- **Beta** is **internal only** (no public tunnel). The `:beta` image on GHCR is the
  artifact self-host testers pull; the Cardinal Beta instance is a dogfooding box.
- Non-prod tiers set `SUBLARR_STATS_ENDPOINT=""` so RC/Beta never ping the usage-stats
  aggregate.

## Pipeline

| Command | Builds | Deploys | Notes |
|---|---|---|---|
| **`/deploy-beta`** | `master` HEAD → `:beta` (+ `:beta-<shortsha>`), **amd64-only** | Beta :5767 | On-demand bleeding edge. No version bump / tag. `:beta` is GHCR-only. |
| **`/deploy`** | `:X.Y.Z-rc.N`, multi-arch | RC :5766 | After deploy, **mirrors prod DB into RC** via `stage-rc-from-prod.sh`. Per-release candidate. |
| **`/release`** | retag rc → `:X.Y.Z` / `:latest` / `:stable` | Prod :5765 | Promote-only, byte-identical to the tested RC. |

- `:beta` is amd64-only for fast, frequent on-demand builds; RC and final tags stay
  multi-arch (amd64 + arm64) for Raspberry Pi / Apple-Silicon self-hosters.

## Release gate — before `/release` promotes anything

Check these in order. Any "no" blocks the promotion, not the next RC.

1. **Data-changing migrations are declared.** Every migration in this release
   that deletes or rewrites rows appears in the version's **Upgrade notes** by
   revision id, with "back up your database before upgrading" above it.
   Schema-only migrations just get a line. Deriving this from the changelog
   prose does not count — the operator reads the notes to decide whether to
   back up.
2. **Each cleanup migration's writer is closed.** If a migration removes bad
   data, the code that produced it is fixed in the same release. Otherwise the
   next run recreates it and the migration silently becomes permanent.
3. **The RC ran under real load long enough to be believed.** For releases
   carrying data-path changes that means a multi-day watch on a full library,
   not a smoke test — see `~/SUBLARR-WATCH.md` on CT142 for the running one.
4. **The watch is green on its own terms**, i.e. `sublarr-findings.log` has no
   unresolved `ERNST` line. Health endpoints being up is not the same thing.

## RC prod-data mirror

Each RC round re-clones prod's Postgres into RC so the RC validates against real state:

```bash
FORCE=1 bash scripts/stage-rc-from-prod.sh
```

The script stops the RC app, drops+recreates the RC DB, `pg_dump | psql` from prod, and
restarts RC. It is **hard-guarded**: it refuses any target but `sublarr-rc-postgres`, and
requires `FORCE=1` — it must never run against Prod or Beta.

## Registries

- **GHCR** (`ghcr.io/abrechen2/sublarr`) — primary; receives everything (`:beta`, `-rc.N`, finals).
- **Docker Hub** (`docker.io/abrechen2/sublarr`) — mirrors final tags + rolling `:rc-latest`.
  `:beta` stays GHCR-only.

## Beta compose (canonical reference)

Lives only on Cardinal at `/mnt/user/appdata/sublarr-beta/docker-compose.yml` (no compose
files are committed to this repo). It mirrors the RC stack: `sublarr-beta` /
`sublarr-beta-postgres` / `sublarr-beta-redis`, port `5767:5765`, `image:
ghcr.io/abrechen2/sublarr:beta`, `env_file: sublarr-beta.env`, volumes
`/mnt/user/appdata/sublarr-beta/config:/config` + `/mnt/user/Sublarr-Beta-Media:/media:rw`,
named volume `pgdata-beta`. The Beta env is a copy of `sublarr-rc.env` with
`SUBLARR_DATABASE_URL` (beta Postgres), `SUBLARR_REDIS_URL` (beta redis), and
`SUBLARR_STATS_ENDPOINT=""` overridden.

Teardown: `docker compose -p sublarr-beta down -v && rm -rf /mnt/user/appdata/sublarr-beta /mnt/user/Sublarr-Beta-Media`.

## Homepage

The homelab Homepage dashboard (CT116, `/opt/homepage/config/services.yaml`) lists all
three tiers under the **Sublarr** group: Prod `:5765`, RC `:5766`, Beta `:5767`.
