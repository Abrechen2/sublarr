# Roadmap: Sublarr

## Milestones

- v0.9.0-beta -- Open Platform + Advanced Features -- Phases 0-16 (shipped 2026-02-20)
- v0.9.5-beta -- Performance Optimizations -- Phase 17 (shipped 2026-02-21)
- v0.10.0-beta -- Translation Excellence + Anime Quality -- Phases 18-28 (in progress)

## Phases

<details>
<summary>v0.9.0-beta -- Open Platform + Advanced Features (Phases 0-16) -- SHIPPED 2026-02-20</summary>

- [x] Phase 0: Architecture Refactoring (3/3 plans)
- [x] Phase 1: Provider Plugin + Expansion (6/6 plans)
- [x] Phase 2: Translation Multi-Backend (6/6 plans)
- [x] Phase 3: Media-Server Abstraction (3/3 plans)
- [x] Phase 4: Whisper Speech-to-Text (3/3 plans)
- [x] Phase 5: Standalone Mode (5/5 plans)
- [x] Phase 6: Forced/Signs Subtitle Management (3/3 plans)
- [x] Phase 7: Events/Hooks + Custom Scoring (3/3 plans)
- [x] Phase 8: i18n + Backup + Admin Polish (5/5 plans)
- [x] Phase 9: OpenAPI + Release Preparation (5/5 plans)
- [x] Phase 10: Performance & Scalability (8/8 plans)
- [x] Phase 11: Subtitle Editor (4/4 plans)
- [x] Phase 12: Batch Operations + Smart-Filter (3/3 plans)
- [x] Phase 13: Comparison + Sync + Health-Check (3/3 plans)
- [x] Phase 14: Dashboard Widgets + Quick-Actions (2/2 plans)
- [x] Phase 15: API-Key Mgmt + Notifications + Cleanup (5/5 plans)
- [x] Phase 16: External Integrations (3/3 plans)

See `.planning/milestones/v0.9.0-beta-ROADMAP.md` for full phase details.

</details>

<details>
<summary>v0.9.5-beta -- Performance Optimizations (Phase 17) -- SHIPPED 2026-02-21</summary>

- [x] Phase 17: Performance Optimizations (3/3 plans) -- Debug interceptor removal, N+1 fixes, frontend bundle

</details>

### v0.10.0-beta -- Translation Excellence + Anime Quality (In Progress)

**Milestone Goal:** Subtitle quality on a new level -- context-aware LLM translation with per-series glossaries, library-wide auto-sync, AI detection of bad provider subtitles, and anime-specific improvements.

- [ ] **Phase 18: Per-Series Glossary** -- Series-specific translation glossaries extending the global glossary system
- [ ] **Phase 19: Context-Window Batching** -- LLM receives surrounding lines as context for better translation coherence
- [ ] **Phase 20: Translation Memory Cache** -- Cache and reuse translations for identical/similar source lines
- [ ] **Phase 21: Translation Quality Scoring** -- LLM self-evaluation with automatic retry for low-quality lines
- [ ] **Phase 22: Bulk Auto-Sync** -- Library-wide subtitle timing alignment via alass/ffsubsync
- [ ] **Phase 23: Machine Translation Detection** -- Detect and penalize machine-translated provider subtitles
- [ ] **Phase 24: Uploader Trust Scoring** -- Incorporate OpenSubtitles uploader reputation into scoring
- [ ] **Phase 25: AniDB Absolute Episode Order** -- Map Sonarr S/E numbering to AniDB absolute numbers for anime
- [ ] **Phase 26: Whisper Fallback Threshold** -- Threshold-based automatic Whisper activation when provider quality is low
- [ ] **Phase 27: Tag-based Profile Assignment** -- Auto-assign Language Profiles from Sonarr/Radarr tags
- [ ] **Phase 28: LLM Backend Presets** -- Pre-configured templates for popular LLM providers

## Phase Details

### Phase 18: Per-Series Glossary
**Goal**: Users can define series-specific glossary entries that override global glossary during translation, ensuring character names and terms are consistently translated per series.
**Depends on**: Nothing (first phase of milestone)
**Requirements**: TRANS-01, TRANS-02
**Success Criteria** (what must be TRUE):
  1. User can create glossary entries scoped to a specific series from the Series Detail view
  2. User can edit and delete per-series glossary entries
  3. When translating a subtitle for that series, per-series glossary entries take precedence over global glossary entries with the same source term
  4. Series without per-series glossary entries continue to use only the global glossary (no regression)
**Plans**: TBD

Plans:
- [ ] 18-01: Backend data model + API (DB table, CRUD endpoints, glossary merge logic)
- [ ] 18-02: Frontend UI (Series Detail glossary tab, Settings glossary management)

### Phase 19: Context-Window Batching
**Goal**: LLM translation calls include surrounding subtitle lines as context, producing more coherent translations that account for conversational flow and scene continuity.
**Depends on**: Phase 18 (glossary merge logic established)
**Requirements**: TRANS-03, TRANS-04
**Success Criteria** (what must be TRUE):
  1. When translating a subtitle line, the LLM prompt includes N preceding and N following lines as context alongside the target lines
  2. User can configure the context window size in Settings (0 to disable, default 3 lines before + after)
  3. Translation output quality is visibly improved for conversational dialogue (context-dependent pronouns, references)
