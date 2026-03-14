# Sublarr Wiki — Design Spec

**Date:** 2026-03-14
**Status:** Approved
**Folder:** `Z:\CC\SublarrWiki\`

---

## Overview

A self-hosted Wiki.js instance for Sublarr documentation, modeled on the Sonarr wiki (wiki.servarr.com/sonarr). Full wiki covering user docs, settings reference, and developer documentation. Content is mirrored to a separate GitHub repository via Wiki.js Git sync.

---

## Infrastructure

| Component | Details |
|-----------|---------|
| Platform | Proxmox LXC CT 115 on pve-node1 (192.168.178.171) |
| OS | Ubuntu 22.04 LXC |
| Resources | 2 vCPU, 2 GB RAM, 20 GB disk |
| Runtime | Docker Compose |
| Wiki engine | Wiki.js v2 (`ghcr.io/requarks/wiki:2`) |
| Database | PostgreSQL 15 Alpine (internal, not exposed) |
| LAN access | `http://192.168.178.194:3000` — LAN only, no reverse proxy initially |
| Local dev | `http://localhost:3000` via `docker compose up` in `Z:\CC\SublarrWiki\` |
| Git sync | `Abrechen2/sublarr-wiki` GitHub repo (separate from main Sublarr repo) |

> **Note:** CT 115 IP to be confirmed at LXC creation time. `192.168.178.194` is a placeholder — verify next free DHCP/static slot on pve-node1 before deploy.

**Local folder:** `Z:\CC\SublarrWiki\` contains Docker Compose config, `.env`, and seed content stubs.

---

## Docker Compose

```yaml
# docker-compose.yml
services:
  wiki:
    image: ghcr.io/requarks/wiki:2
    container_name: sublarr-wiki
    depends_on:
      db:
        condition: service_healthy
    environment:
      DB_TYPE: postgres
      DB_HOST: db
      DB_PORT: 5432
      DB_USER: ${DB_USER}
      DB_PASS: ${DB_PASS}
      DB_NAME: ${DB_NAME}
    ports:
      - "3000:3000"
    restart: unless-stopped

  db:
    image: postgres:15-alpine
    container_name: sublarr-wiki-db
    environment:
      POSTGRES_USER: ${DB_USER}
      POSTGRES_PASSWORD: ${DB_PASS}
      POSTGRES_DB: ${DB_NAME}
    volumes:
      - db-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${DB_USER} -d ${DB_NAME}"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

volumes:
  db-data:
```

---

## Environment Variables

**`.env` file** (never committed):

```env
DB_USER=wiki
DB_PASS=replace-with-strong-password
DB_NAME=wiki
```

**`.env.example`** (committed):

```env
DB_USER=wiki
DB_PASS=   # set a strong password
DB_NAME=wiki
```

> **Git sync credentials are configured in the Wiki.js Admin Panel (Storage → Git), not via env vars.**
> They are not injected into the container. Keep these values handy for the Admin UI setup step:
> - Repository URL: `https://github.com/Abrechen2/sublarr-wiki.git`
> - Username: `Abrechen2`
> - Token: GitHub PAT with `repo` scope (create at github.com → Settings → Developer settings → PATs)
> - Author name: `Sublarr Wiki`
> - Author email: `wiki@sublarr.app`

---

## Git Sync Configuration

Wiki.js v2 Git sync is configured via the **Admin Panel → Storage → Git** after first startup. Settings:

| Field | Value |
|-------|-------|
| Authentication type | Basic (username + token) |
| Repository URL | `https://github.com/Abrechen2/sublarr-wiki.git` |
| Branch | `main` |
| Username | `Abrechen2` |
| Password/Token | GitHub PAT — needs `repo` scope (enter directly in Admin UI, not via env) |
| Author name | `Sublarr Wiki` |
| Author email | `wiki@sublarr.app` |
| Sync direction | Bi-directional |
| Sync interval | 5 minutes |

The GitHub repo `Abrechen2/sublarr-wiki` must be created before configuring sync (empty repo, no README). Wiki.js will push all pages on first sync.

---

## Navigation Structure

