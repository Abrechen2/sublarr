# Feature Research: Subtitle Management Platform (Phase 2+3)

**Domain:** Subtitle management, automated download, translation, and media integration
**Researched:** 2026-02-15
**Confidence:** MEDIUM-HIGH (competitor analysis verified via official docs + community sources; some implementation patterns based on training data)

## Competitor Landscape

| Tool | Focus | Strengths | Weaknesses |
|------|-------|-----------|------------|
| Bazarr | *arr companion for subs | 20+ providers, Sonarr/Radarr deep integration, Whisper via SubGen, sub sync | No translation, forced-sub spam, subliminal_patch complexity, requires Sonarr/Radarr |
| subliminal | Python sub library | Clean API, entry-point providers, CLI | Library only (not app), 8 providers, unmaintained periods |
| Sub-Zero | Plex plugin | Tight Plex integration | Plex-only, aging, based on subliminal |
| Subgen | Whisper STT | Plex/Jellyfin/Bazarr integration, stable-ts | Generation only (no download/management), English-only translation |
| llm-subtrans | LLM translation | ASS/SRT/VTT support, OpenAI-compatible | CLI only, no provider system, no automation |

**Sublarr's unique position:** The only tool combining provider search + LLM translation + ASS-first quality + automation in one app. Phase 2+3 features should reinforce this position rather than dilute it.

---

## Feature Landscape

### Table Stakes (Users Expect These)

Features that users migrating from Bazarr or entering the subtitle automation space assume exist. Missing these creates friction or abandonment.

| Feature | Why Expected | Complexity | Notes | Status |
|---------|--------------|------------|-------|--------|
| Multi-provider search | Bazarr has 20+ providers; 4 is too few for non-anime users | MEDIUM | Plugin system enables community growth without core burden | Planned M13 |
| Provider plugin system | Community expects extensibility; Bazarr's subliminal_patch is messy but functional | HIGH | Drop-in Python files, auto-discovery, hot-reload. Critical enabler for provider growth | Planned M13 |
| Multi-backend translation | Not all users have GPU for Ollama; DeepL/LibreTranslate are expected alternatives | HIGH | ABC pattern like providers. Per-profile backend selection is differentiator | Planned M14 |
| Media-server notifications | Bazarr notifies Plex/Jellyfin/Emby/Kodi after download; table stakes for media stack | MEDIUM | Plex (python-plexapi) and Kodi (JSON-RPC) additions. Jellyfin already exists | Planned M16 |
| Forced/signs subtitle handling | Bazarr has it (badly); users expect the category to exist | MEDIUM | Key insight: default to disabled, not "wanted". Solves Bazarr's #1 forced-sub complaint | Planned M18 |
| Subtitle sync/timing | Bazarr auto-syncs based on embedded subs or audio analysis | HIGH | Integrate ffsubsync or alass rather than building from scratch | Planned M27 |
| Post-processing hooks | Bazarr supports custom scripts with env vars after download | LOW | Shell scripts + env vars (SUBLARR_FILE_PATH, etc.). Well-understood pattern | Planned M19 |
| Backup/restore | Production deployments need config portability | MEDIUM | SQLite dump + config_entries as ZIP. Already have database_backup.py foundation | Planned M20 |
| UI i18n | German-initiated project; EN/DE minimum | MEDIUM | react-i18next is the standard. Namespace per page keeps bundles small | Planned M20 |
| Dark/light theme | Every modern web app supports this | LOW | Tailwind dark: prefix. Low effort, high perceived polish | Planned M20 |
| OpenAPI documentation | Developers and integrators expect machine-readable API docs | MEDIUM | flask-smorest or manual spec. Enables third-party tooling | Planned M21 |
| Health endpoint | Docker/Kubernetes monitoring, Uptime Kuma integration | LOW | /api/v1/health/detailed with component checks. Standard pattern | Planned M21 |

### Differentiators (Competitive Advantage)

Features no competitor offers well or at all. These make Sublarr the clear choice.

