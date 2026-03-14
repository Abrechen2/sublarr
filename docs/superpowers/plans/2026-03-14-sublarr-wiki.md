# Sublarr Wiki Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create `Z:\CC\SublarrWiki\` with a working Wiki.js v2 + PostgreSQL Docker Compose setup and full content seed files migrated from the existing `docs/` folder, plus a local runner for the SublarrWeb landing page.

**Architecture:** Wiki.js v2 runs in Docker Compose with PostgreSQL (healthcheck-gated startup). Content is seeded as Markdown files in `content/en/` mirroring the Sonarr wiki structure. A separate `docker-compose.yml` in `Z:\CC\SublarrWeb\` serves the landing page via nginx. Git sync to `Abrechen2/sublarr-wiki` is configured post-startup via the Admin UI.

**Tech Stack:** Docker Compose, Wiki.js 2.x (`ghcr.io/requarks/wiki:2`), PostgreSQL 15 Alpine, nginx Alpine (SublarrWeb), Markdown

---

## File Map

### `Z:\CC\SublarrWiki\` (create all)
| File | Responsibility |
|------|---------------|
| `docker-compose.yml` | Wiki.js + PostgreSQL service definitions with healthcheck |
| `.env.example` | Required variables template (committed) |
| `.gitignore` | Exclude `.env`, DB volumes |
| `README.md` | Setup guide with 4 required sections from spec |
| `content/en/home.md` | Hub page — overview of all wiki sections |
| `content/en/getting-started/installation.md` | Docker install instructions |
| `content/en/getting-started/quick-start.md` | First-run walkthrough |
| `content/en/getting-started/environment-variables.md` | All `SUBLARR_*` env vars |
| `content/en/getting-started/upgrade-guide.md` | Migration / upgrade paths |
| `content/en/getting-started/faq.md` | FAQ |
| `content/en/user-guide/library.md` | Library UI guide |
| `content/en/user-guide/wanted.md` | Wanted scanner guide |
| `content/en/user-guide/activity.md` | Activity / translations guide |
| `content/en/user-guide/settings/media-management.md` | Settings → Media Management |
| `content/en/user-guide/settings/profiles.md` | Settings → Profiles |
| `content/en/user-guide/settings/providers.md` | Providers + Scoring (merged) |
| `content/en/user-guide/settings/translation.md` | Settings → Translation |
| `content/en/user-guide/settings/integrations.md` | Settings → Integrations |
| `content/en/user-guide/settings/general.md` | Settings → General |
| `content/en/user-guide/language-profiles.md` | Language Profiles |
| `content/en/user-guide/translation-llm.md` | Translation & LLM backends |
| `content/en/user-guide/integrations.md` | *arr / Jellyfin / Emby integration |
| `content/en/troubleshooting/general.md` | Troubleshooting |
| `content/en/troubleshooting/reverse-proxy.md` | Reverse proxy guide |
| `content/en/troubleshooting/performance-tuning.md` | Performance tuning |
| `content/en/development/architecture.md` | Architecture overview |
| `content/en/development/plugin-development.md` | Plugin dev guide |
| `content/en/development/api-reference.md` | API reference |
| `content/en/development/database-schema.md` | DB schema |
| `content/en/development/postgresql.md` | PostgreSQL setup |
| `content/en/development/contributing.md` | Contributing guide |

### `Z:\CC\SublarrWeb\` (add file)
| File | Responsibility |
|------|---------------|
| `docker-compose.yml` | nginx serving static landing page on port 8899 |

---

## Chunk 1: Project Scaffold

**Files:**
- Create: `Z:\CC\SublarrWiki\docker-compose.yml`
- Create: `Z:\CC\SublarrWiki\.env.example`
- Create: `Z:\CC\SublarrWiki\.gitignore`
- Create: `Z:\CC\SublarrWiki\README.md`

### Task 1: Create docker-compose.yml

- [ ] **Step 1: Create `Z:\CC\SublarrWiki\docker-compose.yml`**

```yaml
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

- [ ] **Step 2: Create `Z:\CC\SublarrWiki\.env.example`**

```env
# Database credentials — copy to .env and fill in DB_PASS
DB_USER=wiki
DB_PASS=   # set a strong password here
DB_NAME=wiki
```

- [ ] **Step 3: Create `Z:\CC\SublarrWiki\.env` from example**

```bash
cp Z:/CC/SublarrWiki/.env.example Z:/CC/SublarrWiki/.env
# Then edit .env: set DB_PASS to a strong password (e.g. "wiki-local-dev")
```

Verify `.env` was created:
```bash
cat Z:/CC/SublarrWiki/.env
```
Expected: file contents visible with `DB_PASS=` line (fill it in before continuing).