### Getting Started
- Home (hub page, mirrors Sonarr's overview)
- Installation
- Quick Start Guide
- Environment Variables
- Upgrade Guide ← from `docs/MIGRATION.md`
- FAQ

### User Guide
- Library
- Wanted
- Activity
- Settings
  - Media Management
  - Profiles
  - Providers ← includes Scoring section appended from `docs/SCORING.md`
  - Translation
  - Integrations
  - General
- Language Profiles
- Translation & LLM
- Integrations (*arr, Jellyfin, Emby)

### Troubleshooting
- General Troubleshooting
- Reverse Proxy Guide
- Performance Tuning

### Development
- Architecture
- Plugin Development
- API Reference
- Database Schema
- PostgreSQL Setup
- Contributing

### Links (sidebar footer)
- sublarr.app (landing page)
- Donate (PayPal)
- GitHub
- HuggingFace

---

## Content Migration Mapping

| Source file | Wiki page | Notes |
|-------------|-----------|-------|
| `docs/FAQ.md` | Getting Started / FAQ | Direct copy |
| `docs/USER-GUIDE.md` | User Guide / Library + Wanted + Activity | Split at H2 headings: `## Features` → Library (sections: Wanted System, Subtitle Scoring, Forced Subtitles, Backup and Restore, Tasks Page, Credit Filtering, OP/ED Detection, Stream Removal, Sidecar Auto-Cleanup, Subtitle Trash, Event Hooks); `## Quick Start` + `## Setup Scenarios` + `## Configuration` → Quick Start / Installation; `## Troubleshooting` → Troubleshooting/General supplement |
| `docs/CONFIGURATION.md` | Settings / General + Env Variables | Split: env vars → Getting Started, app config → Settings/General |
| `docs/PROVIDERS.md` | Settings / Providers | Direct copy |
| `docs/SCORING.md` | Settings / Providers | Append as "Subtitle Scoring" section at bottom of Providers page |
| `docs/INTEGRATIONS.md` | User Guide / Integrations | Direct copy |
| `docs/LANGUAGE-PROFILES.md` | User Guide / Language Profiles | Direct copy |
| `docs/TROUBLESHOOTING.md` | Troubleshooting / General | Direct copy |
| `docs/REVERSE-PROXY.md` | Troubleshooting / Reverse Proxy Guide | Direct copy |
| `docs/PERFORMANCE-TUNING.md` | Troubleshooting / Performance Tuning | Direct copy |
| `docs/ARCHITECTURE.md` | Development / Architecture | Direct copy |
| `docs/PLUGIN_DEVELOPMENT.md` | Development / Plugin Development | Direct copy |
| `docs/API.md` | Development / API Reference | Direct copy |
| `docs/DATABASE-SCHEMA.md` | Development / Database Schema | Direct copy |
| `docs/POSTGRESQL.md` | Development / PostgreSQL Setup | Direct copy |
| `docs/CONTRIBUTING.md` | Development / Contributing | Direct copy |
| `docs/MIGRATION.md` | Getting Started / Upgrade Guide | Standalone page — upgrade paths between versions |

---

## Theming

Wiki.js v2 supports custom CSS injection and theme overrides via Admin Panel → Theme:

- **Primary color:** `#1DB8D4` (Sublarr teal) — set in Theme color picker
- **Dark mode:** default
- **Font:** Inter — inject via Admin → Theme → Custom CSS:
  ```css
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
  .v-application { font-family: 'Inter', sans-serif !important; }
  ```
- **Logo:** Upload `logo.png` in Admin → General → Logo

---

## Folder Structure (`Z:\CC\SublarrWiki\`)

```
SublarrWiki/
├── docker-compose.yml
├── .env                     # not committed
├── .env.example             # committed
├── .gitignore
├── README.md
└── content/                 # seed markdown files
    └── en/
        ├── home.md
        ├── getting-started/
        │   ├── installation.md
        │   ├── quick-start.md
        │   ├── environment-variables.md
        │   ├── upgrade-guide.md
        │   └── faq.md
        ├── user-guide/
        │   ├── library.md
        │   ├── wanted.md
        │   ├── activity.md
        │   ├── settings/
        │   │   ├── media-management.md
        │   │   ├── profiles.md
        │   │   ├── providers.md    ← PROVIDERS.md + SCORING.md appended
        │   │   ├── translation.md
        │   │   ├── integrations.md
        │   │   └── general.md
        │   ├── language-profiles.md
        │   ├── translation-llm.md
        │   └── integrations.md
        ├── troubleshooting/
        │   ├── general.md
        │   ├── reverse-proxy.md
        │   └── performance-tuning.md
        └── development/
            ├── architecture.md
            ├── plugin-development.md
            ├── api-reference.md
            ├── database-schema.md
            ├── postgresql.md
            └── contributing.md
```

---

## README.md Required Sections

```
# Sublarr Wiki

## Local Development
docker compose up -d
# Open http://localhost:3000 — complete setup wizard on first run

## Environment Setup
cp .env.example .env
# Fill in DB_PASS in .env

## Git Sync Setup (Admin Panel)
# After first login: Admin → Storage → Add Storage → Git
# Repo: https://github.com/Abrechen2/sublarr-wiki.git
# Branch: main, Auth: Basic, Username: Abrechen2, Password: <PAT>
# Sync direction: Bi-directional, Interval: 5 min

## Deploy to LXC (CT 115 on pve-node1)
ssh root@192.168.178.171 "pct exec 115 -- bash -c 'cd /opt/wiki && docker compose pull && docker compose up -d'"
# Verify:
ssh root@192.168.178.171 "pct exec 115 -- curl -s http://localhost:3000/healthz"

## Content
Seed markdown files are in content/en/ — mirror of Abrechen2/sublarr-wiki repo structure.
```

---

## Success Criteria

1. `docker compose up -d` starts Wiki.js + PostgreSQL; `docker compose ps` shows both containers healthy
2. `http://localhost:3000` loads the Wiki.js setup wizard on first run and the wiki homepage after setup
3. All 22 `content/en/` seed files exist and contain migrated content from `docs/`
4. `.env.example` contains `DB_USER`, `DB_PASS`, `DB_NAME` with inline comments; no secrets present
5. `README.md` contains all four sections defined above (Local Dev, Env Setup, Git Sync Setup, Deploy to LXC)
6. `Abrechen2/sublarr-wiki` GitHub repo created and Wiki.js Git sync pushes pages to it on edit