| Feature | Value Proposition | Complexity | Notes | Status |
|---------|-------------------|------------|-------|--------|
| LLM translation pipeline | **Sublarr's core differentiator.** Bazarr has NO translation. Most-voted Bazarr feature request is "auto translation." | Already built | Maintain and extend. Multi-backend (M14) makes it accessible to non-GPU users | Done (extend M14) |
| ASS-first with style preservation | No other tool preserves Signs/Songs styles during translation. Anime users deeply care about this | Already built | Style classification (Dialog vs Signs/Songs) is unique. Competitors destroy styling | Done |
| Whisper as pipeline fallback | Bazarr treats Whisper as "just another provider" with fixed scores. Sublarr integrates it as intelligent fallback in the translation pipeline (provider fails -> Whisper -> translate) | HIGH | Case D in translator.py. Key workflow: Whisper SRT -> LLM translate -> target ASS. No competitor does this end-to-end | Planned M15 |
| Standalone mode (no *arr required) | Bazarr's #1 limitation: requires Sonarr/Radarr. Standalone with folder-watch + TMDB/AniList metadata opens a huge user segment | HIGH | guessit for filename parsing, watchdog for FS events, TMDB/AniList for metadata. New user acquisition vector | Planned M17 |
| Per-profile translation backend | Choose Ollama for anime (custom prompts, glossary), DeepL for movies (speed), LibreTranslate for privacy. No tool offers this granularity | MEDIUM | Requires M14 backend ABC first. Stored in language_profiles table | Planned M14 |
| Translation fallback chain | If Ollama is down, fall back to DeepL, then LibreTranslate. Zero-downtime translation | LOW | Config: ordered list of backends. Try next on failure. Simple but valuable | Planned M14 |
| Event bus + outgoing webhooks | Script hooks + HTTP webhooks enable integrations without code changes. Bazarr only has post-processing scripts, no outgoing webhooks | MEDIUM | Pub/sub event bus, existing notifications migrate onto it. HTTP webhooks with retry | Planned M19 |
| Custom scoring weights | Bazarr scores are hardcoded. Power users want to tune hash vs release_group vs ASS bonus | LOW | UI sliders for existing weight constants. Presets: "Sublarr Default", "ASS Priority", "Bazarr-compat" | Planned M19 |
| Subtitle inline editor | Web-based subtitle editing with preview. Most editors are desktop apps (Subtitle Edit, Aegisub). Browser-based ASS editing is rare | HIGH | react-subtitle-editor exists for SRT/VTT but ASS support is uncommon. Timeline + text editing. Defer to Phase 3 | Planned M24 |
| Batch operations + smart filters | "Process all anime missing German ASS subs from 2024" in one click. Bazarr batch is limited | MEDIUM | Global search + filter builder + batch action executor. Powerful for large libraries | Planned M25 |
| Glossary system | Consistent terminology across translations (character names, locations). No competitor has this | Already built | Extend: import/export, community sharing, per-language glossaries | Done |
| Quality metrics + comparison | Compare two subtitle files side-by-side. Measure translation quality. No competitor offers this | HIGH | Diff view, timing comparison, quality scoring. Niche but valued by power users | Planned M26 |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem good but create problems. Explicitly NOT building these.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Built-in video player | "Preview subs in the app" | Massive complexity, licensing issues (codecs), browser codec support varies, security surface. Desktop players do this better | Subtitle preview with text + timing display. Link to open in external player |
| Multi-user / RBAC | "Share with family" | Self-hosted single-instance tool. RBAC adds auth complexity, session management, permission bugs. Target audience is homelab single-admin | Single API key auth (already built). If needed later, reverse proxy auth (Authentik/Authelia) |
| Real-time collaborative editing | "Edit subs together" | Requires CRDT/OT, WebSocket state sync, conflict resolution. Enormous complexity for negligible use case | Single-user inline editor is sufficient |
| Provider marketplace / auto-install | "Install providers from a store" | Security nightmare (arbitrary code execution from untrusted sources), versioning hell, dependency conflicts | Manual plugin drop-in with documentation. Community GitHub repo for sharing |
| Paid provider integration | "Support premium subtitle services" | Licensing complexity, payment handling, DRM concerns | Stick to free/API-key-based providers. Users can write plugins for paid services |
| Cloud sync / multi-instance | "Sync settings across instances" | Distributed state is hard. Conflict resolution, network partitions, eventual consistency | Export/import config ZIP. One instance per media library |
| Mobile native app | "Manage subs from phone" | Development/maintenance cost for iOS+Android. Small user base for this use case | Responsive web UI works on mobile browsers. PWA if needed later |
| Transcoding / re-encoding video | "Embed subs into video" | ffmpeg muxing is destructive, slow, storage-heavy. Not subtitle management | External subtitle files only. Link to ffmpeg/Handbrake for users who need muxing |
| subliminal as dependency | "Use subliminal's provider ecosystem" | 15+ transitive deps, Bazarr-fork complexity, metaclass magic in subliminal_patch | Own lightweight provider ABC (already built). Simpler, fewer deps, better control |
| Forced subs enabled by default | "Search for forced subs for everything" | Bazarr's biggest complaint: thousands of unwanted "wanted" entries for non-existent forced subs | Default: disabled. Per-profile opt-in. Smart detection: only search when foreign audio detected |
| Building subtitle sync from scratch | "Add subtitle synchronization" | Complex audio analysis, NLP-based alignment, years of refinement in existing tools | Integrate ffsubsync or alass as external dependency via subprocess/hooks |
| Cloud-hosted SaaS mode | "Run Sublarr in the cloud" | Contradicts self-hosted philosophy. Cloud translation APIs are optional add-ons, not the hosting model | All cloud APIs (DeepL, Google, OpenAI) are optional. Core works fully offline |

