# Provider Ecosystem — Design Spec
**Version:** v0.22.0
**Date:** 2026-03-11
**Status:** Approved

---

## Overview

A full-lifecycle plugin system for community-built subtitle providers. Providers are
discoverable via GitHub, installable at runtime without restart, and verified via
SHA-256 integrity checks. Builtin providers are unchanged — community providers are
purely additive.

---

## Architecture

```
backend/
  providers/          # Builtin providers (unchanged, always active)
  plugins/
    providers/        # Community providers (.zip extracted here)
    manager.py        # PluginManager — load, reload, unload
    registry.py       # GitHub API discovery + DB cache (TTL 1h)
    sandbox.py        # SHA256 verification + capability parser
```

**Three new layers:**
1. **PluginManager** — dynamically imports community providers, registers them in the
   existing provider registry; supports hot-reload without restart
2. **Registry** — fetches GitHub repos with topic `sublarr-provider`; caches results
   in DB with 1h TTL; parses manifest per repo
3. **DB tables** — `installed_plugins` (what's installed) + `marketplace_cache` (GitHub results)

---

## Plugin Format

Each community provider ships as a `.zip`:

```
provider-name-v1.0.0.zip
├── manifest.json     # Required
├── provider.py       # Required — entry point, inherits BaseProvider
├── requirements.txt  # Optional — extra pip dependencies
└── README.md         # Optional
```

**`manifest.json` schema:**
```json
{
  "name": "opensubtitles-community",
  "display_name": "OpenSubtitles Community",
  "version": "1.2.0",
  "author": "username",
  "description": "OpenSubtitles.com provider with enhanced scoring",
  "entry_point": "provider.py",
  "class_name": "OpenSubtitlesCommunityProvider",
  "capabilities": ["network", "external_api"],
  "min_sublarr_version": "0.22.0",
  "sha256": "abc123..."
}
```

**Capabilities** (declared, not enforced — UI shows warning):

| Capability | Meaning | Warning level |
|---|---|---|
| `network` | Makes HTTP requests | Low |
| `external_api` | Calls external APIs | Low |
| `filesystem` | Reads/writes files outside media paths | High |
| `subprocess` | Spawns subprocesses | High |

**Entry point:** provider class inherits `BaseProvider` — identical to builtin providers.
Community developers write the same code as builtins.

---

## GitHub Registry & Discovery

**Discovery flow:**
```
GitHub API → search repos (topic:sublarr-provider)
           → fetch manifest.json per repo
           → read latest release .zip URL + SHA256
           → store in marketplace_cache (TTL 1h)
```

**Trust model:**
- A curated `official-registry.json` in the Sublarr repo lists verified providers
- Providers in that list → green "Official" badge
- All others → grey "Community" badge + more prominent capability warnings

**Rate limiting:**
- GitHub API: 60 req/h unauthenticated, 5000/h with token
- Optional `SUBLARR_GITHUB_TOKEN` setting
- Manual "Refresh" button in UI; cache prevents redundant requests

**DB table `marketplace_cache`:**
```
name, display_name, author, version, description,
github_url, zip_url, sha256, capabilities,
min_sublarr_version, last_fetched
```

---

## Install / Update / Uninstall

**Install flow:**
```
Download .zip from GitHub release URL
→ SHA256 verify (against manifest value)
→ Validate manifest (required fields, min_sublarr_version)
→ Show capabilities + warning modal if filesystem/subprocess
→ User confirms
→ Extract to backend/plugins/providers/<name>/
→ pip install requirements.txt (if present)
→ Write DB entry to installed_plugins
→ PluginManager.load(name) — dynamic import, register in provider registry
→ Socket.IO event → UI refresh
```

**Update:** identical to install; PluginManager.reload(name) hot-swaps without restart.

**Uninstall:**
```
PluginManager.unload(name) — remove from provider registry
→ Delete directory
→ Remove DB entry
→ Graceful drain: wait for in-flight jobs using this provider to finish
```

**DB table `installed_plugins`:**
```
name, display_name, version, path, sha256,
capabilities, enabled, installed_at
```

---

## API Routes

All under `/api/v1/marketplace/`:

```
GET    /marketplace/browse           # Cached GitHub results
POST   /marketplace/refresh          # Manual cache refresh
GET    /marketplace/installed         # installed_plugins from DB
POST   /marketplace/install           # body: {name, github_url}
POST   /marketplace/update/<name>     # Re-download + reload
DELETE /marketplace/uninstall/<name>
```

---

## UI — Settings → Providers → Marketplace Tab

**Tab structure:**
```
Settings → Providers
  ├── Configured    (existing)
  ├── Available     (existing)
  └── Marketplace   (new)
```

**Marketplace tab:**
- Search bar + "Refresh" button + "Only Installed" toggle
- Provider cards showing: Official/Community badge, name, version, author,
  capabilities, description, Install/Update/Remove action button
- "Update available" indicator when cached version > installed version

**Capability warning modal** (shown before install when `filesystem` or `subprocess` declared):
> "This provider declares `filesystem` access. Community code runs inside the Sublarr
> process. Only install if you trust the source."
> `[Cancel]` `[Install anyway]`

---

## Security Model

- **Explicit consent** — user initiates every install; no silent downloads
- **SHA-256 integrity** — zip hash verified against manifest value before extraction
- **Capability declarations** — manifest declares what the provider needs; Sublarr
  warns at install time; not enforced at runtime (no sandboxing)
- **Official vs. Community** — curated registry provides visual trust signal
- **No sandbox** — community providers run in the Sublarr process; this is accepted
  risk for a homelab tool (same model as Home Assistant custom components, Bazarr)

---

## Testing

**Backend:**
- `test_plugin_manager.py` — load/reload/unload mock provider; verify registry entry
- `test_registry.py` — GitHub API mocked; verify cache logic, TTL, official badge detection
- `test_sandbox.py` — SHA256: valid zip passes, tampered zip rejected; capability parser
- `test_marketplace_routes.py` — all 6 routes; install flow with mocked GitHub download

**Frontend:**
- `MarketplaceTab.test.tsx` — browse list renders; install button triggers API call;
  capability warning modal appears for `filesystem`/`subprocess`

**Manual smoke test:**
1. Build a real mini-provider `.zip` (5 lines, returns empty results)
2. Install via UI — verify it appears in Configured tab
3. Restart Sublarr — verify provider reloads (DB persistence)
4. Uninstall — verify it disappears

---

## Out of Scope (v0.22)

- Runtime sandboxing (subprocess/WASM isolation)
- Signature-based trust (PKI)
- pip-installable packages requiring container rebuild
- List virtualization (deferred to v0.22.x)
- Provider dependency resolution between plugins