- [ ] **Step 4: Create `Z:\CC\SublarrWiki\.gitignore`**

```
.env
```

- [ ] **Step 5: Verify Docker Compose syntax**

```bash
cd Z:/CC/SublarrWiki && docker compose config
```

Expected: Resolved config printed with no errors. `wiki` service shows `condition: service_healthy` under `depends_on`.

- [ ] **Step 6: Start containers**

```bash
cd Z:/CC/SublarrWiki && docker compose up -d
```

Expected: `db` starts first, passes healthcheck, then `wiki` starts. Takes ~30s.

- [ ] **Step 7: Verify both containers are running**

```bash
docker compose ps
```

Expected:
```
NAME                STATUS
sublarr-wiki        running
sublarr-wiki-db     running (healthy)
```

- [ ] **Step 8: Verify Wiki.js is accessible**

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000
```

Expected: `200` or `302` (redirect to setup wizard on first run).

- [ ] **Step 9: Commit**

```bash
cd Z:/CC/SublarrWiki
git init
git add docker-compose.yml .env.example .gitignore
git commit -m "chore: initial Wiki.js + PostgreSQL Docker Compose setup"
```

---

### Task 2: Create README.md

- [ ] **Step 1: Create `Z:\CC\SublarrWiki\README.md`**

````markdown
# Sublarr Wiki

Self-hosted documentation wiki for [Sublarr](https://github.com/Abrechen2/sublarr) — powered by Wiki.js v2.

## Local Development

```bash
cp .env.example .env
# Edit .env — set DB_PASS
docker compose up -d
```

Open http://localhost:3000 and complete the setup wizard on first run.
Admin credentials are set during the wizard — use `admin@sublarr.app` as email.

## Environment Setup

| Variable | Description | Default |
|----------|-------------|---------|
| `DB_USER` | PostgreSQL username | `wiki` |
| `DB_PASS` | PostgreSQL password | — must set — |
| `DB_NAME` | PostgreSQL database name | `wiki` |

## Git Sync Setup (Admin Panel)

After completing the setup wizard:

1. Go to **Admin → Storage → Add Storage → Git**
2. Fill in:
   - **Repository URL:** `https://github.com/Abrechen2/sublarr-wiki.git`
   - **Branch:** `main`
   - **Authentication:** Basic
   - **Username:** `Abrechen2`
   - **Password/Token:** GitHub PAT with `repo` scope
   - **Author Name:** `Sublarr Wiki`
   - **Author Email:** `wiki@sublarr.app`
   - **Sync Direction:** Bi-directional
   - **Sync Interval:** 5 minutes
3. Click **Apply** — Wiki.js will push all pages to GitHub on first sync.

> Create the `Abrechen2/sublarr-wiki` GitHub repo (empty, no README) before enabling sync.

## Deploy to LXC (CT 115 on pve-node1)

```bash
# Copy files to LXC
scp -r . root@192.168.178.171:/tmp/wiki-deploy
ssh root@192.168.178.171 "pct exec 115 -- bash -c 'mkdir -p /opt/wiki && cp -r /tmp/wiki-deploy/* /opt/wiki/'"

# Start
ssh root@192.168.178.171 "pct exec 115 -- bash -c 'cd /opt/wiki && docker compose up -d'"

# Verify
ssh root@192.168.178.171 "pct exec 115 -- curl -s -o /dev/null -w '%{http_code}' http://localhost:3000"
# Expected: 200 or 302
```

## Content

Seed markdown files live in `content/en/` — these mirror the `Abrechen2/sublarr-wiki` GitHub repo structure. After Git sync is configured, Wiki.js will manage this content.

## Structure

```
content/en/
├── home.md
├── getting-started/    installation, quick-start, env vars, upgrade guide, FAQ
├── user-guide/         library, wanted, activity, settings/*, language profiles, translation, integrations
├── troubleshooting/    general, reverse proxy, performance
└── development/        architecture, plugins, API, DB schema, PostgreSQL, contributing
```
````

- [ ] **Step 2: Commit**

```bash
cd Z:/CC/SublarrWiki
git add README.md
git commit -m "docs: add README with setup, git sync, and LXC deploy instructions"
```

---

## Chunk 2: Getting Started Content

**Files:** `content/en/home.md`, `content/en/getting-started/*.md`
**Source docs:** `Z:\CC\Sublarr\docs\FAQ.md`, `docs\CONFIGURATION.md`, `docs\MIGRATION.md`, `docs\USER-GUIDE.md` (Quick Start + Setup Scenarios sections)

### Task 3: home.md (hub page)

- [ ] **Step 1: Create `Z:\CC\SublarrWiki\content\en\home.md`**