---

## Feature Dependencies

```
Provider Plugin System (M13)
    |
    +---> Translation Multi-Backend (M14) [same ABC pattern, learn from M13]
    |         |
    |         +---> Whisper Integration (M15) [Whisper -> translate chain needs M14 backend]
    |         |
    |         +---> Per-Profile Backend Selection [requires M14 backends to exist]
    |
    +---> Provider Health Monitoring [extends plugin system with health tracking]
    +---> Built-in Provider Expansion [new providers use the plugin architecture]

Media-Server Abstraction (M16) [independent of M13-M15]
    |
    +---> Standalone Mode (M17) [can use media-server refresh from M16]

Forced/Signs Management (M18) [independent, builds on existing ASS style classification]

Event System (M19) [should come after M13-M18 so it captures all event types]
    |
    +---> Outgoing Webhooks [requires event bus]
    |
    +---> Script Hooks [requires event bus]
    |
    +---> Migrate existing notifications onto event bus

UI i18n (M20) [do early -- all new UI code should use t() from the start]
    +---> Backup/Restore [independent but grouped in same milestone]
    +---> Statistics Page [independent but grouped in same milestone]
    +---> Dark/Light Theme [independent]

OpenAPI + Performance (M21) [should come after API surface is stable from M13-M19]

--- Phase 3 ---

Subtitle Editor (M24) [independent, but benefits from subtitle tools in M20]
    |
    +---> Subtitle Comparison (M26) [editor foundation helps comparison UI]

Batch Operations (M25) [independent, but richer with plugin providers from M13]

Subtitle Sync (M27) [independent, integrate alass/ffsubsync as external tool]
```

### Dependency Notes

- **M15 requires M14:** Whisper generates source-language SRT. The translation backend ABC from M14 is needed to translate that SRT into the target language. Without M14, Whisper can only transcribe, not translate+transcribe.
- **M17 benefits from M16:** Standalone mode creates its own library. If media servers are abstracted (M16), standalone items can also trigger media-server refresh.
- **M19 should come after M13-M18:** The event bus should capture events from all feature areas. Building it after providers/translation/whisper/media-server/forced means more event types are available.
- **M20 (i18n) has a strategic timing concern:** Ideally do i18n setup early so all new UI from M13-M19 uses `t()` from the start. However, adding it mid-development means retrofitting existing pages. The pragmatic choice is: set up i18n infrastructure early, but full translation can happen later.
- **M21 (OpenAPI) should come last in Phase 2:** Documents the final API surface after all endpoints are added.
- **M24 (Editor) conflicts with M25 (Batch) in scope:** Both are Phase 3 UX features. Do NOT build in parallel -- editor first establishes subtitle manipulation patterns, batch ops reuses them.

---

## MVP Definition

### Phase 2 Wave 1: Core Platform (v0.2.0-beta)

These are the highest-impact features that validate Phase 2's "Open Platform" thesis.

- [x] **Provider Plugin System (M13)** -- Opens the ecosystem. Without this, Sublarr stays at 4 providers and loses non-anime users. Foundation for everything else.
- [x] **Translation Multi-Backend (M14)** -- Makes translation accessible to users without GPU. DeepL and OpenAI-compatible are the critical backends. Per-profile selection is unique.
- [x] **Whisper Integration (M15)** -- Completes the end-to-end pipeline. "No subtitle exists? Generate one." This is the killer workflow no competitor has.

### Phase 2 Wave 2: Reach Expansion (v0.3.0-beta)

Features that expand the user base and fix competitor pain points.

