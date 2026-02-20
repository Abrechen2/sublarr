# Phase 6: Forced/Signs Subtitle Management - Research

**Researched:** 2026-02-15
**Domain:** Forced/signs subtitle detection, tracking, search, and UI integration
**Confidence:** HIGH

## Summary

Forced/signs subtitle management requires changes across all layers of Sublarr: database schema, detection logic, provider search, translation pipeline, and frontend UI. The core challenge is treating forced subtitles as a **separate category** alongside regular subtitles -- a file can have both a full dialog subtitle AND a forced/signs-only subtitle, and both need independent tracking.

The existing codebase already has strong foundations for this feature. `SubtitleResult.forced` exists as a field (never populated). `ass_utils.classify_styles()` already distinguishes dialog from signs/songs styles. The `run_ffprobe()` function already returns disposition data including the `forced` flag (never read). Language profiles already support per-series configuration. The wanted system already tracks items per-file-per-language. The main work is extending these existing patterns rather than building new architecture.

Provider support for forced-specific search varies: OpenSubtitles has `foreign_parts_only` as a response attribute (can filter client-side), SubDL has no forced parameter, and AnimeTosho/Jimaku have no explicit forced flag. This means Sublarr's detection heuristics (ffprobe disposition, ASS style analysis, filename patterns) are more important than provider-side filtering for reliable forced subtitle identification.

**Primary recommendation:** Add `subtitle_type` enum field (`full`/`forced`/`signs`) to the data model, extend detection in `ass_utils.py` using ffprobe disposition + filename patterns + ASS style heuristics, add `forced_preference` field to language profiles, and keep forced subtitles as a parallel track in the wanted system (separate wanted items per subtitle_type).

## Standard Stack

### Core (already in project)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pysubs2 | existing | ASS/SRT parsing for style classification | Already used for dialog/signs split |
| ffprobe (ffmpeg) | existing | Embedded stream metadata + disposition flags | Already used, disposition data available but unread |
| SQLite | existing | Schema extension for subtitle_type tracking | Already WAL-mode with migration support |
| Flask | existing | API endpoints for forced preferences | Blueprint pattern established |
| React/TanStack Query | existing | Frontend forced preference UI | Pattern established in Settings/SeriesDetail |

### Supporting (no new dependencies)

No new Python or Node packages are needed. All forced/signs detection can be built using existing `pysubs2`, `re` (regex), and `subprocess` (ffprobe) capabilities. The ASS style classification logic in `ass_utils.py` already provides the foundation for signs detection.

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Custom ASS heuristics | MediaInfo CLI for forced flag | MediaInfo adds dependency; ffprobe already provides disposition data |
| Per-file subtitle_type tracking | Tag system (multiple tags per subtitle) | Tags are more flexible but overkill; forced/full is a simple binary per subtitle file |
| Forced as separate language variant (Bazarr approach: "en:forced") | Separate subtitle_type field | Bazarr's approach conflates language and type; a dedicated field is cleaner for Sublarr's data model |

## Architecture Patterns

### Recommended Data Model Extension

```
# subtitle_type enum values
SUBTITLE_TYPES = "full", "forced", "signs"

# Language profile extension
language_profiles table:
  + forced_preference TEXT DEFAULT 'disabled'   -- 'disabled' | 'separate' | 'auto'

# Wanted items extension
wanted_items table:
  + subtitle_type TEXT DEFAULT 'full'           -- 'full' | 'forced'

# Subtitle downloads tracking
subtitle_downloads table:
  + subtitle_type TEXT DEFAULT 'full'           -- 'full' | 'forced' | 'signs'
```

### Pattern 1: Subtitle Type Detection (Multi-Signal)

**What:** Determine if a subtitle file/stream is forced/signs using multiple detection signals with confidence scoring.
**When to use:** During scanning (wanted_scanner), import, and manual analysis.

