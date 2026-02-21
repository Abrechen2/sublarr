# Requirements — v0.10.0-beta: Translation Excellence + Anime Quality

**Milestone:** v0.10.0-beta
**Created:** 2026-02-21
**Status:** Defined — awaiting roadmap

---

## Milestone Requirements

### A. Translation Quality

- [ ] **TRANS-01**: User can define a per-series glossary (character names, terms) that overrides the global glossary during LLM translation for that series
- [ ] **TRANS-02**: User can edit per-series glossary entries in the Settings or Series Detail view
- [ ] **TRANS-03**: LLM translation sends N configurable preceding and following subtitle lines as context alongside the lines being translated (context-window batching)
- [ ] **TRANS-04**: User can configure the context window size (0 = disabled, default: 3 lines before + after)
- [ ] **TRANS-05**: Successfully translated subtitle lines are stored in a translation memory cache keyed by source language + target language + normalized text
- [ ] **TRANS-06**: On subsequent translation runs, the system re-uses cached translations for identical or near-identical source lines (configurable similarity threshold)
- [ ] **TRANS-07**: After translating a subtitle line, the LLM evaluates its own output and assigns a quality score (0-100); lines below a configurable threshold are automatically retried
- [ ] **TRANS-08**: Quality scores are stored per translated file and visible in the subtitle editor and job history

### B. Sync and Auto-Repair

- [ ] **SYNC-01**: User can trigger auto-sync (alass or ffsubsync) for a single subtitle file directly from the Library view, Series Detail, or Subtitle Editor
- [ ] **SYNC-02**: User can trigger bulk auto-sync for an entire series (all episodes) or the entire library from the Library view or Tools section
- [ ] **SYNC-03**: Bulk sync runs as a background job with real-time progress via WebSocket (current file, completed count, failed count)
- [ ] **SYNC-04**: User can choose the sync engine (alass or ffsubsync) per operation or globally in Settings
- [ ] **SYNC-05**: Sync operations create a .bak backup of the original subtitle file before modifying it

### C. Provider Intelligence

- [ ] **PROV-01**: The system analyzes downloaded subtitle metadata and text patterns to detect likely machine-translated subtitles
- [ ] **PROV-02**: Detected machine-translated subtitles receive a configurable score penalty (default: -30 points) applied before the download decision
- [ ] **PROV-03**: MT-detection results are shown in the provider search results UI (badge with confidence %)
- [ ] **PROV-04**: User can configure the MT score penalty (0 = disabled) and confidence threshold in Settings Providers
- [ ] **PROV-05**: For OpenSubtitles provider: the uploader trust score is fetched and incorporated into subtitle scoring (normalized 0-20 bonus points)
- [ ] **PROV-06**: Uploader trust bonus is shown in search results alongside the existing score breakdown

### D. LLM Backend Presets

- [ ] **LLM-01**: The TranslationTab shows an "Add from Template" option listing pre-configured templates (DeepSeek V3, Gemini 1.5 Flash, Claude Haiku, Mistral Medium, LM Studio local)
- [ ] **LLM-02**: Selecting a template pre-fills the API endpoint, model name, and recommended context-window size; user still provides API key
- [ ] **LLM-03**: Templates include a brief description of cost/quality tradeoff visible in the template picker

### E. Anime AniDB Absolute Order

- [ ] **ANIME-01**: User can enable "Absolute Order" mode per series in Series Settings; when enabled, Sublarr maps Sonarr S/E numbering to AniDB absolute episode numbers for provider search
- [ ] **ANIME-02**: The system maintains an AniDB mapping table (sourced from anime-lists project or manual entry) mapping TVDB series ID plus season/episode to AniDB episode number
- [ ] **ANIME-03**: The mapping table is auto-refreshed on a configurable schedule (default: weekly) and can be manually triggered
- [ ] **ANIME-04**: Providers that accept absolute episode numbers (AnimeTosho, Jimaku) receive the AniDB absolute number; providers using S/E receive correct numbering from Sonarr

### F. Whisper Fallback Mode

- [ ] **WHIS-01**: User can configure a minimum provider score threshold (0-100) below which Whisper transcription is automatically triggered as fallback (default: disabled)
- [ ] **WHIS-02**: When threshold is set and all provider results are below threshold, Whisper runs automatically and its result is used
- [ ] **WHIS-03**: Whisper-generated subtitles are tagged as whisper_generated and flagged as upgrade candidates so better provider results can replace them later

### G. Tag-based Profile Assignment

- [ ] **PROF-01**: User can create tag mapping rules: Sonarr/Radarr tag label to Language Profile name (e.g., tag "anime-ja" to profile "Anime DE")
- [ ] **PROF-02**: When a new series/movie is added via webhook, Sublarr checks its Sonarr/Radarr tags and auto-assigns the matching Language Profile
- [ ] **PROF-03**: Tag mapping rules are manageable in Settings Language Profiles
- [ ] **PROF-04**: If no tag rule matches, the existing default profile logic applies unchanged

---

## Future Requirements (Deferred)

- Subtitle burning for HLS transcoding
- Plugin Marketplace UI (browse and install plugins via web)
- Mobile-optimized view
- Multi-user RBAC
- Real-time collaborative editing

---

## Out of Scope

- AniDB account integration (read-only mapping table is sufficient)
- Cloud subtitle storage
- Paid provider integrations
- Breaking API changes (all v0.9.x endpoints remain compatible)

---

## Traceability (filled by roadmapper)

| REQ-ID | Phase | Notes |
|--------|-------|-------|
| TRANS-01..08 | TBD | |
| SYNC-01..05 | TBD | |
| PROV-01..06 | TBD | |
| LLM-01..03 | TBD | |
| ANIME-01..04 | TBD | |
| WHIS-01..03 | TBD | |
| PROF-01..04 | TBD | |
