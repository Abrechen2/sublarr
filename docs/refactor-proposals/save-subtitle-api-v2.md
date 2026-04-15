# Refactor proposal — `save_subtitle` API v2

**Status:** Proposed
**Created:** 2026-04-15
**Trigger:** `0.51.13`–`0.51.14` regression where 5+ wanted-search Auto-sync calls per Sonarr-webhook batch were called with stale `.de.ass` paths while the actual file on disk was `.de.srt` — masked for years by `SyncUnavailableError` until `ffsubsync` shipped in `0.51.12-beta`.

## Problem

The current `providers.download_manager.save_subtitle(result, output_path) -> str` API has two latent failure modes the type system cannot prevent:

1. **`output_path` is a hint, not an authority.** When the caller-supplied extension does not match the actual subtitle format (provider lied, format detection ran, content sniffer disagreed), the function silently rewrites the path and writes the file under the corrected name. The caller has no idea unless they inspect the return value.
2. **The return value is `str`.** Python does not warn when a return value is discarded. Six of seven callers in the codebase ignored it before this fix. Static analysers do not flag it. The tests that *did* exercise the return-value flow lived next to tests that did not, and the divergence stayed invisible.

The bug only became externally visible once `ffsubsync` was bundled, because the previous "Auto-sync skipped: ffsubsync is not installed" message ate the `FileNotFoundError` for every wrong path.

## Short-term fix (shipped 0.51.14)

- All seven call sites now capture the return value (`saved_path = manager.save_subtitle(...)`).
- `_try_auto_sync` guards `os.path.isfile(subtitle_path)` and `os.path.isfile(video_path)`.
- `download_manager.save_subtitle` emits a `WARNING` log line whenever it rewrites an extension, so the production frequency of mismatches is observable.
- Regression test `TestSaveSubtitleReturnPathPropagated` reproduces the symptom and pins the fix.

## Long-term: API v2

The short-term fix relies on every caller doing the right thing. That is exactly the contract that broke in the first place. A proper fix removes the foot-gun by construction.

### Proposed signature

```python
@dataclass(frozen=True)
class SavedSubtitle:
    path: str           # absolute path the file ended up at
    format: str         # "ass" | "srt" | "vtt" — derived from result, never from input
    bytes_written: int

def save_subtitle_v2(
    result: SubtitleResult,
    *,
    dest_dir: str,
    base_name: str,        # filename WITHOUT extension, e.g. "Foo.de" or "Foo.de.forced"
    series_id: int | None = None,
) -> SavedSubtitle:
    """Save subtitle. Extension is derived from the actual content; caller
    cannot influence it. Returns a SavedSubtitle so the caller is forced
    to reach for `.path` rather than re-using a string they constructed
    earlier.
    """
```

Why this shape:

- **Caller never specifies extension.** Mismatch becomes structurally impossible.
- **`SavedSubtitle` is a small dataclass.** Discarding the return value is more obviously suspicious than throwing away a `str`. Plus `format`/`bytes_written` are useful telemetry the current API does not surface.
- **`dest_dir` + `base_name`** matches how callers actually think about the destination ("where do I put this file for episode X in language Y") and removes the ad-hoc `os.path.splitext` dance most call sites perform.

### Helper to extract

A second helper `get_subtitle_dest(file_path, language, *, forced=False) -> tuple[str, str]` should replace `get_output_path_for_lang` + `get_forced_output_path`. Returning `(dest_dir, base_name)` removes the "build then split" pattern entirely.

### Migration

1. Add `save_subtitle_v2` next to `save_subtitle`. New code uses v2.
2. Mark `save_subtitle` with `warnings.warn(..., DeprecationWarning, stacklevel=2)` and a docstring `.. deprecated::` block. Existing tests still pass (Python's `simplefilter("default")` does not error).
3. Migrate one caller per PR (7 callers + ~5 helper sites = ~12 changes). Each PR is small enough to review.
4. Once `git grep "save_subtitle("` returns only `save_subtitle_v2`, delete v1 and rename v2 → v1.

Estimated effort: ~1 day of focused work plus deploys between migrations.

### Why not other options

- **Mutate `result.saved_path` and return `None`.** Slightly better than current but still relies on caller remembering to read `result.saved_path`. Discarding `None` looks fine.
- **Wrap return value in a "must-use" sentinel that warns in `__del__`.** Pythonic but obscure; easy to break with `try/except` and noisy in tests.
- **`@must_use_result` mypy plugin.** Adds dependency, only catches at type-check time, not for ad-hoc `monkeypatch` callers.
- **Pre-compute extension outside `save_subtitle`.** Pushes the format-detection logic to every caller — same misuse surface, more places.

The "no extension in" + "dataclass out" combination is the only one that makes the failure mode structurally impossible.

## Risks / open questions

- The `dest_dir` + `base_name` split forces callers to know the destination directory exists. Today some callers rely on `save_subtitle` creating it. The v2 helper should still create the dir.
- Some callers rename the saved file afterwards (e.g. translation pipeline saves a `.en.srt`, then `_translate_external_ass` produces `.de.ass`). Make sure the migration touches both ends.
- `DuplicateSubtitleError.existing_path` already returns the duplicate's path — confirm v2 raises the same exception type so callers do not need a new handler.