```python
# Priority-ordered detection signals:
# 1. ffprobe disposition forced=1 (highest confidence)
# 2. Filename pattern: ".forced." or ".signs." in name
# 3. Stream title: "forced", "signs", "signs/songs" in title
# 4. ASS style analysis: ALL styles are signs-type (no dialog styles)
# 5. Line count heuristic: very few lines (<50) with position tags

def detect_subtitle_type(stream_info=None, file_path=None, ass_content=None):
    """Returns ('full' | 'forced' | 'signs', confidence: float)"""
    signals = []

    # Signal 1: ffprobe disposition
    if stream_info:
        disposition = stream_info.get("disposition", {})
        if disposition.get("forced", 0) == 1:
            signals.append(("forced", 1.0))

    # Signal 2: Filename pattern
    if file_path:
        name_lower = os.path.basename(file_path).lower()
        if ".forced." in name_lower:
            signals.append(("forced", 0.9))
        if ".signs." in name_lower or ".sign." in name_lower:
            signals.append(("signs", 0.9))

    # Signal 3: Stream title
    if stream_info:
        title = (stream_info.get("tags", {}).get("title", "") or "").lower()
        if "forced" in title:
            signals.append(("forced", 0.8))
        if "sign" in title or "song" in title:
            signals.append(("signs", 0.8))

    # Signal 4: ASS all-signs heuristic
    if ass_content:
        dialog_styles, signs_styles = classify_styles(ass_content)
        if signs_styles and not dialog_styles:
            signals.append(("signs", 0.7))

    # Determine type from signals
    if not signals:
        return ("full", 1.0)
    # ... aggregate and return
```

### Pattern 2: Forced Subtitle File Naming

**What:** External forced subtitle files use the media server standard naming convention.
**When to use:** When saving downloaded or detected forced subtitles to disk.

```python
# Standard forced subtitle naming (Plex/Jellyfin/Emby compatible):
# MovieName.en.forced.ass
# MovieName.en.forced.srt
# SeriesName S01E01.en.forced.ass

def get_forced_output_path(mkv_path, fmt="ass", target_language=None):
    """Get output path for a forced/signs subtitle."""
    settings = get_settings()
    lang = target_language or settings.target_language
    base = os.path.splitext(mkv_path)[0]
    return f"{base}.{lang}.forced.{fmt}"
```

### Pattern 3: Parallel Wanted Tracking

**What:** Forced subtitles are tracked as separate wanted items alongside full subtitles.
**When to use:** In the scanner and wanted system.

```python
# A single file can have TWO wanted items:
# 1. wanted_item(file_path, subtitle_type='full', target_language='de')
# 2. wanted_item(file_path, subtitle_type='forced', target_language='de')
#
# The wanted_items table already supports this via the target_language
# uniqueness constraint. Adding subtitle_type to the uniqueness check
# enables parallel tracking.

# In wanted_scanner._scan_sonarr_series:
for target_lang, target_name in zip(target_languages, target_language_names):
    # Check full subtitle
    _check_and_upsert_wanted(file_path, target_lang, subtitle_type="full", ...)

    # Check forced subtitle (if profile enables it)
    if forced_preference in ("separate", "auto"):
        _check_and_upsert_wanted(file_path, target_lang, subtitle_type="forced", ...)
```

### Pattern 4: Provider Forced Search

**What:** Pass forced flag to providers that support it; filter results client-side for others.
**When to use:** When searching for forced-only subtitles.

```python
# VideoQuery extension:
@dataclass
class VideoQuery:
    # ... existing fields ...
    forced_only: bool = False  # Search for forced/signs subtitles only

# OpenSubtitles: filter on foreign_parts_only attribute in response
# SubDL: no forced parameter -- rely on result metadata/filename
# AnimeTosho: filter by filename patterns (.signs., .forced.)
# All providers: post-filter results by SubtitleResult.forced flag
```

### Anti-Patterns to Avoid