**Plans**: TBD

Plans:
- [ ] 19-01: Backend pipeline changes (context assembly, batch prompt formatting, config entry)
- [ ] 19-02: Frontend config UI + verification

### Phase 20: Translation Memory Cache
**Goal**: Previously translated lines are cached and reused on subsequent runs, dramatically reducing LLM API calls and cost for series with repeated phrases or re-translation scenarios.
**Depends on**: Phase 19 (context-window changes to translation pipeline settled)
**Requirements**: TRANS-05, TRANS-06
**Success Criteria** (what must be TRUE):
  1. Successfully translated lines are stored in a persistent cache keyed by source language, target language, and normalized text
  2. On subsequent translation runs, cached translations are reused for identical source lines without calling the LLM
  3. Near-identical lines (configurable similarity threshold) also hit the cache
  4. User can configure the similarity threshold and clear the translation memory cache from Settings
**Plans**: TBD

Plans:
- [ ] 20-01: Backend cache system (DB table, similarity matching, cache lookup/store in pipeline)
- [ ] 20-02: Frontend config + cache management UI

### Phase 21: Translation Quality Scoring
**Goal**: Every translated line receives an LLM-assigned quality score, and low-scoring lines are automatically retried, giving users confidence in translation output and surfacing problem areas.
**Depends on**: Phase 20 (translation pipeline stable after cache integration)
**Requirements**: TRANS-07, TRANS-08
**Success Criteria** (what must be TRUE):
  1. After translating a subtitle line, the LLM evaluates its own output and assigns a quality score (0-100)
  2. Lines scoring below a configurable threshold are automatically retried (up to a configurable max retries)
  3. Quality scores are visible per line in the Subtitle Editor
  4. Aggregate quality scores per file are visible in Job History
  5. User can configure the quality threshold and max retries in Settings
**Plans**: TBD

Plans:
- [ ] 21-01: Backend scoring pipeline (LLM evaluation prompt, retry logic, score storage)
- [ ] 21-02: Frontend display (editor score column, job history scores, config UI)

### Phase 22: Bulk Auto-Sync
**Goal**: Users can align subtitle timing across their entire library or per series using alass/ffsubsync, with real-time progress tracking and safe backup handling.
**Depends on**: Nothing (independent feature, extends existing Phase 13 sync tools)
**Requirements**: SYNC-01, SYNC-02, SYNC-03, SYNC-04, SYNC-05
**Success Criteria** (what must be TRUE):
  1. User can trigger auto-sync for a single subtitle file from Library view, Series Detail, or Subtitle Editor
  2. User can trigger bulk auto-sync for an entire series or the entire library
  3. Bulk sync runs as a background job with real-time WebSocket progress (current file, completed count, failed count)
  4. User can choose the sync engine (alass or ffsubsync) per operation or globally in Settings
  5. Every sync operation creates a .bak backup of the original subtitle file before modifying it
**Plans**: TBD

Plans:
- [ ] 22-01: Backend bulk sync engine (job queue integration, backup logic, engine selection, progress events)
- [ ] 22-02: Frontend sync UI (single-file triggers, bulk controls, progress display, engine config)

### Phase 23: Machine Translation Detection
**Goal**: The system identifies likely machine-translated subtitles from providers and applies a score penalty, so users automatically get human-translated subtitles when available.
**Depends on**: Nothing (independent feature, modifies provider scoring pipeline)
**Requirements**: PROV-01, PROV-02, PROV-03, PROV-04
**Success Criteria** (what must be TRUE):
  1. Downloaded subtitle metadata and text patterns are analyzed to detect likely machine translation
  2. Detected MT subtitles receive a configurable score penalty (default -30) applied before the download decision
  3. MT detection results appear in provider search results UI as a badge with confidence percentage
  4. User can configure the MT score penalty (0 = disabled) and confidence threshold in Settings Providers
**Plans**: TBD

Plans:
- [ ] 23-01: Backend MT detection engine (text analysis, metadata heuristics, scoring integration)
- [ ] 23-02: Frontend UI (search result badges, Settings config)

### Phase 24: Uploader Trust Scoring
**Goal**: OpenSubtitles uploader reputation is factored into subtitle scoring, giving a bonus to subtitles from trusted uploaders and improving download decisions.
**Depends on**: Phase 23 (scoring pipeline changes settled)
**Requirements**: PROV-05, PROV-06
**Success Criteria** (what must be TRUE):
  1. For OpenSubtitles results, the uploader trust score is fetched and incorporated as a normalized bonus (0-20 points)
  2. The uploader trust bonus is visible in search results alongside the existing score breakdown
  3. Non-OpenSubtitles providers are unaffected (no regression)
**Plans**: TBD

Plans:
- [ ] 24-01: Backend + frontend (OpenSubtitles API integration, scoring formula, UI display)

