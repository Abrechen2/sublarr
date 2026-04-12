# Road to V1.0 — Release Roadmap

**Created:** 2026-04-12
**Current version:** 0.50.0-beta
**Target:** 1.0.0 (stable)

## Context

Sublarr has been in active beta development for ~7 weeks (v0.1 through v0.50), accumulating 35 subtitle providers, LLM translation, a plugin system, web player, CLI mode, standalone mode, full i18n (DE/EN), and comprehensive security hardening. The codebase is feature-rich but needs stabilization, test coverage, and final polish before a V1 stable release.

### Current State Summary

| Metric | Value |
|--------|-------|
| Backend test coverage | ~24% (1,579 tests collected) |
| Frontend unit tests | 783 tests (4 failing) |
| Frontend E2E tests | 31 spec files (58 tests skipped) |
| Files >800 LOC | 10 files (9,437 lines total) |
| Known broken tests | 6 (4 backend, 2 frontend) |
| Settings gap analysis | Multiple wrong config keys, missing UI fields |
| Security findings | 16 pentest findings (11 fixed, 5 accepted/open) |
| OpenAPI coverage | Partial (framework in place, most routes undocumented) |

---

## Phase 1: Code Health

**Goal:** Make the codebase maintainable and V1-worthy.

### 1.1 Split oversized files

All 10 files exceeding the 800-line project limit must be refactored into smaller, focused modules:

| File | Lines | Split Strategy |
|------|-------|----------------|
| `services/wanted_scanner_core.py` | 1,233 | Scanner + ItemProcessor + FailureTracker |
| `routes/cleanup.py` | 1,113 | Routes (thin) + CleanupService |
| `routes/standalone.py` | 967 | Routes + StandaloneService |
| `routes/profiles.py` | 964 | Routes + ProfileService |
| `bazarr_migrator.py` | 948 | Migrator + DataMapper + Validators |
| `translator/core.py` | 926 | TranslationOrchestrator + BatchProcessor |
| `providers/__init__.py` | 847 | ProviderManager + ProviderRegistry + SearchCoordinator (partially done) |
| `routes/subtitles.py` | 824 | Routes + SubtitleService |
| `config.py` | 812 | Settings + ConfigGroups (or accept as config-only, evaluate) |
| `routes/api_keys.py` | 803 | Routes + ApiKeyService |

**Rule:** No new code may exceed 800 lines. Each split must preserve all existing tests.

### 1.2 Fix broken tests

- 4 backend tests: `test_sonarr_download_webhook`, `test_radarr_download_webhook`, `test_parse_llm_response_too_many_merge`, `test_record_backend_success`
- 2 frontend tests: CleanupSettings (4 assertions failing on "Neu" button text)
- Re-evaluate ignored test files: `test_video_sync.py`, `test_translation_backends.py`, `test_provider_pipeline.py` — fix or permanently remove with rationale

### 1.3 Settings gap analysis

Resolve all findings from `docs/SETTINGS_GAP_ANALYSIS.md`:
- Fix wrong config keys (frontend sends keys that backend silently discards)
- Add missing UI fields for settings that users need access to
- Remove or document settings that intentionally stay ENV-only

### 1.4 Code cleanup

- Remove debug `console.log` statements (SettingsSearchModal.tsx)
- Audit for any remaining debug artifacts

---

## Phase 2: Test Coverage

**Goal:** Backend 70%+, Frontend 70%+, Settings pages fully covered.

### 2.1 Backend coverage: 24% to 70%

Current: 1,579 tests, ~24% line coverage. Target: ~2,300-2,400 tests, 70%+ coverage.

Priority modules for new tests (by business criticality):
1. **Services layer** — wanted_scanner, translation orchestrator, provider manager
2. **Routes** — all API endpoints with happy path + error cases
3. **Repositories** — data access layer edge cases
4. **Security modules** — security_utils, auth, ui_auth (extend existing 22 tests)
5. **Integration** — provider pipeline, webhook processing

### 2.2 Frontend unit coverage

- Fix 4 failing tests first
- Measure current coverage (v8 provider configured, thresholds at 70%)
- Focus on: Settings components, API hooks, state management, form validation

### 2.3 Settings page testing

