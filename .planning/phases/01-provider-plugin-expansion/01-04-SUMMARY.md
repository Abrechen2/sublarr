---
phase: 01-provider-plugin-expansion
plan: 04
subsystem: providers
tags: [gestdown, podnapisi, rest-api, xml-api, subtitle-provider, addic7ed-proxy, zip-extraction]

# Dependency graph
requires:
  - phase: 01-provider-plugin-expansion
    plan: 01
    provides: "SubtitleProvider ABC with declarative config_fields, @register_provider decorator, ProviderManager"
provides:
  - "GestdownProvider: REST API provider covering Addic7ed content via stable proxy"
  - "PodnapisiProvider: XML API provider with European language focus and ZIP extraction"
  - "Both providers registered via @register_provider with declarative class attributes"
affects: [01-06, frontend-settings, provider-health-dashboard]

# Tech tracking
tech-stack:
  added: []
  patterns: [rest-api-provider, xml-api-provider, language-code-mapping, zip-subtitle-extraction, lxml-fallback-to-stdlib]

key-files:
  created:
    - backend/providers/gestdown.py
    - backend/providers/podnapisi.py
  modified:
    - backend/providers/__init__.py

key-decisions:
  - "Gestdown covers both PROV-01 (Addic7ed) and PROV-03 (Gestdown) -- single provider, no duplication"
  - "Gestdown language mapping uses API fetch with hardcoded fallback for resilience"
  - "Podnapisi uses lxml for XML parsing with graceful fallback to stdlib xml.etree.ElementTree"
  - "Podnapisi language mapping uses hardcoded dict of 40+ ISO 639-1 to numeric code mappings"

patterns-established:
  - "REST API provider pattern: TVDB ID lookup with name search fallback, language-specific subtitle fetch"
  - "XML API provider pattern: XML response parsing with lxml/stdlib fallback, ZIP archive extraction"
  - "Language code mapping: provider-specific numeric/string codes mapped to ISO 639-1 via lookup dicts"
  - "HTTP 423 handling: wait 1s and retry once for locked responses (Gestdown-specific)"

# Metrics
duration: 8min
completed: 2026-02-15
---

# Phase 01 Plan 04: Gestdown + Podnapisi Provider Summary

**Two REST/XML-based subtitle providers: Gestdown (Addic7ed proxy, TV shows, TVDB lookup) and Podnapisi (XML API, European languages, ZIP extraction)**

## Performance

- **Duration:** 8 min
- **Started:** 2026-02-15T12:29:51Z
- **Completed:** 2026-02-15T12:38:14Z
- **Tasks:** 2
- **Files modified:** 3 (2 created, 1 modified)

## Accomplishments

- Implemented GestdownProvider: REST API-based Addic7ed proxy with TVDB ID + name search, language ID mapping via API with fallback, HTTP 423 retry logic, and direct file download
- Implemented PodnapisiProvider: XML search API with ISO 639-1 to numeric language code mapping (40+ languages), lxml with stdlib fallback, and ZIP archive extraction for downloads
- Both providers registered via @register_provider with config_fields=[], rate_limit=(30,60), and all required class attributes
- Added import hooks for both providers in ProviderManager._init_providers

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement Gestdown provider (Addic7ed proxy via REST API)** - `5229f07` (feat)
2. **Task 2: Implement Podnapisi provider (XML API)** - `b4548b5` (feat, included in concurrent agent's commit)

## Files Created/Modified

- `backend/providers/gestdown.py` - GestdownProvider: REST API proxy for Addic7ed subtitles, TVDB ID/name show lookup, language API with cache, HTTP 429/423 handling
- `backend/providers/podnapisi.py` - PodnapisiProvider: XML search API with sXML=1 param, 40+ language mappings, lxml/stdlib XML parsing, ZIP download extraction
- `backend/providers/__init__.py` - Added gestdown and podnapisi import blocks in _init_providers()

## Decisions Made

- Gestdown covers both PROV-01 (Addic7ed) and PROV-03 (Gestdown) as a single provider -- Gestdown IS the Addic7ed proxy, no need for separate implementations
- Gestdown language mapping fetched from /languages API on first use and cached; hardcoded fallback for resilience when API is unavailable
- Podnapisi uses lxml.etree.fromstring() when available, falls back to stdlib xml.etree.ElementTree with a debug warning about degraded performance
- Both providers use conservative rate_limit=(30, 60) as specified in the plan

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- Task 2 (Podnapisi) was committed by a concurrent agent as part of commit `b4548b5` because the file existed on the filesystem when that agent staged its changes. The implementation was authored by this agent; only the commit attribution differs.

## User Setup Required

None - both providers require no authentication or API keys.

## Next Phase Readiness

- Two new providers ready for subtitle search: Gestdown (TV shows via Addic7ed content) and Podnapisi (broad European language coverage)
- Both follow established provider patterns and are compatible with ProviderManager's parallel search, circuit breaker, and rate limiting
- All 24 existing unit tests continue to pass
- Providers will appear in /api/v1/providers status when enabled

## Self-Check: PASSED

- All 3 key files verified present
- Task 1 commit verified (5229f07)
- Task 2 content verified in commit (b4548b5)
- 24/24 unit tests passing
- Both providers instantiate correctly with expected attributes
- Both providers register in _PROVIDER_CLASSES

---
*Phase: 01-provider-plugin-expansion*
*Completed: 2026-02-15*