- [ ] **Media-Server Abstraction (M16)** -- Plex is the most-used media server; not supporting it loses users. Kodi adds homelab coverage. python-plexapi is mature.
- [ ] **Standalone Mode (M17)** -- Opens Sublarr to non-*arr users. guessit + watchdog + TMDB metadata. Validate demand before investing heavily.
- [ ] **Forced/Signs Management (M18)** -- Solves Bazarr's worst pain point. Default-disabled avoids the "thousands of wanted entries" trap. Builds on existing ASS style classification.

### Phase 2 Wave 3: Platform Polish (v0.4.0-beta)

Features that make the platform production-ready and extensible.

- [ ] **Event System + Hooks + Custom Scoring (M19)** -- Enables automation and third-party integration without code changes. Outgoing webhooks are differentiating.
- [ ] **UI i18n + Backup/Restore + Statistics + Theme (M20)** -- Production readiness. German community. Visual polish.
- [ ] **OpenAPI + Performance + Health + Tasks Page (M21)** -- API documentation for the final API surface. Performance optimization for large libraries. Tasks dashboard.

### Phase 2 Wave 4: Stabilization (v0.9.0-beta -> v1.0.0)

- [ ] **Community Launch + Documentation (M22)** -- Migration guide, plugin developer guide, user guide.
- [ ] **Performance & Scalability (M23)** -- PostgreSQL option, Redis, RQ job queue. Only for users at scale.

### Phase 3: Advanced Features (v1.1+)

Defer until Phase 2 is stable and community feedback confirms demand.

- [ ] **Subtitle Editor (M24)** -- High complexity, niche. Desktop editors (Subtitle Edit, Aegisub) serve this today. But web-based ASS editing IS a market gap.
- [ ] **Batch Operations (M25)** -- Valuable for power users with 1000+ series. Smart filters make it powerful.
- [ ] **Subtitle Comparison (M26)** -- Side-by-side diff, quality scoring. Very niche but unique.
- [ ] **Subtitle Sync Tools (M27)** -- Integrate alass or ffsubsync rather than building from scratch.
- [ ] **Dashboard Widgets + Quick-Actions (M28)** -- Polish, not priority.
- [ ] **API Key Management + Bazarr Migration (M29)** -- Migration tool helps Bazarr users switch.
- [ ] **Notification Templates + Quiet Hours (M30)** -- Power user feature.
- [ ] **Deduplication + Cleanup (M31)** -- Maintenance tooling.
- [ ] **External Tool Integration (M32)** -- Ecosystem integration.

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority | Phase |
|---------|------------|---------------------|----------|-------|
| Provider Plugin System | HIGH | HIGH | P1 | 2 (v0.2) |
| Translation Multi-Backend | HIGH | HIGH | P1 | 2 (v0.2) |
| Whisper STT Integration | HIGH | HIGH | P1 | 2 (v0.2) |
| Media-Server Abstraction (Plex/Kodi) | HIGH | MEDIUM | P1 | 2 (v0.3) |
| Standalone Mode | HIGH | HIGH | P1 | 2 (v0.3) |
| Forced/Signs Management | MEDIUM | MEDIUM | P2 | 2 (v0.3) |
| Event System + Hooks | MEDIUM | MEDIUM | P2 | 2 (v0.4) |
| Custom Scoring | LOW | LOW | P2 | 2 (v0.4) |
| UI i18n (EN/DE) | MEDIUM | MEDIUM | P2 | 2 (v0.4) |
| Backup/Restore | MEDIUM | LOW | P2 | 2 (v0.4) |
| Statistics Page | MEDIUM | MEDIUM | P2 | 2 (v0.4) |
| Dark/Light Theme | LOW | LOW | P2 | 2 (v0.4) |
| OpenAPI/Swagger Docs | MEDIUM | MEDIUM | P2 | 2 (v0.4) |
| Performance Optimization | HIGH | MEDIUM | P2 | 2 (v0.4) |
| Health Endpoint | LOW | LOW | P2 | 2 (v0.4) |
| Tasks Page | MEDIUM | MEDIUM | P2 | 2 (v0.4) |
| Subtitle Processing Tools | LOW | MEDIUM | P3 | 2 (v0.4) |
| Subtitle Editor | MEDIUM | HIGH | P3 | 3 |
| Batch Operations | MEDIUM | MEDIUM | P3 | 3 |
| Subtitle Comparison | LOW | HIGH | P3 | 3 |
| Subtitle Sync Tools | MEDIUM | HIGH | P3 | 3 |
| Dashboard Widgets | LOW | LOW | P3 | 3 |
| API Key Management | LOW | MEDIUM | P3 | 3 |
| Notification Templates | LOW | MEDIUM | P3 | 3 |
| Deduplication/Cleanup | LOW | MEDIUM | P3 | 3 |