```markdown
---
title: Sublarr Wiki
description: Documentation for Sublarr — self-hosted subtitle manager for anime & media
published: true
date: 2026-03-14
---

# Sublarr

Self-hosted subtitle manager for anime & media libraries. Finds the best subtitles, translates them locally with a custom LLM model, and keeps everything in sync with your *arr stack.

> **Latest:** v0.28.0-beta — AI Glossary Builder  <!-- Update at each release — source of truth: `backend/VERSION` -->

---

## Getting Started

| | |
|---|---|
| [Installation](/getting-started/installation) | Docker, Docker Compose, environment variables |
| [Quick Start Guide](/getting-started/quick-start) | Connect your *arr apps and find your first subtitles |
| [Environment Variables](/getting-started/environment-variables) | All `SUBLARR_*` configuration options |
| [Upgrade Guide](/getting-started/upgrade-guide) | Upgrading between versions, migration notes |
| [FAQ](/getting-started/faq) | Frequently asked questions |

## User Guide

| | |
|---|---|
| [Library](/user-guide/library) | Browsing and managing your media library |
| [Wanted](/user-guide/wanted) | Automatic missing subtitle detection and search |
| [Activity](/user-guide/activity) | Translation jobs, download history |
| [Settings](/user-guide/settings/general) | Full settings reference |
| [Language Profiles](/user-guide/language-profiles) | Per-series language targeting |
| [Translation & LLM](/user-guide/translation-llm) | Ollama, custom anime model, translation pipeline |
| [Integrations](/user-guide/integrations) | Sonarr, Radarr, Jellyfin, Emby |

## Troubleshooting

| | |
|---|---|
| [General Troubleshooting](/troubleshooting/general) | Common issues and solutions |
| [Reverse Proxy Guide](/troubleshooting/reverse-proxy) | nginx, Caddy, NPM setup |
| [Performance Tuning](/troubleshooting/performance-tuning) | Large libraries, translation throughput |

## Development

| | |
|---|---|
| [Architecture](/development/architecture) | System design, component overview |
| [Plugin Development](/development/plugin-development) | Writing custom provider/hook plugins |
| [API Reference](/development/api-reference) | REST API endpoints |
| [Database Schema](/development/database-schema) | SQLite tables and relationships |
| [PostgreSQL Setup](/development/postgresql) | Switching to PostgreSQL |
| [Contributing](/development/contributing) | Development workflow, PR guidelines |

---

## Links

- [sublarr.app](https://sublarr.app) — Landing page
- [GitHub](https://github.com/Abrechen2/sublarr) — Source code & releases
- [HuggingFace](https://huggingface.co/Sublarr) — Custom anime translation model
- [Donate](https://www.paypal.com/donate?hosted_button_id=GLXYTD3FV9Y78) — Support development
```

### Task 4: Installation page

- [ ] **Step 1: Verify source section headings exist in `docs/USER-GUIDE.md`**

```bash
grep -n "^##" Z:/CC/Sublarr/docs/USER-GUIDE.md
```

Expected: output includes `## Quick Start` (line ~5) and `## Setup Scenarios` (line ~74) and `## Configuration` (line ~181). Note the exact line numbers — the Installation page content runs from `## Quick Start` through the end of `## Setup Scenarios` (i.e. up to but not including `## Configuration`).

- [ ] **Step 2: Create `Z:\CC\SublarrWiki\content\en\getting-started\installation.md`**

File content: frontmatter header + lines from `## Quick Start` through end of `## Setup Scenarios` copied from `docs/USER-GUIDE.md`:

```markdown
---
title: Installation
description: How to install Sublarr with Docker or Docker Compose
published: true
date: 2026-03-14
---

# Installation
```

After the frontmatter, paste all lines from `## Quick Start` (line ~5) through the last line of `## Setup Scenarios` (line ~180) from `Z:\CC\Sublarr\docs\USER-GUIDE.md`. These sections cover: Prerequisites, Docker Compose (recommended), Unraid, Environment Variables, Scenario 1 (Sonarr + Radarr), Scenario 2 (Standalone), Scenario 3 (Mixed Mode).

- [ ] **Step 3: Verify the file was created with content**

```bash
wc -l Z:/CC/SublarrWiki/content/en/getting-started/installation.md
```

Expected: 170+ lines (the source section spans ~175 lines).

### Task 5: Quick Start Guide

- [ ] **Step 1: Create `Z:\CC\SublarrWiki\content\en\getting-started\quick-start.md`**