- **Forced as a language variant (e.g., "en:forced"):** This conflates two orthogonal dimensions (language and subtitle type). Use separate fields instead. Bazarr does this and it creates complexity in every language comparison.
- **Single detection signal:** Never rely on only ffprobe disposition OR only filename pattern. Many MKV files have incorrect disposition flags. Use multi-signal detection with confidence scoring.
- **Forced detection on every scan:** Running ASS style analysis on every file during scanning is too slow. Cache detection results in the ffprobe_cache table or a new detection_cache.
- **Modifying classify_styles to return forced status:** Keep `classify_styles()` focused on dialog/signs classification for translation. Add a separate `detect_subtitle_type()` function for the forced detection concern.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| ASS file parsing | Custom ASS parser | `pysubs2` (already used) | ASS format has many edge cases; pysubs2 handles them |
| ffprobe JSON parsing | Manual stream parsing | Existing `run_ffprobe()` + dictionary access | ffprobe output is well-structured JSON, just need to read `disposition.forced` |
| File naming convention | Custom naming scheme | Plex/Jellyfin standard `.lang.forced.ext` | Media servers expect this format; custom naming breaks library refresh |
| Style classification | New signs detector | Extend `classify_styles()` patterns | SIGNS_PATTERNS and POS_MOVE_RE already capture most signs/songs styles |

**Key insight:** The existing codebase already does 80% of what's needed. The `forced` field exists on SubtitleResult, classify_styles separates dialog from signs, ffprobe data includes disposition, and the wanted system tracks per-file-per-language. The work is wiring these together, not building from scratch.

## Common Pitfalls

### Pitfall 1: False Positive Forced Detection on Short Subtitle Files
**What goes wrong:** Small subtitle files (few lines) get incorrectly classified as "forced" because they have position tags and low line counts, when actually they're just incomplete or short-episode subtitles.
**Why it happens:** Line count alone is not a reliable indicator. Some episodes genuinely have very few dialog lines.
**How to avoid:** Use multi-signal detection. A subtitle is only "forced" if at least 2 signals agree (e.g., disposition flag + title match, or filename pattern + all-signs styles). Never classify based on line count alone.
**Warning signs:** High percentage of files incorrectly marked as forced in the UI.

### Pitfall 2: MKV Disposition Flags Are Often Wrong
**What goes wrong:** Many MKV files have incorrect or missing `disposition.forced` flags on subtitle streams. Some muxers don't set it, others set it on full subtitles.
**Why it happens:** No enforcement of correct disposition flags during muxing. Fansubbers rarely set dispositions correctly.
**How to avoid:** Treat ffprobe disposition as ONE signal among several, not the sole truth. Always cross-reference with title and filename patterns. Use confidence scoring.
**Warning signs:** Users report full subtitles being detected as forced.

### Pitfall 3: Wanted Table Uniqueness with subtitle_type
**What goes wrong:** The current wanted_items uniqueness is based on `file_path + target_language`. Adding subtitle_type creates duplicate items if the migration isn't careful.
**Why it happens:** Existing items have no subtitle_type (NULL or 'full'). New scans will try to insert forced items that might conflict with existing rows.
**How to avoid:** Migration must set all existing items to `subtitle_type='full'` before adding the column to the uniqueness constraint. Use `ALTER TABLE` followed by careful constraint update.
**Warning signs:** SQLite constraint violations during scan after upgrade.

### Pitfall 4: Signs Detection vs Forced Detection Confusion
**What goes wrong:** Developers conflate "signs/songs" ASS styles (used in translation to keep original) with "forced subtitles" (a separate subtitle file containing only foreign-language dialog and signs).
**Why it happens:** Both concepts relate to non-dialog subtitle content, but they serve different purposes.
**How to avoid:** Clear terminology: "Signs styles" = ASS style classification within a FULL subtitle file (affects translation). "Forced subtitle" = an entire subtitle FILE that only contains foreign speech/signs. A forced subtitle file may itself contain multiple styles.
**Warning signs:** Code that tries to use classify_styles output to determine if a subtitle file is "forced".

### Pitfall 5: Double-Searching Providers
**What goes wrong:** For each file, the scanner checks both full and forced wanted items, causing twice as many provider searches.
**Why it happens:** Naive implementation searches providers separately for full and forced subtitles.
**How to avoid:** Search providers ONCE, then classify results into full vs. forced categories. Use `SubtitleResult.forced` flag from providers plus client-side heuristics (filename patterns) to split results.
**Warning signs:** Provider rate limits being hit twice as fast; search times doubling.