**Priority key:**
- P1: Must have -- validates the "Open Platform" thesis or fills critical competitive gaps
- P2: Should have -- production readiness, polish, power-user features
- P3: Nice to have -- defer until community feedback confirms demand

---

## Competitor Feature Analysis

| Feature | Bazarr | subliminal | Sub-Zero | Subgen | Sublarr (current) | Sublarr (planned) |
|---------|--------|------------|----------|--------|-------------------|-------------------|
| Provider count | 20+ | 8 | 8 (via subliminal) | 0 (generates) | 4 | 12+ via plugins |
| Plugin/extension system | No (hardcoded subliminal_patch) | Entry-point based | No | No | No | Yes (M13) |
| Translation | No | No | No | Whisper EN-only | Ollama LLM | Multi-backend (M14) |
| Whisper/STT | Via SubGen external | No | No | Core feature | No | Integrated fallback (M15) |
| ASS style handling | Basic | No | No | No (SRT only) | Advanced (classify+preserve) | Maintained |
| Forced sub mgmt | Yes (broken -- spam) | No | No | No | No | Smart defaults (M18) |
| Standalone mode | No (requires *arr) | Yes (CLI) | No (requires Plex) | Partial | No (requires *arr) | Folder-watch+metadata (M17) |
| Plex support | Yes | N/A | Core | Yes | No | Yes (M16) |
| Jellyfin support | Yes | N/A | No | Yes | Yes | Yes (maintained) |
| Kodi support | Yes | N/A | No | No | No | Yes (M16) |
| Post-processing | Custom scripts | No | No | No | Notifications only | Events+hooks+webhooks (M19) |
| Sub sync | Yes (ffsubsync) | No | No | stable-ts | No | Integrate external (M27) |
| Subtitle editor | No | No | No | No | No | Web-based ASS (M24) |
| Scoring config | Hardcoded | Hardcoded | Hardcoded | Fixed (67%/51%) | Hardcoded | Configurable (M19) |
| API docs | No | No | No | No | No | OpenAPI (M21) |
| Glossary | No | No | No | No | Yes | Extended |
| Quality validation | No | No | No | No | Yes (line count, hallucination) | Extended |
| Batch operations | Limited | CLI batch | No | No | Batch search | Smart filter+batch (M25) |

---

## Key Insights from Research

### 1. Translation is the killer feature -- protect and extend it
Bazarr's most-voted feature request is "auto translation." Multiple community requests ask for download+translate automation. Sublarr is the ONLY tool that does this. Every Phase 2 feature should reinforce or extend the translation story. Multi-backend (M14) is the most impactful extension because it removes the GPU barrier.

### 2. Forced subtitle handling needs a different philosophy
Bazarr's approach (search forced for everything by default) creates thousands of spurious "wanted" entries. Users explicitly request "treat forced as optional" on FeatureUpvote. Sublarr should default forced to DISABLED and use smart detection (foreign audio parts detected -> search forced). This alone converts frustrated Bazarr users.

### 3. Provider count matters for non-anime adoption
With 4 providers, Sublarr is viable for anime (AnimeTosho + Jimaku cover most needs). For general media, OpenSubtitles + SubDL is insufficient. The plugin system (M13) is the force multiplier -- built-in providers provide a baseline (Addic7ed, Podnapisi, Gestdown, Kitsunekko), community plugins provide the long tail without core maintenance burden.

### 4. Whisper integration should be a pipeline step, not just a provider
Bazarr treats Whisper as another provider (SubGen) with fixed low scores (67% episode, 51% movie). This forces users to lower score thresholds globally, accepting worse subtitle matches. Sublarr's approach is better: Whisper is Case D in the translation pipeline -- triggered only when ALL providers fail. The workflow is: no provider has subs -> Whisper transcribes source audio -> LLM translates -> target language subtitle. No competitor does this end-to-end.

### 5. Standalone mode is a significant acquisition channel
The #1 Bazarr limitation mentioned across forums is "requires Sonarr/Radarr." Users with manually organized media, Plex-only setups, or non-*arr workflows have no good option. Standalone mode with folder-watch (watchdog) + filename parsing (guessit) + metadata enrichment (TMDB/AniList) opens this segment. The key architectural insight: standalone items should use the exact same `wanted_items` table and translation pipeline as *arr-sourced items.

