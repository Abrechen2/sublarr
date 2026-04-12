# Sublarr — Settings Gap Analysis

Complete analysis of all settings: Backend `config.py` vs. UI Settings pages.

**Method:** Every field in `backend/config.py` (Pydantic Settings) compared against actual config key usage in all frontend Settings TSX files.

**Last updated:** 2026-04-12 (v0.50.1-beta)

---

## Summary

| Metric | Count |
|--------|-------|
| Total backend config fields | 165 |
| Fields with UI | 162 |
| Fields missing from UI | 3 |
| Wrong config keys (bugs) | 0 |
| Coverage | **98.2%** |

---

## Missing Fields (no UI)

These 3 backend config fields have no corresponding UI element:

| Field | Type | Default | Category | Recommendation |
|-------|------|---------|----------|----------------|
| `auto_process_common_fixes_config_json` | str | "" | Post-Processing | JSON config for which common fixes to apply. Complex structure — consider a checkbox-based UI or leave as ENV-only. |
| `scan_yield_ms` | int | 0 | Scanning | Sleep between series to yield CPU. Expert/performance tuning only — acceptable as ENV-only. |
| `provider_rate_limit_throttle_minutes` | int | 60 | Providers | Extended throttle on HTTP 429. Could be added to Provider Advanced section, but low user demand. |

**Assessment:** All 3 missing fields are expert-level tuning parameters. None are user-facing settings that would cause confusion. Acceptable to leave as ENV-only for V1.

---

## Previously Fixed (v0.31–v0.50)

The original analysis from 2026-03-21 identified **14 wrong config keys** and **~60 missing UI fields**. All have been resolved:

- All wrong key names corrected (AutomationSettings, GeneralSettings)
- AniDB settings page added (4 fields)
- Remux settings page added (4 fields)
- Standalone settings expanded (4 fields)
- Subtitle naming page added (4 fields)
- Quiet hours added (4 fields)
- Interface preferences added (5 fields)
- Security settings expanded (4 fields)
- Backup retention settings added (4 fields)
- Disk monitoring added (2 fields)
- Scan ignore patterns added (3 fields)
- Score thresholds per language added
- Provider advanced settings expanded (~15 fields)
- Post-processing pipeline fully configurable (~8 fields)
- Translation advanced settings expanded (~5 fields)

---

*Analysis based on complete comparison of `backend/config.py` (165 fields) against all `frontend/src/pages/Settings/**/*.tsx` files.*