### Pitfall 6: Forced Subtitle Output Path Conflicts
**What goes wrong:** When saving forced subtitles, the path `movie.en.forced.ass` might conflict with existing `movie.en.ass` detection logic.
**Why it happens:** `detect_existing_target_for_lang()` uses `_get_language_tags()` to build patterns like `.en.ass`, but doesn't account for `.en.forced.ass`.
**How to avoid:** Update `detect_existing_target_for_lang()` to also check for `.{lang}.forced.{fmt}` patterns, and return metadata about which type was found. This should be one of the first changes since it affects the scanner.
**Warning signs:** Forced subtitles not detected during scanning; same file repeatedly appearing in wanted list.

## Code Examples

### Reading ffprobe Disposition Data (Verified: ffprobe always includes disposition in -show_streams)

```python
# Current ffprobe output already includes disposition:
# {
#   "streams": [{
#     "index": 2,
#     "codec_type": "subtitle",
#     "codec_name": "ass",
#     "disposition": {
#       "default": 0,
#       "forced": 1,        # <-- THIS IS THE KEY FLAG
#       "hearing_impaired": 0,
#       ...
#     },
#     "tags": {
#       "language": "eng",
#       "title": "Signs/Songs"
#     }
#   }]
# }

def is_forced_stream(stream: dict) -> bool:
    """Check if a subtitle stream has the forced disposition flag."""
    disposition = stream.get("disposition", {})
    return disposition.get("forced", 0) == 1
```

### Detecting Forced External Subtitles by Filename

```python
import re

# Standard naming: movie.en.forced.ass, movie.eng.forced.srt
FORCED_FILENAME_RE = re.compile(
    r'\.(?:forced|signs?|foreign)\.(?:ass|srt|ssa|vtt)$',
    re.IGNORECASE,
)

def is_forced_external_sub(file_path: str) -> bool:
    """Check if an external subtitle file is a forced/signs subtitle by name."""
    return bool(FORCED_FILENAME_RE.search(os.path.basename(file_path)))
```

### OpenSubtitles foreign_parts_only Response Filtering

```python
# Source: OpenSubtitles REST API docs (stoplight.io)
# The foreign_parts_only field is in response attributes, not a search parameter.
# Filter client-side after receiving results.

def search(self, query: VideoQuery) -> list[SubtitleResult]:
    # ... existing search logic ...

    for item in data.get("data", []):
        attrs = item.get("attributes", {})
        is_forced = attrs.get("foreign_parts_only", False)

        # If searching for forced only, skip non-forced results
        if query.forced_only and not is_forced:
            continue
        # If searching for full only, skip forced results
        if not query.forced_only and is_forced:
            continue

        result = SubtitleResult(
            # ... existing fields ...
            forced=is_forced,
        )
        results.append(result)
```

### Language Profile Forced Preference (Database)

```python
# Migration: add forced_preference to language_profiles
# In db/__init__.py _run_migrations():

cursor = conn.execute("PRAGMA table_info(language_profiles)")
lp_columns = {row[1] for row in cursor.fetchall()}
if "forced_preference" not in lp_columns:
    conn.execute(
        "ALTER TABLE language_profiles ADD COLUMN forced_preference TEXT DEFAULT 'disabled'"
    )
    logger.info("Added forced_preference column to language_profiles")
```

### Wanted Item with subtitle_type

