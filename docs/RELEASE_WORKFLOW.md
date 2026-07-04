# Sublarr Release & Update Workflow

Canonical release process: how a change goes from a dev branch to production,
via a release candidate that is first validated on a **prod-data mirror** (the
RC Server) before it ever touches prod.

> **Status:** the RC-Server staging stage below is a *target* workflow. Sublarr
> today deploys straight to Cardinal (prod) via `/deploy`. Adopting this
> concept requires provisioning one staging host — see stage [3] and the
> "Decisions to make" section. Everything else already matches how Sublarr ships.
>
> Concept ported from TravStats (`docs/RELEASE_WORKFLOW.md` there).

## 1. Environments

| Stage | Host | Reachable | DB | Role |
|---|---|---|---|---|
| **Local Dev** | dev machine | backend `5765` / frontend `5173` | local | Build, tests, rehearse Alembic migrations |
| **RC Server** | **TO PROVISION** (2nd Unraid container / CT) | e.g. `:5765` | own | **Validate the RC against a copy of prod data** |
| **Prod** | Cardinal (Unraid) | `192.168.178.36:5765` | Cardinal DB | Real users |
| **Web** | SublarrWeb (CT 130) | `sublarr.de` | — | Marketing/Wiki, version badge in lockstep with `backend/VERSION` |

Prod compose: `/mnt/user/appdata/sublarr/docker-compose.yml`. Health:
`http://192.168.178.36:5765/api/v1/health`. Builds happen on the dev PC (Docker
Desktop) → GHCR; Cardinal pulls, it never builds.

## 2. Version numbering

Sublarr is pre-1.0, so today every build carries a `-beta` suffix
(`0.55.0-beta`). Fold the RC gate into that scheme:

```
   0 . MINOR . PATCH  [ -rc.N ]        (pre-1.0)
   │     │       │        │
   │     │       │        └─ release-candidate counter (one per staging round)
   │     │       └─ fix / chore / deps           →  PATCH  (0.55.1 → 0.55.2)
   │     └─ feat (new features)                  →  MINOR  (0.55.x → 0.56.0)
   └─ stays 0 until the 1.0 milestone
```

### Tag strategy

| Tag | Where | When | Immutable |
|---|---|---|---|
| `:0.X.Y-rc.N` | GHCR | RC cut, every staging round | yes |
| `:0.X.Y` `:latest` | GHCR | after promotion (byte-identical retag) | yes |

> Sublarr publishes to GHCR only (no Docker Hub mirror today). If external users
> ever pull, add a `:latest` mirror the same way TravStats does.

## 3. The pipeline (stages 0–6)

```
 [0] dev branch ──gate──▶ [1] RC cut ──▶ [2] build GHCR :0.X.Y-rc.1
                                                   │
                        ┌──────────────────────────┘
                        ▼
 [3] RC SERVER      ──▶ clone Prod data → RC-Server DB
     (to provision)     deploy :rc.N, `alembic upgrade head`, UAT on real data
                        │
              ok? ──yes─┤        no → back to [0], cut rc.N+1, re-stage
                        ▼
 [4] PROD           ──▶ deploy the SAME :rc.N image to Cardinal, health + user UAT
     (Cardinal)
                        │
              ok? ──yes─┤        no → back to [0], cut rc.N+1
                        ▼
 [5] PROMOTE        ──▶ retag rc → :0.X.Y / :latest (byte-identical)
                        ▼
 [6] RELEASE        ──▶ /release (GH release), bump SublarrWeb version badge
```

**Key difference from today:** the RC lands on the **RC Server first** (against a
copy of prod data), and only then on Cardinal. Migrations that break do so on
the mirror, never on prod. Right now `/deploy` goes straight to Cardinal — this
adds the staging gate in front of it.

## 4. Stage detail

**[0] Develop** — feature/fix branches off the trunk; keep the deploy trunk
release-clean.

**[1] RC cut** — bump `backend/VERSION`→`0.X.Y-rc.N`, update `CHANGELOG.md`,
commit, git tag, GitHub **Pre-release** (`--prerelease`, never `--latest`). The
`/deploy` skill already automates the bump + changelog; extend it to stop at the
RC-Server deploy instead of going to Cardinal.

**[2] Build** — `docker build → GHCR :0.X.Y-rc.N` (multi-arch
`linux/amd64,linux/arm64`). Run the pre-deploy checks first
(`scripts/run-tests.sh`, ruff, license audit) per CLAUDE.md.

**[3] RC Server (the staging gate)** —
1. **Clone Prod DB → RC-Server DB** so the RC runs against real data.
2. Deploy `:0.X.Y-rc.N` to the RC Server; run `alembic upgrade head`, lifting the
   prod data additively onto the new schema.
3. UAT against realistic data. **If a migration breaks here, it did NOT break prod.**

**[4] Prod (Cardinal)** — deploy the *same* validated `:rc.N` image, run the
health check, do final UAT.

**[5] Promote** (only on explicit "promote"/"final") — retag the RC to
`:0.X.Y` / `:latest` (byte-identical, `docker buildx imagetools create`).

**[6] Release** — `/release` (GitHub release), bump the SublarrWeb version badge
to match `backend/VERSION`, and keep the three-repo version lockstep
(see the `cross-repo-sync` skill).

## 5. Update tracks

| Kind | Version step | Path |
|---|---|---|
| **Feature release** | minor `0.55.x → 0.56.0` | full pipeline 0–6 |
| **Patch release** (bugfixes, deps) | patch `0.56.0 → 0.56.1` | full pipeline, batched |
| **Hotfix** (prod on fire) | patch, `fix/<slug>` | express: RC → **short** RC-Server smoke → prod → promote |
| **Dependency updates** (Dependabot) | roll into next patch RC | test, fold into the next patch |

## 6. The "RC Server = copy of prod data" invariant

Every staging run (stage 3) starts the RC Server from fresh prod data, so it stays
an honest prod mirror instead of drifting. Sublarr prod runs Postgres on Cardinal
(per the `sublarr-devlog` skill), so the clone is a `pg_dump | pg_restore`, then
`alembic upgrade head` on the RC image:

```bash
# Sketch — adapt once the RC Server host exists.
ssh root@192.168.178.36 "docker exec <cardinal-db> pg_dump -U <user> <db>" \
  | ssh root@<rc-server> "docker exec -i <rc-db> psql -U <user> -d <db>"
# then deploy the RC image; `alembic upgrade head` lifts the prod data forward.
```

A ready-made `scripts/stage-rc-from-prod.sh` can be written once the RC-Server
host + prod DB details are fixed (mirrors TravStats's script).

## 7. Decisions to make before adopting

1. **RC-Server host** — a second Unraid container on Cardinal, or a separate box?
   (TravStats uses a dedicated Proxmox CT.) This is the one prerequisite the
   concept needs.
2. **Prod DB type** — confirm Cardinal runs Postgres (assumed here) vs. SQLite;
   it changes the clone from `pg_dump/restore` to a file copy.
3. **Extend `/deploy`** — split it so it can target the RC Server (staging) vs.
   Cardinal (prod), instead of always shipping to Cardinal.
4. **RC vs `-beta` naming** — decide whether pre-1.0 keeps `-beta` and adds
   `-rc.N` only during staging, or switches wholesale to `-rc.N`.