The Settings pages are the most complex UI surface in Sublarr (48 components across 8 top-level pages with dozens of sub-tabs). They require dedicated, thorough testing:

**Unit tests (Vitest):**
- Every Settings page renders without crash
- Every FormGroup saves the correct config key to the backend
- Toggle/Select/Input components produce correct values
- Validation rules (min password length, URL format, numeric ranges)
- Unsaved changes guard triggers on navigation
- Settings search (Ctrl+K) finds fields across all pages
- Highlight mechanism works after search navigation

**E2E tests (Playwright):**
- Full save-reload cycle for each Settings page (change value, save, reload, verify persistence)
- Settings search navigation: search for field, click result, verify correct page + highlight
- Multi-instance editors (Sonarr/Radarr instances) — add, edit, remove
- Language profile CRUD with all fields (mustContain, cutoff, HI/forced preference)
- Provider priority drag-and-drop reorder
- Config export/import round-trip
- Error states: invalid URLs, missing required fields, conflicting settings
- Advanced toggle: hidden fields appear when expanded

### 2.4 E2E test infrastructure

- Add missing `data-testid` attributes to components that lack them (theme toggle, language switcher, sidebar collapse, view toggle, pagination)
- Re-enable as many of the 58 skipped Playwright tests as possible
- Target: <10 legitimately skipped tests remaining

### 2.5 Performance baselines

- Enable and run `backend/tests/performance/` suite
- Establish baselines for: library scan (100/500/1000 series), provider search (parallel), translation batch, database queries
- Document acceptable thresholds for V1

---

## Phase 3: Feature Completion (Feature Freeze)

**Goal:** Everything that ships in V1 must be finished. No new features after this phase.

### 3.1 Translation: beta to stable

- Define quality acceptance criteria (BLEU score threshold, manual review of 50 sample translations)
- Fix known edge cases (context window overflow, glossary injection failures)
- Ensure all 5 backends work reliably (Ollama, DeepL, Google, LibreTranslate, OpenAI-compatible)
- Remove "Experimental" / "Beta" labels from UI
- Document limitations clearly (e.g. quality varies by model, anime-specific fine-tune recommended)

### 3.2 Bazarr migration