### 6. Browser-based ASS editing is a gap in the market
Most subtitle editors are desktop apps (Subtitle Edit, Aegisub). Browser-based editors exist for SRT/VTT (react-subtitle-editor) but NOT for ASS. A web-based ASS editor with style preview would be genuinely novel. However, complexity is very high (ASS rendering, timeline UI, style editor). This is correctly placed in Phase 3 -- build it when the rest of the platform is stable.

### 7. Sub sync should leverage existing tools, not rebuild
Bazarr uses ffsubsync for auto-sync. alass is another strong option (reportedly faster and more accurate). Building subtitle synchronization from scratch requires audio analysis, text alignment, and edge-case handling that has been refined over years in these projects. Integrate one as an external dependency via subprocess call. ffsubsync is the safer choice (more users, known patterns), but alass may be more accurate.

### 8. i18n timing is strategic
Setting up react-i18next early means all new UI components from M13-M21 use `t()` from the start, avoiding a painful retrofit. However, the actual translation work (EN -> DE) can happen later. Recommendation: set up i18n infrastructure in the first Phase 2 milestone, extract strings progressively as milestones are built.

---

## Sources

### Verified (MEDIUM-HIGH confidence)
- [Bazarr Wiki - Settings](https://wiki.bazarr.media/Additional-Configuration/Settings/) -- Feature inventory, sync thresholds, post-processing
- [Bazarr Wiki - Whisper Provider](https://wiki.bazarr.media/Additional-Configuration/Whisper-Provider/) -- Whisper/SubGen integration details, score limitations
- [Bazarr GitHub Issues](https://github.com/morpheus65535/bazarr/issues) -- Forced sub complaints (#2041, #1505, #1580, #1398), scoring issues (#1418)
- [Bazarr FeatureUpvote](https://bazarr.featureupvote.com/) -- Community feature requests (translation, forced subs, manual import)
- [TRaSH Guides - Bazarr Scoring](https://trash-guides.info/Bazarr/Bazarr-suggested-scoring/) -- Scoring thresholds (90/80 recommended)
- [Subgen GitHub](https://github.com/McCloudS/subgen) -- Whisper subtitle generation, faster-whisper, stable-ts
- [subliminal GitHub](https://github.com/Diaoul/subliminal) -- Provider architecture, entry-point extensibility
- [subliminal Docs](https://subliminal.readthedocs.io/) -- Version 2.2.0, supported providers
- [DeepL Python Library](https://github.com/DeepLcom/deepl-python) -- Official translation API, 500k chars/mo free
- [DeepL SRT Translation](https://www.deepl.com/en/features/document-translation/srt) -- Native SRT support
- [LibreTranslate GitHub](https://github.com/LibreTranslate/LibreTranslate) -- Self-hosted translation, v1.8.4, batch support, Argos Translate engine
- [vLLM OpenAI-Compatible Server](https://docs.vllm.ai/en/latest/serving/openai_compatible_server/) -- OpenAI-compatible API pattern
- [llm-subtrans](https://github.com/machinewrapped/llm-subtrans) -- LLM subtitle translation, ASS/SRT/VTT, OpenAI-compatible API support
- [python-plexapi](https://python-plexapi.readthedocs.io/) -- Plex API integration, subtitle management, library refresh
- [Kodi JSON-RPC API v13](https://kodi.wiki/view/JSON-RPC_API/v13) -- Library scan, subtitle management
- [watchdog PyPI](https://pypi.org/project/watchdog/) -- Filesystem monitoring, cross-platform
- [guessit GitHub](https://github.com/guessit-io/guessit) -- Media filename parsing, LGPLv3
- [react-subtitle-editor](https://github.com/spun/react-subtitle-editor) -- Browser-based subtitle editing (SRT/VTT, not ASS)
- [tmdbv3api](https://github.com/AnthonyBloomer/tmdbv3api) -- TMDB API Python wrapper

### Training-data derived (LOW confidence -- verify during implementation)
- Specific ffsubsync vs alass performance comparison for subtitle sync
- Exact SubGen API contract details beyond what's documented in wiki
- AniList GraphQL schema specifics for anime metadata endpoints
- react-i18next namespace loading performance characteristics
- Browser-based ASS rendering library maturity

---
*Feature landscape research for: Sublarr Phase 2+3 subtitle management platform*
*Researched: 2026-02-15*