### Phase 25: AniDB Absolute Episode Order
**Goal**: Anime series using absolute episode numbering get correct subtitle matches by mapping Sonarr S/E numbers to AniDB absolute numbers for provider searches.
**Depends on**: Nothing (independent feature, new subsystem)
**Requirements**: ANIME-01, ANIME-02, ANIME-03, ANIME-04
**Success Criteria** (what must be TRUE):
  1. User can enable Absolute Order mode per series in Series Settings
  2. The system maintains an AniDB mapping table (TVDB series ID + S/E to AniDB absolute episode number) sourced from anime-lists or manual entry
  3. The mapping table auto-refreshes on a configurable schedule (default weekly) and can be manually triggered
  4. Providers accepting absolute numbers (AnimeTosho, Jimaku) receive the AniDB absolute number; S/E providers receive Sonarr numbering unchanged
**Plans**: TBD

Plans:
- [ ] 25-01: Backend data model + mapping engine (DB table, anime-lists sync, scheduler, mapping logic)
- [ ] 25-02: Provider integration + frontend UI (provider query adaptation, series settings toggle, mapping management)

### Phase 26: Whisper Fallback Threshold
**Goal**: When all provider results are below a minimum quality threshold, Whisper transcription automatically kicks in as fallback, ensuring users always get usable subtitles.
**Depends on**: Nothing (modifies existing wanted_search pipeline, independent of other phases)
**Requirements**: WHIS-01, WHIS-02, WHIS-03
**Success Criteria** (what must be TRUE):
  1. User can configure a minimum provider score threshold (0-100) below which Whisper is triggered (default: disabled)
  2. When threshold is set and all provider results score below it, Whisper runs automatically and its result is used
  3. Whisper-generated subtitles are tagged as whisper_generated and flagged as upgrade candidates so better provider results can replace them later
**Plans**: TBD

Plans:
- [ ] 26-01: Backend + frontend (threshold config, wanted_search decision logic, tagging, UI config)

### Phase 27: Tag-based Profile Assignment
**Goal**: Language Profiles are automatically assigned to new series/movies based on Sonarr/Radarr tags, eliminating manual profile configuration for tag-organized libraries.
**Depends on**: Nothing (independent feature, modifies webhook handling)
**Requirements**: PROF-01, PROF-02, PROF-03, PROF-04
**Success Criteria** (what must be TRUE):
  1. User can create tag mapping rules (Sonarr/Radarr tag label to Language Profile name) in Settings
  2. When a new series/movie arrives via webhook, its tags are checked and the matching Language Profile is auto-assigned
  3. Tag mapping rules are manageable (create, edit, delete) in Settings Language Profiles section
  4. If no tag rule matches, the existing default profile logic applies unchanged (no regression)
**Plans**: TBD

Plans:
- [ ] 27-01: Backend (DB table for tag rules, webhook integration, CRUD API)
- [ ] 27-02: Frontend (tag rule management UI in Settings)

### Phase 28: LLM Backend Presets
**Goal**: New users can quickly configure popular LLM backends from pre-built templates instead of manually entering API endpoints and model names.
**Depends on**: Nothing (UI-only, no backend pipeline changes)
**Requirements**: LLM-01, LLM-02, LLM-03
**Success Criteria** (what must be TRUE):
  1. The TranslationTab shows an Add from Template option listing pre-configured templates (DeepSeek V3, Gemini 1.5 Flash, Claude Haiku, Mistral Medium, LM Studio local)
  2. Selecting a template pre-fills API endpoint, model name, and recommended context-window size; user provides only the API key
  3. Each template includes a brief description of cost/quality tradeoff visible in the template picker
**Plans**: TBD

Plans:
- [ ] 28-01: Backend + frontend (template definitions, template picker component, pre-fill logic)

## Progress

**Execution Order:**
Phases execute in numeric order: 18 -> 19 -> 20 -> 21 -> 22 -> 23 -> 24 -> 25 -> 26 -> 27 -> 28

Note: Phases 22, 23, 25, 26, 27, 28 have no dependencies on other v0.10.0-beta phases and could be parallelized or reordered if needed. The listed order prioritizes the translation quality stack (18-21) first as it is the milestone core theme.

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 18. Per-Series Glossary | 0/2 | Not started | - |
| 19. Context-Window Batching | 0/2 | Not started | - |
| 20. Translation Memory Cache | 0/2 | Not started | - |
| 21. Translation Quality Scoring | 0/2 | Not started | - |
| 22. Bulk Auto-Sync | 0/2 | Not started | - |
| 23. Machine Translation Detection | 0/2 | Not started | - |
| 24. Uploader Trust Scoring | 0/1 | Not started | - |
| 25. AniDB Absolute Episode Order | 0/2 | Not started | - |
| 26. Whisper Fallback Threshold | 0/1 | Not started | - |
| 27. Tag-based Profile Assignment | 0/2 | Not started | - |
| 28. LLM Backend Presets | 0/1 | Not started | - |

---
*Roadmap created: 2026-02-15*
*Last updated: 2026-02-21 -- v0.10.0-beta milestone roadmap created (11 phases, 33 requirements)*