```python
# Migration: add subtitle_type to wanted_items
# In db/__init__.py _run_migrations():

cursor = conn.execute("PRAGMA table_info(wanted_items)")
wi_columns = {row[1] for row in cursor.fetchall()}
if "subtitle_type" not in wi_columns:
    conn.execute(
        "ALTER TABLE wanted_items ADD COLUMN subtitle_type TEXT DEFAULT 'full'"
    )
    logger.info("Added subtitle_type column to wanted_items")

# Update upsert_wanted_item to include subtitle_type in uniqueness check:
# Match on file_path + target_language + subtitle_type
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Forced subs as language variant ("en:forced") | Separate subtitle_type field | Bazarr still uses old approach | Cleaner data model, avoids language comparison issues |
| Only ffprobe disposition for detection | Multi-signal detection (disposition + title + filename + ASS analysis) | Industry best practice | Much higher accuracy on real-world files |
| No forced tracking | Parallel wanted items per subtitle_type | This phase | Users can manage forced subs independently |

**Industry conventions:**
- Plex: `filename.lang.forced.ext` naming, recognizes disposition flags
- Jellyfin: `filename.lang.forced.ext` naming, reads disposition from MKV
- Emby: Same as Jellyfin
- Kodi: `filename.lang.forced.ext` naming
- Bazarr: Tracks forced as language variant, searches separately per provider

## Open Questions

1. **Should forced subtitles be translatable?**
   - What we know: Forced subs typically contain foreign-language speech and signs. Translation makes sense for the foreign speech parts but not for location signs that are visual.
   - What's unclear: Whether users want forced subs translated or just downloaded in their target language.
   - Recommendation: Start with "download forced subs in target language" (no translation). Add translation support later if requested. The existing ASS signs/songs classification can be repurposed.

2. **How to handle "auto" forced_preference?**
   - What we know: "auto" should mean "detect and manage forced subs automatically when they exist."
   - What's unclear: What exactly "auto" does when no forced subs are detected -- should it create wanted items for forced subs?
   - Recommendation: "auto" means: detect forced subs if they exist (during scan), download them if found during provider search, but do NOT create dedicated wanted items. "separate" means: always create forced wanted items and actively search for forced subs.

3. **Database uniqueness constraint update strategy**
   - What we know: Current uniqueness is `file_path + target_language`. Needs to become `file_path + target_language + subtitle_type`.
   - What's unclear: Whether to use a UNIQUE index or handle it in application code.
   - Recommendation: Use application-level uniqueness check (already done in `upsert_wanted_item`). SQLite doesn't support modifying constraints on existing tables without recreating the table, which is risky. The Python code already handles deduplication.

4. **Provider search efficiency for forced subtitles**
   - What we know: Searching providers twice (once for full, once for forced) doubles API calls.
   - What's unclear: How many providers actually return forced results separately vs mixed in with full results.
   - Recommendation: Search ONCE per file, then classify results. For OpenSubtitles, read `foreign_parts_only` from response. For others, use filename pattern matching on results. Only do a dedicated forced-only search if the first search yielded no forced results AND the profile demands them.

## Sources

### Primary (HIGH confidence)
- **Sublarr codebase analysis** -- `base.py` (SubtitleResult.forced field), `ass_utils.py` (classify_styles, run_ffprobe), `db/__init__.py` (schema), `config.py` (Settings), `translator.py` (pipeline), `providers/__init__.py` (ProviderManager), `wanted_scanner.py`, `wanted_search.py`
- **ffprobe documentation** (https://ffmpeg.org/ffprobe.html) -- disposition flags include `forced` (0/1) in JSON output

### Secondary (MEDIUM confidence)
- **OpenSubtitles REST API** (https://opensubtitles.stoplight.io/docs/opensubtitles-api/) -- `foreign_parts_only` attribute in subtitle search response, usable as order_by field
- **SubDL API docs** (https://subdl.com/api-doc) -- confirmed NO forced subtitle search parameter
- **Plex subtitle naming** (https://support.plex.tv/articles/200471133-adding-local-subtitles-to-your-media/) -- `.lang.forced.ext` standard
- **Jellyfin subtitle naming** (https://github.com/jellyfin/jellyfin/issues/7057) -- same `.lang.forced.ext` convention
- **Bazarr forced subs** (https://wiki.bazarr.media/Additional-Configuration/Settings/) -- forced as language variant, three modes (false/true/both)
- **Bazarr source** (GitHub morpheus65535/bazarr) -- tracks forced via "lang:forced" string pattern in language fields

### Tertiary (LOW confidence)
- **ffprobe disposition accuracy** -- multiple forum reports of incorrect forced flags in MKV files (https://trac.ffmpeg.org/ticket/9018), needs multi-signal approach

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, extending existing patterns
- Architecture: HIGH -- clear data model extension, patterns directly derived from codebase analysis
- Pitfalls: HIGH -- based on direct codebase analysis and Bazarr community issues
- Provider support: MEDIUM -- OpenSubtitles `foreign_parts_only` verified via API docs, SubDL confirmed no support, other providers unverified

**Research date:** 2026-02-15
**Valid until:** 2026-04-15 (90 days -- stable domain, no fast-moving dependencies)