- Test `bazarr_migrator.py` end-to-end with real Bazarr database exports
- Document migration guide (what transfers, what doesn't, known limitations)
- Add migration validation step (pre-check before destructive import)

### 3.3 OpenAPI documentation

- Add YAML docstrings to all route functions
- Cover: request/response schemas, error codes, auth requirements
- Verify `/api/v1/openapi.json` serves complete, valid spec
- Consider adding Swagger UI or ReDoc endpoint for interactive docs

### 3.4 Remaining settings gaps

- All ⚠️ (wrong key) findings from gap analysis must be fixed in Phase 1
- Evaluate all ❌ (missing UI) fields — add UI or document as ENV-only
- Ensure every user-facing setting has a description in the UI

### 3.5 Security items: final disposition

Review all open/accepted security findings and make V1 decision:
- F-05 (Webhook middleware exemption) — accept or implement header check
- F-08 (SocketIO handshake unauthenticated) — accept or gate
- F-15 (Internal topology in config) — accept for self-hosted tool
- Document all accepted risks in a SECURITY.md for users

---

## Phase 4: Pentesting & Hardening (Release Candidate)

**Goal:** RC quality — no known data loss paths, no exploitable vulnerabilities.

### 4.1 Penetration testing

Full pentest before V1 release (Round 4), covering:

**Scope:**
- All API endpoints (authenticated + unauthenticated)
- WebSocket (SocketIO) attack surface
- File upload/download paths (subtitle upload, plugin install, ZIP extraction)
- Authentication & session management (brute force, session fixation, cookie theft)
- Provider interaction (SSRF via provider URLs, response injection)
- Translation pipeline (prompt injection via subtitle content)
- Config API (privilege escalation, sensitive data exposure)
- Docker container escape / privilege escalation

**Methodology:**
- Automated scanning (Burp Suite / ZAP)
- Manual testing of business logic flaws
- Dependency audit (pip-audit, npm audit — already in CI, verify clean)
- Compare against OWASP Top 10 (2021) checklist

**Deliverable:** Updated PENTEST_FINDINGS.md with all findings categorized, fix all CRITICAL/HIGH before release, document accepted MEDIUM/LOW.

### 4.2 Load testing

- Test with 500+ series library (real-world scale)
- Concurrent user simulation (5-10 simultaneous browser sessions)
- Provider search under load (20+ parallel searches)
- Translation queue saturation (50+ items)
- Database performance under load (SQLite + PostgreSQL)
- Document results and acceptable thresholds

### 4.3 Migration guide

- Upgrade path from any beta version (v0.13+) to V1
- Alembic migration chain validation (every beta → V1 in one step)
- Breaking changes documented with migration instructions
- Rollback procedure documented

### 4.4 API stability audit

- Catalog all API endpoints with request/response contracts
- Flag any breaking changes from beta → V1
- Add deprecation warnings where needed (minimum 1 minor version)
- Version the API contract (already at `/api/v1/`)

### 4.5 Error handling audit

- No silent error swallowing — every catch block must log or propagate
- User-facing errors must be actionable (not "Something went wrong")
- Database errors must not leak schema/connection details to API responses
- Translation failures must clearly indicate why (model unavailable, timeout, content too long)

### 4.6 Multi-arch Docker validation

- Build and test amd64 + arm64 images
- Verify all system dependencies available on both architectures (ffmpeg, mkvtoolnix, tesseract, hunspell)
- Run full test suite inside container on both architectures
- Health check verification on both

### 4.7 Release notes

- Consolidate 50 beta changelog entries into coherent V1 release notes
- Categorize by: Core Features, Integrations, Tools, Security, Performance
- Highlight migration notes for beta users
- Write "What's New in V1" summary for website/wiki

---

## Phase 5: Public Launch (Post-V1, incremental)

**Goal:** Build community and visibility. These items ship after V1.0.0 is tagged.

### 5.1 Distribution

- **Unraid Community App Template** — finalize XML template, submit to Community Applications
- **Docker Hub** — mirror GHCR images to Docker Hub for discoverability
- **AUR / Homebrew** — evaluate community package manager presence

### 5.2 Community

- **Discord server** — set up channels (support, feature-requests, dev, announcements)
- **GitHub Discussions** — enable for Q&A and feature requests
- **Issue templates** — bug report, feature request, security vulnerability

### 5.3 Marketing

- **SublarrWeb** — remove "Beta" badge, update to "V1 Stable", refresh feature list and screenshots
- **SublarrWiki** — version badge update, review all pages for accuracy
- **Video tutorial / demo** — 5-10 minute walkthrough of setup + key features
- **Reddit / self-hosted communities** — announcement posts

### 5.4 Ongoing

- **Dependabot** — keep dependencies current (already configured)
- **Claude Code PR reviews** — already configured in CI
- **Changelog discipline** — every PR gets a changelog entry

---

## Phase Dependencies

```
Phase 1 (Code Health)
  └─► Phase 2 (Test Coverage)
        ├─► Phase 3 (Feature Completion)  [can overlap with Phase 2]
        └─► Phase 4 (Pentesting & Hardening)
              └─► V1.0.0 Tag
                    └─► Phase 5 (Public Launch, incremental)
```

Phase 3 can start before Phase 2 is fully complete (feature work doesn't depend on 70% coverage), but Phase 4 (pentesting) requires Phase 2 and 3 to be done — you don't pentest moving targets.

---

## Success Criteria for V1.0.0

| Criterion | Threshold |
|-----------|-----------|
| Backend test coverage | >= 70% |
| Frontend test coverage | >= 70% |
| Settings E2E coverage | All 8 pages with save-reload cycle |
| Failing tests | 0 |
| Skipped E2E tests | < 10 (with documented reason) |
| Files >800 LOC | 0 (except config.py if justified) |
| Pentest CRITICAL/HIGH | 0 open |
| Pentest MEDIUM | All documented with accept/fix decision |
| OpenAPI coverage | 100% of public routes |
| Settings gap wrong keys | 0 |
| Load test (500 series) | No crashes, <2s page load |
| Migration (any beta to V1) | Tested, documented |
| Docker multi-arch | amd64 + arm64 verified |
| Known data loss paths | 0 |
