---
phase: 4D
plan: features
subsystem: download-tracking, post-processing
tags: [history, upgrade-chain, post-download, shell-hook, config]
dependency_graph:
  requires: [db/models/providers.SubtitleDownload.upgraded_from_id, post_download.py, config.py]
  provides: [episode-history-upgraded_from_id, post-processing-enabled-guard, media_type-variable, path-alias]
  affects: [routes/history, providers/download_manager.py]
tech_stack:
  added: []
  patterns: [TDD, repository-pattern]
key_files:
  created:
    - backend/tests/test_routes_subtitles.py
  modified:
    - backend/db/repositories/cache.py
    - backend/post_download.py
    - backend/config.py
    - backend/providers/download_manager.py
    - backend/tests/test_upgrade_chain.py
    - backend/tests/test_post_download.py
decisions:
  - "post_processing_enabled defaults to False (opt-in) matching translation_enabled pattern"
  - "enabled param propagated from settings at call site; function also accepts direct override for testing"
  - "{path} alias substituted before {subtitle_path} would be redundant — order in replace chain does not matter since they map to same value"
metrics:
  duration: "~20 minutes"
  completed: 2026-04-03
  tasks_completed: 2/2
  tests_added: 4
  tests_passing: 12
---

# Phase 4D Plan Features Summary

**One-liner:** Closed two Bazarr-parity gaps — `upgraded_from_id` now appears in per-episode history responses, and the post-download shell hook gained `{media_type}`, `{path}` alias, and a `post_processing_enabled` boolean guard.

## What Was Built

### Task 1 — `upgraded_from_id` in episode history

`get_episode_history()` in `backend/db/repositories/cache.py` built its SELECT with an explicit column list that omitted `upgraded_from_id`. Added the column to the SELECT and the result dict so `GET /api/v1/episodes/<id>/history` entries now include `"upgraded_from_id": <int|null>`.

### Task 2 — Post-download shell hook enhancements

Three gaps closed in one commit:

1. **`{path}` alias** — `{path}` now expands to the same value as `{subtitle_path}`, providing Bazarr script compatibility.
2. **`{media_type}` variable** — expands to `"series"` when `series_id is not None`, `"movie"` otherwise. `run_post_download_command` gained `media_type: str = ""` parameter; `download_manager.py` derives and passes the value.
3. **`post_processing_enabled` guard** — new `bool = False` setting in `config.py`; `run_post_download_command` gained `enabled: bool = True` parameter; `download_manager.py` reads `post_processing_enabled` from settings and passes it as `enabled`. When `False`, the function returns immediately without spawning a subprocess.

## Commits

| Hash | Message |
|------|---------|
| `61082c6` | feat: expose upgraded_from_id in episode history response |
| `bcbb579` | feat: add {media_type}/{path} variables and post_processing_enabled guard to shell hook |

## Test Results

- **Before:** 8 tests across 2 files
- **After:** 12 tests across 2 files (4 new TDD tests added)
- **Full suite:** 1265 passed, 3 skipped, 3 errors (all 3 errors pre-existing `mocker` fixture issue unrelated to this plan)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing] Fixed ruff import ordering in test files**
- **Found during:** Task 2 ruff check
- **Issue:** New tests used `import subprocess` + `from post_download import ...` blocks that ruff flagged as unsorted (I001). Additionally `tests/test_routes_subtitles.py` had a pre-existing I001 violation that was caught by the full-directory ruff scan.
- **Fix:** Ran `ruff check --fix` then `ruff format` on affected files.
- **Files modified:** `backend/tests/test_post_download.py`, `backend/tests/test_routes_subtitles.py`, `backend/config.py`
- **Note:** `test_routes_subtitles.py` was a new file from the remote (pulled during rebase) — not authored in this plan; fixing its pre-existing lint violation was required to keep `ruff check .` clean.

**2. [Rule 3 - Blocking] Fixed test mock for `get_episode_history`**
- **Found during:** Task 1 RED phase
- **Issue:** The plan's test mock used `mock_session.execute.return_value.all.return_value = [mock_row]` which caused the second `execute().all()` call (for job_rows) to also return `[mock_row]`, triggering a `TypeError` in the sort because `MagicMock` datetime objects can't be compared with real `datetime`.
- **Fix:** Used `side_effect = [[mock_row], []]` so the first call returns download rows and the second returns an empty list.
- **Files modified:** `backend/tests/test_upgrade_chain.py`

## Self-Check: PASSED

Files verified:
- `backend/db/repositories/cache.py` — `upgraded_from_id` in SELECT and result dict: confirmed
- `backend/post_download.py` — `media_type`, `path` alias, `enabled` param: confirmed
- `backend/config.py` — `post_processing_enabled: bool = False`: confirmed
- `backend/providers/download_manager.py` — `_pd_enabled`, `_pd_media_type` passed: confirmed

Commits verified:
- `61082c6` feat: expose upgraded_from_id in episode history response
- `bcbb579` feat: add {media_type}/{path} variables and post_processing_enabled guard to shell hook