```markdown
---
title: Quick Start Guide
description: Connect Sublarr to your *arr stack and find your first subtitles
published: true
date: 2026-03-14
---

# Quick Start Guide

## 1. Open Sublarr

After running `docker compose up -d`, open [http://localhost:5765](http://localhost:5765) in your browser.

## 2. Configure a Provider

Go to **Settings → Providers** and enable at least one subtitle provider:

- **AnimeTosho** — best for anime (no API key required)
- **OpenSubtitles** — large library, requires free account
- **Jimaku** — Japanese anime focus

Click **Test** to verify the provider is reachable.

## 3. Set Up Language Profile

Go to **Settings → Profiles → Language Profiles** and create a profile:
- **Source language:** English (en)
- **Target language:** German (de) or your preferred language
- **Minimum score:** 60 (recommended)

## 4. Connect a Media Server

Go to **Settings → Integrations** and add Jellyfin or Emby:
- Enter your server URL and API key
- Click **Test Connection**

Sublarr will scan your library and populate the Wanted list with missing subtitles.

## 5. Connect Sonarr / Radarr (optional)

Go to **Settings → Integrations → Sonarr** (or Radarr):
- Enter URL: `http://sonarr:8989`
- Enter API key (found in Sonarr → Settings → General)
- Enable webhooks: in Sonarr, add a webhook pointing to `http://sublarr:5765/api/v1/webhook/sonarr`

New downloads will now trigger automatic subtitle search.

## 6. Search for Subtitles

Go to **Wanted** — click **Search All** to start finding subtitles for everything in your library.

> **Tip:** The first scan can take a while for large libraries. Watch progress in **Activity → Tasks**.
```

### Task 6: Environment Variables page

- [ ] **Step 1: Create `Z:\CC\SublarrWiki\content\en\getting-started\environment-variables.md`**

Content: Copy all content from `Z:\CC\Sublarr\docs\CONFIGURATION.md`. Add Wiki.js frontmatter:

```markdown
---
title: Environment Variables
description: All SUBLARR_* environment variables and configuration options
published: true
date: 2026-03-14
---
```

Then paste full contents of `docs/CONFIGURATION.md`.

### Task 7: Upgrade Guide page

- [ ] **Step 1: Create `Z:\CC\SublarrWiki\content\en\getting-started\upgrade-guide.md`**

Content: Copy all content from `Z:\CC\Sublarr\docs\MIGRATION.md`. Add frontmatter:

```markdown
---
title: Upgrade Guide
description: Upgrading Sublarr between versions — migration notes and breaking changes
published: true
date: 2026-03-14
---
```

Then paste full contents of `docs/MIGRATION.md`.

### Task 8: FAQ page

- [ ] **Step 1: Create `Z:\CC\SublarrWiki\content\en\getting-started\faq.md`**

Content: Copy all content from `Z:\CC\Sublarr\docs\FAQ.md`. Add frontmatter:

```markdown
---
title: FAQ
description: Frequently asked questions about Sublarr
published: true
date: 2026-03-14
---
```

Then paste full contents of `docs/FAQ.md`.

- [ ] **Step 2: Commit all Getting Started content**

```bash
cd Z:/CC/SublarrWiki
git add content/
git commit -m "docs: add Getting Started wiki pages (home, installation, quick-start, env vars, upgrade guide, FAQ)"
```

---

## Chunk 3: User Guide Content

**Files:** `content/en/user-guide/*.md`, `content/en/user-guide/settings/*.md`
**Source docs:** `docs/USER-GUIDE.md`, `docs/PROVIDERS.md`, `docs/SCORING.md`, `docs/LANGUAGE-PROFILES.md`, `docs/INTEGRATIONS.md`

### Task 9: Library, Wanted, Activity pages

- [ ] **Step 1: Create `Z:\CC\SublarrWiki\content\en\user-guide\library.md`**

```markdown
---
title: Library
description: Browsing and managing your media library in Sublarr
published: true
date: 2026-03-14
---

# Library

The Library view shows all series and movies that Sublarr is aware of, sourced from your connected Jellyfin, Emby, or *arr integrations.

## Series List

Each row shows:
- **Title** — series name with year
- **Subtitle status** — how many episodes have subtitles vs. total
- **Language** — active language profile
- **Provider last used** — which provider found the last subtitle

Click a series to open the **Series Detail** view showing per-episode subtitle status.

## Series Detail

- Lists all seasons and episodes
- Shows subtitle file path, score, provider, and language for each episode
- **Search** button triggers a manual provider search for that episode
- **Translate** button sends the subtitle through the LLM translation pipeline
- **Delete** removes the subtitle file (moves to Trash)

## Filters

Use the filter bar to narrow by:
- Subtitle status: `all`, `subtitled`, `missing`, `wanted`
- Language profile
- Provider

## Bulk Actions

Select multiple series with the checkbox column, then:
- **Batch Search** — searches all selected series for missing subtitles
- **Batch Translate** — queues all selected for translation
```

- [ ] **Step 2: Verify source headings before creating wanted.md**

```bash
grep -n "### Wanted System\|### Tasks Page" Z:/CC/Sublarr/docs/USER-GUIDE.md
```

Expected: `### Wanted System` at line ~263, `### Tasks Page` at line ~329.

- [ ] **Step 3: Create `Z:\CC\SublarrWiki\content\en\user-guide\wanted.md`**

Frontmatter + intro paragraph + paste `### Wanted System` section from `docs/USER-GUIDE.md` (line ~263 through ~278):

```markdown
---
title: Wanted
description: Automatic missing subtitle detection and search
published: true
date: 2026-03-14
---

# Wanted

The Wanted list tracks all episodes and movies in your library that are missing subtitles matching your Language Profile. Sublarr automatically populates this list from your connected Jellyfin/Emby library.
```

Then paste the `### Wanted System` section from `docs/USER-GUIDE.md` (lines ~263–278).

Verify:
```bash
wc -l Z:/CC/SublarrWiki/content/en/user-guide/wanted.md
```
Expected: 25+ lines.

- [ ] **Step 4: Create `Z:\CC\SublarrWiki\content\en\user-guide\activity.md`**

```markdown
---
title: Activity
description: Translation jobs, download history, and background task monitoring
published: true
date: 2026-03-14
---

# Activity

The Activity section shows all background operations: subtitle downloads, translation jobs, webhook events, and scheduled scanner runs.

## Translation Jobs

Lists all active and completed translation jobs with:
- Source and target language
- Progress (lines translated / total)
- Model used (e.g. `anime-translator-v6`)
- Status: `queued`, `running`, `done`, `failed`

## Tasks
```

After the frontmatter block above, paste the `### Tasks Page` section from `docs/USER-GUIDE.md` (lines ~329–343).

Verify:
```bash
wc -l Z:/CC/SublarrWiki/content/en/user-guide/activity.md
```
Expected: 30+ lines.

### Task 10: Settings sub-pages

- [ ] **Step 1: Create `Z:\CC\SublarrWiki\content\en\user-guide\settings\media-management.md`**

```markdown
---
title: Settings — Media Management
description: File naming, importing, and media path configuration
published: true
date: 2026-03-14
---

# Settings — Media Management

## Subtitle File Naming

Sublarr writes subtitle files alongside your media using this naming pattern:

```
{MediaFileName}.{language}.{format}
```

Examples:
- `Show.S01E01.mkv` → `Show.S01E01.de.ass`
- `Movie.2023.mkv` → `Movie.2023.en.srt`

The language code uses ISO 639-1 (2-letter: `en`, `de`, `ja`) or ISO 639-2 (3-letter: `eng`, `deu`).

## Root Folders

Root folders define where Sublarr looks for media files. These must match your Jellyfin/Emby library paths and your Docker volume mounts.

Add root folders under **Settings → Media Management → Root Folders**.

## Import Behaviour

- Sublarr **never deletes or modifies media files** — it only creates `.ass` and `.srt` sidecar files
- Existing subtitles with a higher score than the found subtitle are not overwritten (upgrade threshold configurable)
- Files are written with the same permissions as the media file's directory
```

- [ ] **Step 2: Create `Z:\CC\SublarrWiki\content\en\user-guide\settings\profiles.md`**

```markdown
---
title: Settings — Profiles
description: Quality profiles, language profiles, and scoring configuration
published: true
date: 2026-03-14
---

# Settings — Profiles

## Language Profiles

Language Profiles define the subtitle search strategy per series. See the dedicated [Language Profiles](/user-guide/language-profiles) page for full documentation.

## Quality / Score Thresholds

Each profile sets a minimum score (0–100) a subtitle must reach before it is downloaded.

| Score range | Meaning |
|-------------|---------|
| 80–100 | High confidence match — exact episode hash or release name match |
| 60–79 | Good match — title + season/episode match |
| 40–59 | Weak match — title only |
| < 40 | Rejected — too uncertain |

See [Settings → Providers → Scoring](/user-guide/settings/providers#scoring) for how scores are calculated.

## Delay Profiles

Delay profiles add a wait time before searching, allowing better subtitle releases to appear. Useful for newly aired episodes where only machine-translated subtitles are available initially.

Configure per language profile: **Delay (hours)** — default `0`.
```

- [ ] **Step 3: Create `Z:\CC\SublarrWiki\content\en\user-guide\settings\providers.md`**

Content: Copy full contents of `Z:\CC\Sublarr\docs\PROVIDERS.md`, then append the full contents of `Z:\CC\Sublarr\docs\SCORING.md` as a new `## Subtitle Scoring` section. Add frontmatter:

```markdown
---
title: Settings — Providers
description: Subtitle provider configuration, supported providers, and scoring algorithm
published: true
date: 2026-03-14
---
```

Then paste `docs/PROVIDERS.md` contents, then append:

```markdown

---

## Subtitle Scoring
```

Then paste `docs/SCORING.md` contents.

- [ ] **Step 4: Create `Z:\CC\SublarrWiki\content\en\user-guide\settings\translation.md`**

First verify section exists:
```bash
grep -n "### Translation Backends" Z:/CC/Sublarr/docs/USER-GUIDE.md
```
Expected: line ~203.

```markdown
---
title: Settings — Translation
description: LLM translation backend configuration — Ollama, custom model
published: true
date: 2026-03-14
---

# Settings — Translation
```

Then paste the `### Translation Backends` section from `docs/USER-GUIDE.md` (lines ~203–227).

Verify:
```bash
wc -l Z:/CC/SublarrWiki/content/en/user-guide/settings/translation.md
```
Expected: 30+ lines.

- [ ] **Step 5: Verify source sections before creating settings/integrations.md**

```bash
grep -n "### Webhooks\|## Sonarr\|## Media Server\|## Integrations" Z:/CC/Sublarr/docs/USER-GUIDE.md Z:/CC/Sublarr/docs/CONFIGURATION.md
```

Expected: `### Webhooks (Sonarr/Radarr)` in USER-GUIDE.md ~line 247, and integration-related sections in CONFIGURATION.md.

- [ ] **Step 6: Create `Z:\CC\SublarrWiki\content\en\user-guide\settings\integrations.md`**

```markdown
---
title: Settings — Integrations
description: Sonarr, Radarr, Jellyfin, and Emby integration settings
published: true
date: 2026-03-14
---

# Settings — Integrations
```

After the frontmatter, paste in order:
1. `### Webhooks (Sonarr/Radarr)` section from `docs/USER-GUIDE.md` (lines ~247–260)
2. Any `## Sonarr & Radarr` and `## Media Servers` sections from `docs/CONFIGURATION.md`

Verify:
```bash
wc -l Z:/CC/SublarrWiki/content/en/user-guide/settings/integrations.md
```
Expected: 40+ lines.

- [ ] **Step 7: Create `Z:\CC\SublarrWiki\content\en\user-guide\settings\general.md`**

`docs/CONFIGURATION.md` consists entirely of `SUBLARR_*` environment variable documentation. There is no separate "general app settings" section to extract. This page is written directly:

```markdown
---
title: Settings — General
description: General application settings — host, security, authentication, UI, backups
published: true
date: 2026-03-14
---

# Settings — General

This page covers the UI-configurable settings in **Settings → General**. For environment variable configuration, see [Environment Variables](/getting-started/environment-variables).

## Host & Port

| Setting | Default | Description |
|---------|---------|-------------|
| Host | `0.0.0.0` | Bind address — keep default unless on a multi-NIC server |
| Port | `5765` | HTTP port — change if port is already in use |
| URL Base | _(empty)_ | Set if running behind a reverse proxy at a subpath (e.g. `/sublarr`) |

## Authentication

| Setting | Default | Description |
|---------|---------|-------------|
| Authentication enabled | `false` | Enable single-account login |
| Username | `admin` | Login username |
| Password | _(set on first run)_ | Login password |

See [Login Setup](/getting-started/quick-start#authentication) for the full setup flow.

## Updates

Sublarr checks GitHub releases for newer versions. Notification appears in the sidebar when an update is available. Auto-update is not supported — pull the new Docker image manually.

## Backups

Sublarr automatically backs up its SQLite database to `/config/backups/` on a configurable schedule. Default: daily, keep 7 backups. Restore by replacing `/config/sublarr.db` and restarting the container.

## Analytics

Sublarr does not collect analytics or telemetry. No data leaves your server.
```

Verify:
```bash
wc -l Z:/CC/SublarrWiki/content/en/user-guide/settings/general.md
```
Expected: 50+ lines.

### Task 11: Language Profiles, Translation-LLM, Integrations pages

- [ ] **Step 1: Create `Z:\CC\SublarrWiki\content\en\user-guide\language-profiles.md`**

Content: Full copy of `Z:\CC\Sublarr\docs\LANGUAGE-PROFILES.md`. Add frontmatter:

```markdown
---
title: Language Profiles
description: Per-series language targeting — source language, target language, scoring thresholds
published: true
date: 2026-03-14
---
```

- [ ] **Step 2: Create `Z:\CC\SublarrWiki\content\en\user-guide\translation-llm.md`**

Content: frontmatter + inline model card (below) + `### Translation Backends` section from `docs/USER-GUIDE.md`. Add frontmatter:

````markdown
---
title: Translation & LLM
description: Local LLM translation with Ollama — custom anime model, translation pipeline
published: true
date: 2026-03-14
---

# Translation & LLM

Sublarr supports fully offline subtitle translation using [Ollama](https://ollama.com). No cloud APIs, no accounts required.

## Custom Anime Model

Sublarr ships a fine-tuned anime translation model trained on 75,000 subtitle pairs:

```bash
ollama pull hf.co/Sublarr/anime-translator-v6-GGUF:Q4_K_M
```

| Property | Value |
|----------|-------|
| Direction | English → German |
| Training data | OPUS OpenSubtitles v2018, 75k anime subtitle pairs |
| BLEU-1 | 0.281 |
| Size | 7 GB (Q4_K_M GGUF) |
| Config key | `SUBLARR_OLLAMA_MODEL` |

## Configuring Ollama

Set in `.env` or Settings → Translation:

```env
SUBLARR_OLLAMA_URL=http://ollama:11434
SUBLARR_OLLAMA_MODEL=hf.co/Sublarr/anime-translator-v6-GGUF:Q4_K_M
```
````

After the frontmatter block, also paste the `### Translation Backends` section from `docs/USER-GUIDE.md` (lines ~203–227).

Verify:
```bash
wc -l Z:/CC/SublarrWiki/content/en/user-guide/translation-llm.md
```
Expected: 60+ lines.

- [ ] **Step 3: Create `Z:\CC\SublarrWiki\content\en\user-guide\integrations.md`**

Content: Full copy of `Z:\CC\Sublarr\docs\INTEGRATIONS.md`. Add frontmatter:

```markdown
---
title: Integrations
description: Connecting Sublarr to Sonarr, Radarr, Jellyfin, and Emby
published: true
date: 2026-03-14
---
```

Verify:
```bash
wc -l Z:/CC/SublarrWiki/content/en/user-guide/integrations.md
```
Expected: matches `wc -l Z:/CC/Sublarr/docs/INTEGRATIONS.md` + 5 (frontmatter lines).

- [ ] **Step 4: Commit User Guide content**

```bash
cd Z:/CC/SublarrWiki
git add content/en/user-guide/
git commit -m "docs: add User Guide wiki pages (library, wanted, activity, settings, language profiles, translation, integrations)"
```

---

## Chunk 4: Troubleshooting + Development Content

**Files:** `content/en/troubleshooting/*.md`, `content/en/development/*.md`
**Source docs:** `docs/TROUBLESHOOTING.md`, `docs/REVERSE-PROXY.md`, `docs/PERFORMANCE-TUNING.md`, `docs/ARCHITECTURE.md`, `docs/PLUGIN_DEVELOPMENT.md`, `docs/API.md`, `docs/DATABASE-SCHEMA.md`, `docs/POSTGRESQL.md`, `docs/CONTRIBUTING.md`

### Task 12: Troubleshooting pages

For each file below: add Wiki.js frontmatter, then paste the full source doc contents.

- [ ] **Step 1: Create `content/en/troubleshooting/general.md`** — source: `docs/TROUBLESHOOTING.md`

```markdown
---
title: General Troubleshooting
description: Common Sublarr issues and how to fix them
published: true
date: 2026-03-14
---
```

Then paste full contents of `docs/TROUBLESHOOTING.md`.

- [ ] **Step 2: Create `content/en/troubleshooting/reverse-proxy.md`** — source: `docs/REVERSE-PROXY.md`

```markdown
---
title: Reverse Proxy Guide
description: Setting up Sublarr behind nginx, Caddy, or NPM
published: true
date: 2026-03-14
---
```

Then paste full contents of `docs/REVERSE-PROXY.md`.

- [ ] **Step 3: Create `content/en/troubleshooting/performance-tuning.md`** — source: `docs/PERFORMANCE-TUNING.md`

```markdown
---
title: Performance Tuning
description: Optimizing Sublarr for large libraries and high translation throughput
published: true
date: 2026-03-14
---
```

Then paste full contents of `docs/PERFORMANCE-TUNING.md`.

- [ ] **Step 4: Verify all three troubleshooting files have content**

```bash
wc -l Z:/CC/SublarrWiki/content/en/troubleshooting/*.md
```

Expected: each file has at least as many lines as its source doc + 5 (frontmatter).

- [ ] **Step 6: Commit troubleshooting content**

```bash
cd Z:/CC/SublarrWiki
git add content/en/troubleshooting/
git commit -m "docs: add Troubleshooting wiki pages"
```

### Task 13: Development pages

For each file below: add Wiki.js frontmatter, then paste the full source doc contents.

- [ ] **Step 1: Create `content/en/development/architecture.md`** — source: `docs/ARCHITECTURE.md`

```markdown
---
title: Architecture
description: Sublarr system design, component overview, data flow
published: true
date: 2026-03-14
---
```

Then paste full contents of `docs/ARCHITECTURE.md`.

- [ ] **Step 2: Create `content/en/development/plugin-development.md`** — source: `docs/PLUGIN_DEVELOPMENT.md`

```markdown
---
title: Plugin Development
description: Writing custom subtitle provider and hook plugins for Sublarr
published: true
date: 2026-03-14
---
```

Then paste full contents of `docs/PLUGIN_DEVELOPMENT.md`.

- [ ] **Step 3: Create `content/en/development/api-reference.md`** — source: `docs/API.md`

```markdown
---
title: API Reference
description: Sublarr REST API — all endpoints under /api/v1/
published: true
date: 2026-03-14
---
```

Then paste full contents of `docs/API.md`.

- [ ] **Step 4: Create `content/en/development/database-schema.md`** — source: `docs/DATABASE-SCHEMA.md`

```markdown
---
title: Database Schema
description: SQLite table definitions, relationships, and migration history
published: true
date: 2026-03-14
---
```

Then paste full contents of `docs/DATABASE-SCHEMA.md`.

- [ ] **Step 5: Create `content/en/development/postgresql.md`** — source: `docs/POSTGRESQL.md`

```markdown
---
title: PostgreSQL Setup
description: Switching Sublarr from SQLite to PostgreSQL
published: true
date: 2026-03-14
---
```

Then paste full contents of `docs/POSTGRESQL.md`.

- [ ] **Step 6: Create `content/en/development/contributing.md`** — source: `docs/CONTRIBUTING.md`

```markdown
---
title: Contributing
description: Development workflow, branching strategy, PR guidelines for Sublarr
published: true
date: 2026-03-14
---
```

Then paste full contents of `docs/CONTRIBUTING.md`.

- [ ] **Step 7: Verify all six development files have content**

```bash
wc -l Z:/CC/SublarrWiki/content/en/development/*.md
```

Expected: each file has at least as many lines as its source doc + 5.

- [ ] **Step 8: Commit development content**

```bash
cd Z:/CC/SublarrWiki
git add content/en/development/
git commit -m "docs: add Development wiki pages (architecture, plugins, API, DB, PostgreSQL, contributing)"
```

---

## Chunk 5: SublarrWeb Local Runner

**Files:**
- Create: `Z:\CC\SublarrWeb\docker-compose.yml`

### Task 14: nginx Docker Compose for SublarrWeb

- [ ] **Step 1: Create `Z:\CC\SublarrWeb\docker-compose.yml`**

```yaml
services:
  web:
    image: nginx:alpine
    container_name: sublarr-web
    ports:
      - "8899:80"
    volumes:
      - .:/usr/share/nginx/html:ro
    restart: unless-stopped
```

- [ ] **Step 2: Start the landing page**

```bash
cd Z:/CC/SublarrWeb && docker compose up -d
```

Expected: `sublarr-web` container starts.

- [ ] **Step 3: Verify**

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:8899
```

Expected: `200`

- [ ] **Step 4: Verify static assets are served**

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:8899/app.js
curl -s -o /dev/null -w "%{http_code}" http://localhost:8899/style.css
curl -s -o /dev/null -w "%{http_code}" http://localhost:8899/img/screen-dashboard.png
```

Expected: `200` for all three. Then open `http://localhost:8899` in browser and verify the hero screenshot loads and the 5 showcase tabs switch images correctly.

- [ ] **Step 5: Commit**

```bash
cd Z:/CC/SublarrWeb
git add docker-compose.yml
git commit -m "chore: add nginx Docker Compose for local SublarrWeb dev server"
```

---

## Post-Setup: Wiki.js First-Run Checklist

After `docker compose up -d` in SublarrWiki and opening `http://localhost:3000`:

- [ ] Complete setup wizard: set admin email (`admin@sublarr.app`) and password
- [ ] Admin → General → Site Title: `Sublarr Wiki`
- [ ] Admin → General → Upload logo (`Z:\CC\SublarrWeb\logo.png`)
- [ ] Admin → Theme → Primary color: `#1DB8D4`
- [ ] Admin → Theme → Dark mode: enabled
- [ ] Admin → Theme → Custom CSS: inject Inter font
- [ ] Admin → Navigation → Build sidebar from content structure
- [ ] Create GitHub repo `Abrechen2/sublarr-wiki` (empty, no README)
- [ ] Admin → Storage → Add Git sync (see README for settings)
- [ ] Import seed pages: Admin → Pages → Import from disk (point to `content/en/`)
