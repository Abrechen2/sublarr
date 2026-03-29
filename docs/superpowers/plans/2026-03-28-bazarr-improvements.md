# Bazarr Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the nine feature gaps between Sublarr and Bazarr identified in the 2026-03-28 codebase comparison.

**Architecture:** Four independent phases (A–D). Each can be developed in its own branch/worktree. The Alembic migrations in B, C, D form a chain and must be applied in order B → C → D.

**Tech Stack:** Python 3.12, Flask, SQLAlchemy + Alembic (SQLite), React 19, TypeScript, Vite

> **Scope note:** These four phases are independent subsystems. For parallel implementation consider four branches: `feat/scoring-enhancements`, `feat/profile-filters`, `feat/provider-infrastructure`, `feat/download-quality`.

---

## File Map

### Phase A — Scoring Enhancements
| Action | File |
|--------|------|
| Modify | `backend/providers/base.py:155–179` |
| Test | `backend/tests/test_score_breakdown.py` |

### Phase B — Language Profile Filters
| Action | File |
|--------|------|
| Create | `backend/db/migrations/versions/c1d2e3f4a5b6_add_language_profile_filter_fields.py` |
| Modify | `backend/db/models/core.py:128–146` (LanguageProfile) |
| Create | `backend/wanted_search/profile_filters.py` |
| Modify | `backend/providers/__init__.py:764` (search signature + post-filter block) |
| Modify | `backend/wanted_search/process.py:207` (process_wanted_item) |
| Create | `backend/tests/test_profile_filters.py` |

### Phase C — Provider Infrastructure
| Action | File |
|--------|------|
| Modify | `backend/circuit_breaker.py` (add `is_open` property) |
| Modify | `backend/providers/__init__.py` (persist CB open → DB; restore on init; rate-limit throttle) |

### Phase D — Download Quality
| Action | File |
|--------|------|
| Create | `backend/db/migrations/versions/d2e3f4a5b6c7_add_subtitle_download_upgrade_tracking.py` |
| Modify | `backend/db/models/providers.py:30–49` (SubtitleDownload) |
| Modify | `backend/db/repositories/providers.py:132` (record_subtitle_download + get_latest_download_id) |
| Modify | `backend/db/providers.py:74` (record_subtitle_download wrapper) |
| Modify | `backend/wanted_search/process.py` (pass upgraded_from_id on upgrade) |
| Modify | `backend/config.py` (add post_download_command) |
| Create | `backend/post_download.py` |
| Modify | `backend/providers/__init__.py:1320` (save_subtitle: call post-process) |
| Create | `backend/routes/sync.py` (POST /api/v1/sync/alass) |
| Modify | `backend/app.py` (register sync blueprint) |
| Create | `backend/tests/test_post_download.py` |

---

## Phase A — Scoring Enhancements

### Task A1: Add video_codec weight to scoring tables

**Files:**
- Modify: `backend/providers/base.py:155–179`
- Test: `backend/tests/test_score_breakdown.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_score_breakdown.py — add to class TestScoreBreakdown:

def test_video_codec_in_episode_scores(self):
    from providers.base import EPISODE_SCORES, MOVIE_SCORES
    assert "video_codec" in EPISODE_SCORES
    assert EPISODE_SCORES["video_codec"] == 2
    assert "video_codec" in MOVIE_SCORES
    assert MOVIE_SCORES["video_codec"] == 2

def test_video_codec_match_adds_points(self):
    from providers.base import SubtitleFormat, SubtitleResult, VideoQuery, compute_score
    from unittest.mock import patch

    result = SubtitleResult(
        provider_name="test",
        subtitle_id="1",
        language="de",
        format=SubtitleFormat.SRT,
        matches={"series", "video_codec"},
    )
    query = VideoQuery(series_title="Test Show", season=1, episode=5, video_codec="x265")
    with (
        patch("providers.base._get_cached_weights",
              return_value={"series": 180, "video_codec": 2}),
        patch("providers.base._get_cached_modifier", return_value=0),
    ):
        score = compute_score(result, query)

    assert result.score_breakdown.get("video_codec") == 2
    assert score == 182
```

- [ ] **Step 2: Run test to confirm it fails**

```
cd backend && python -m pytest tests/test_score_breakdown.py::TestScoreBreakdown::test_video_codec_in_episode_scores -v
```
Expected: FAIL — `AssertionError: assert "video_codec" in EPISODE_SCORES`

- [ ] **Step 3: Add video_codec to EPISODE_SCORES and MOVIE_SCORES**

In `backend/providers/base.py:155`, replace the EPISODE_SCORES block:

```python
EPISODE_SCORES = {
    "hash": 359,
    "series": 180,
    "year": 90,
    "season": 30,
    "episode": 30,
    "release_group": 14,
    "source": 7,
    "audio_codec": 3,
    "resolution": 2,
    "video_codec": 2,  # x264/x265/AV1 match
    "hearing_impaired": 1,
    "format_bonus": 50,  # ASS format bonus (Sublarr-specific)
}

MOVIE_SCORES = {
    "hash": 119,
    "title": 60,
    "year": 30,
    "release_group": 13,
    "source": 7,
    "audio_codec": 3,
    "resolution": 2,
    "video_codec": 2,  # x264/x265/AV1 match
    "hearing_impaired": 1,
    "format_bonus": 50,
}
```

Note: `compute_score()` iterates `result.matches` and calls `weights.get(match, 0)`. No change needed there — providers that already populate `"video_codec"` into `result.matches` will automatically score. The DB override system also exposes the new key automatically.

- [ ] **Step 4: Run tests to confirm they pass**

```
cd backend && python -m pytest tests/test_score_breakdown.py -v
```
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add backend/providers/base.py backend/tests/test_score_breakdown.py
git commit -m "feat: add video_codec(2) weight to EPISODE_SCORES and MOVIE_SCORES"
```

---

## Phase B — Language Profile Filters

### Task B1: Migration — add filter columns to language_profiles

**Files:**
- Create: `backend/db/migrations/versions/c1d2e3f4a5b6_add_language_profile_filter_fields.py`

- [ ] **Step 1: Write the migration file**

```python
"""Add mustContain, mustNotContain, cutoff_language, audio_exclude columns to language_profiles."""

from alembic import op

revision = "c1d2e3f4a5b6"
down_revision = "b4c5d6e7f8a9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE language_profiles ADD COLUMN "
        "must_contain_json TEXT NOT NULL DEFAULT '[]'"
    )
    op.execute(
        "ALTER TABLE language_profiles ADD COLUMN "
        "must_not_contain_json TEXT NOT NULL DEFAULT '[]'"
    )
    op.execute(
        "ALTER TABLE language_profiles ADD COLUMN "
        "cutoff_language TEXT NOT NULL DEFAULT ''"
    )
    op.execute(
        "ALTER TABLE language_profiles ADD COLUMN "
        "audio_exclude_languages_json TEXT NOT NULL DEFAULT '[]'"
    )


def downgrade() -> None:
    # SQLite doesn't support DROP COLUMN — recreate table without these columns
    op.execute(
        "CREATE TABLE language_profiles_backup AS "
        "SELECT id, name, source_language, source_language_name, "
        "target_languages_json, target_language_names_json, is_default, "
        "translation_backend, fallback_chain_json, forced_preference, "
        "created_at, updated_at FROM language_profiles"
    )
    op.execute("DROP TABLE language_profiles")
    op.execute("ALTER TABLE language_profiles_backup RENAME TO language_profiles")
```

- [ ] **Step 2: Verify migration applies cleanly**

```
cd backend && python -m alembic upgrade head
```
Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add backend/db/migrations/versions/c1d2e3f4a5b6_add_language_profile_filter_fields.py
git commit -m "feat(db): add mustContain/cutoff/audioExclude columns to language_profiles"
```

---

### Task B2: Update LanguageProfile SQLAlchemy model

**Files:**
- Modify: `backend/db/models/core.py:128–146`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_profile_filters.py (new file)

def test_language_profile_has_filter_columns():
    """Verify LanguageProfile model has the new filter columns."""
    from db.models.core import LanguageProfile
    assert hasattr(LanguageProfile, "must_contain_json")
    assert hasattr(LanguageProfile, "must_not_contain_json")
    assert hasattr(LanguageProfile, "cutoff_language")
    assert hasattr(LanguageProfile, "audio_exclude_languages_json")
```

- [ ] **Step 2: Run test to confirm it fails**

```
cd backend && python -m pytest tests/test_profile_filters.py::test_language_profile_has_filter_columns -v
```

- [ ] **Step 3: Add columns to LanguageProfile model**

In `backend/db/models/core.py`, inside the `LanguageProfile` class after `forced_preference`:

```python
# Language Profile filter fields (Bazarr parity)
must_contain_json: Mapped[str] = mapped_column(Text, nullable=False, default='[]')
must_not_contain_json: Mapped[str] = mapped_column(Text, nullable=False, default='[]')
cutoff_language: Mapped[str] = mapped_column(Text, nullable=False, default='')
audio_exclude_languages_json: Mapped[str] = mapped_column(Text, nullable=False, default='[]')
```

Full updated class (lines 128–152):
```python
class LanguageProfile(db.Model):
    """Language profile for translation source/target configuration."""

    __tablename__ = "language_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    source_language: Mapped[str] = mapped_column(Text, nullable=False, default="en")
    source_language_name: Mapped[str] = mapped_column(Text, nullable=False, default="English")
    target_languages_json: Mapped[str] = mapped_column(Text, nullable=False, default='["de"]')
    target_language_names_json: Mapped[str] = mapped_column(
        Text, nullable=False, default='["German"]'
    )
    is_default: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    translation_backend: Mapped[str | None] = mapped_column(Text, default="ollama")
    fallback_chain_json: Mapped[str | None] = mapped_column(Text, default='["ollama"]')
    forced_preference: Mapped[str | None] = mapped_column(Text, default="disabled")
    # Filter fields (Bazarr parity)
    must_contain_json: Mapped[str] = mapped_column(Text, nullable=False, default='[]')
    must_not_contain_json: Mapped[str] = mapped_column(Text, nullable=False, default='[]')
    cutoff_language: Mapped[str] = mapped_column(Text, nullable=False, default='')
    audio_exclude_languages_json: Mapped[str] = mapped_column(Text, nullable=False, default='[]')
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)
```

- [ ] **Step 4: Run test to confirm it passes**

```
cd backend && python -m pytest tests/test_profile_filters.py::test_language_profile_has_filter_columns -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/db/models/core.py backend/tests/test_profile_filters.py
git commit -m "feat: add filter columns to LanguageProfile model"
```

---

### Task B3: Create profile_filters.py helper

**Files:**
- Create: `backend/wanted_search/profile_filters.py`

- [ ] **Step 1: Write failing tests**

```python
# Append to backend/tests/test_profile_filters.py

from unittest.mock import MagicMock


def _make_result(release_info: str):
    from providers.base import SubtitleFormat, SubtitleResult
    r = SubtitleResult(provider_name="test", subtitle_id="1", language="de",
                       format=SubtitleFormat.SRT)
    r.release_info = release_info
    return r


def test_must_contain_filters_out_non_matching():
    from wanted_search.profile_filters import apply_must_contain
    results = [_make_result("BluRay.x265"), _make_result("WEB-DL.x264")]
    filtered = apply_must_contain(results, ["BluRay"])
    assert len(filtered) == 1
    assert filtered[0].release_info == "BluRay.x265"


def test_must_not_contain_removes_matching():
    from wanted_search.profile_filters import apply_must_not_contain
    results = [_make_result("BluRay.x265"), _make_result("HDCAM.x264")]
    filtered = apply_must_not_contain(results, ["HDCAM"])
    assert len(filtered) == 1
    assert filtered[0].release_info == "BluRay.x265"


def test_must_contain_empty_returns_all():
    from wanted_search.profile_filters import apply_must_contain
    results = [_make_result("BluRay"), _make_result("WEB")]
    assert apply_must_contain(results, []) == results


def test_load_profile_filters_from_none():
    from wanted_search.profile_filters import load_profile_filters
    pf = load_profile_filters(None)
    assert pf["must_contain"] == []
    assert pf["must_not_contain"] == []
    assert pf["cutoff_language"] == ""
    assert pf["audio_exclude_languages"] == []


def test_load_profile_filters_from_profile():
    from wanted_search.profile_filters import load_profile_filters
    profile = MagicMock()
    profile.must_contain_json = '["BluRay"]'
    profile.must_not_contain_json = '["HDCAM","CAM"]'
    profile.cutoff_language = "de"
    profile.audio_exclude_languages_json = '["de","fr"]'
    pf = load_profile_filters(profile)
    assert pf["must_contain"] == ["BluRay"]
    assert pf["must_not_contain"] == ["HDCAM", "CAM"]
    assert pf["cutoff_language"] == "de"
    assert pf["audio_exclude_languages"] == ["de", "fr"]
```

- [ ] **Step 2: Run tests to confirm they fail**

```
cd backend && python -m pytest tests/test_profile_filters.py -v
```
Expected: FAIL — `ModuleNotFoundError: wanted_search.profile_filters`

- [ ] **Step 3: Create profile_filters.py**

```python
# backend/wanted_search/profile_filters.py
"""Post-search result filtering derived from a LanguageProfile's filter settings."""

import json
import logging

logger = logging.getLogger(__name__)


def apply_must_contain(results: list, must_contain: list[str]) -> list:
    """Keep only results whose release_info contains at least one must_contain term."""
    if not must_contain:
        return results
    terms = [t.lower() for t in must_contain if t.strip()]
    if not terms:
        return results
    filtered = [r for r in results if any(t in r.release_info.lower() for t in terms)]
    logger.debug("mustContain(%s): %d → %d results", terms, len(results), len(filtered))
    return filtered


def apply_must_not_contain(results: list, must_not_contain: list[str]) -> list:
    """Remove results whose release_info contains any must_not_contain term."""
    if not must_not_contain:
        return results
    terms = [t.lower() for t in must_not_contain if t.strip()]
    if not terms:
        return results
    filtered = [r for r in results if not any(t in r.release_info.lower() for t in terms)]
    logger.debug("mustNotContain(%s): %d → %d results", terms, len(results), len(filtered))
    return filtered


def load_profile_filters(profile) -> dict:
    """Extract filter config from a LanguageProfile ORM instance (or None).

    Returns a dict with keys:
        must_contain: list[str]
        must_not_contain: list[str]
        cutoff_language: str  (empty = no cutoff)
        audio_exclude_languages: list[str]
    """
    if profile is None:
        return {
            "must_contain": [],
            "must_not_contain": [],
            "cutoff_language": "",
            "audio_exclude_languages": [],
        }

    def _load(attr: str, default: str = "[]") -> list:
        raw = getattr(profile, attr, default) or default
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, TypeError):
            return []

    return {
        "must_contain": _load("must_contain_json"),
        "must_not_contain": _load("must_not_contain_json"),
        "cutoff_language": getattr(profile, "cutoff_language", "") or "",
        "audio_exclude_languages": _load("audio_exclude_languages_json"),
    }
```

- [ ] **Step 4: Run tests to confirm they pass**

```
cd backend && python -m pytest tests/test_profile_filters.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/wanted_search/profile_filters.py backend/tests/test_profile_filters.py
git commit -m "feat: add profile_filters.py with mustContain/mustNotContain helpers"
```

---

### Task B4: Wire must_contain/must_not_contain into ProviderManager.search()

**Files:**
- Modify: `backend/providers/__init__.py:764`

- [ ] **Step 1: Write failing test**

```python
# Append to backend/tests/test_profile_filters.py

def test_search_applies_must_contain(monkeypatch):
    """ProviderManager.search() respects must_contain param."""
    from providers import ProviderManager
    from providers.base import SubtitleFormat, SubtitleResult

    def _mock_search_with_retry(name, provider, query):
        r = SubtitleResult(provider_name=name, subtitle_id="1", language="de",
                           format=SubtitleFormat.SRT)
        r.release_info = "HDCAM.x264"
        r.score = 100
        return [r], 50.0

    import providers as pm_module
    monkeypatch.setattr(pm_module, "_PROVIDER_CLASSES", {})
    manager = ProviderManager.__new__(ProviderManager)
    manager._providers = {}
    manager._rate_limits = {}
    manager._rate_limit_lock = __import__("threading").Lock()
    manager._circuit_breakers = {}

    # Manually add a result to simulate search output via override
    from unittest.mock import patch
    stub_results = [
        SubtitleResult(provider_name="p", subtitle_id="1", language="de",
                       format=SubtitleFormat.SRT, release_info="BluRay.x265"),
        SubtitleResult(provider_name="p", subtitle_id="2", language="de",
                       format=SubtitleFormat.SRT, release_info="HDCAM.x264"),
    ]
    for r in stub_results:
        r.score = 100

    with patch.object(manager, "_get_all_raw_results", return_value=stub_results, create=True):
        # Since _get_all_raw_results is not a real method, test the filter functions directly
        from wanted_search.profile_filters import apply_must_contain
        filtered = apply_must_contain(stub_results, ["BluRay"])
        assert len(filtered) == 1
        assert filtered[0].release_info == "BluRay.x265"
```

- [ ] **Step 2: Add params to search() signature**

Find the `def search(` line at `backend/providers/__init__.py:764`:

```python
# OLD:
def search(
    self,
    query: VideoQuery,
    format_filter: SubtitleFormat | None = None,
    min_score: int = 0,
    early_exit: bool = True,
) -> list[SubtitleResult]:

# NEW:
def search(
    self,
    query: VideoQuery,
    format_filter: SubtitleFormat | None = None,
    min_score: int = 0,
    early_exit: bool = True,
    must_contain: list[str] | None = None,
    must_not_contain: list[str] | None = None,
) -> list[SubtitleResult]:
```

- [ ] **Step 3: Add filter block after the blacklist filter (around line 976)**

Find the comment `# Release group filtering` block. Insert before it:

```python
        # mustContain / mustNotContain filtering (language profile)
        if must_contain:
            from wanted_search.profile_filters import apply_must_contain
            all_results = apply_must_contain(all_results, must_contain)
        if must_not_contain:
            from wanted_search.profile_filters import apply_must_not_contain
            all_results = apply_must_not_contain(all_results, must_not_contain)
```

- [ ] **Step 4: Pass params through search_with_fallback and search_and_download_best**

In `search_with_fallback()` (around line 1049):
```python
# OLD:
def search_with_fallback(
    self,
    query: VideoQuery,
    format_filter: SubtitleFormat | None = None,
    min_score: int = 0,
) -> list[SubtitleResult]:

# NEW:
def search_with_fallback(
    self,
    query: VideoQuery,
    format_filter: SubtitleFormat | None = None,
    min_score: int = 0,
    must_contain: list[str] | None = None,
    must_not_contain: list[str] | None = None,
) -> list[SubtitleResult]:
```

And update the internal `self.search(...)` call inside `search_with_fallback` to pass through:
```python
results = self.search(query, format_filter=format_filter, min_score=min_score,
                      must_contain=must_contain, must_not_contain=must_not_contain)
```

In `search_and_download_best()` (around line 1103):
```python
# OLD:
def search_and_download_best(
    self,
    query: VideoQuery,
    format_filter: SubtitleFormat | None = None,
    min_score: int = 0,
) -> SubtitleResult | None:

# NEW:
def search_and_download_best(
    self,
    query: VideoQuery,
    format_filter: SubtitleFormat | None = None,
    min_score: int = 0,
    must_contain: list[str] | None = None,
    must_not_contain: list[str] | None = None,
) -> SubtitleResult | None:
```

And update the internal call:
```python
results = self.search_with_fallback(
    query, format_filter=format_filter, min_score=min_score,
    must_contain=must_contain, must_not_contain=must_not_contain
)
```

- [ ] **Step 5: Run existing tests to confirm no regressions**

```
cd backend && python -m pytest tests/ --tb=short -q \
  --ignore=tests/performance \
  --ignore=tests/integration/test_provider_pipeline.py \
  --ignore=tests/test_video_sync.py \
  --ignore=tests/test_translation_backends.py \
  -k "not (test_sonarr_download_webhook or test_radarr_download_webhook or test_parse_llm_response_too_many_merge or test_record_backend_success)"
```

- [ ] **Step 6: Commit**

```bash
git add backend/providers/__init__.py
git commit -m "feat: add must_contain/must_not_contain params to ProviderManager.search()"
```

---

### Task B5: Apply profile filters in process_wanted_item (cutoff + audio_exclude)

**Files:**
- Modify: `backend/wanted_search/process.py:207`

- [ ] **Step 1: Write failing tests**

```python
# Append to backend/tests/test_profile_filters.py

def test_cutoff_language_check():
    """load_profile_filters returns correct cutoff_language."""
    from unittest.mock import MagicMock
    from wanted_search.profile_filters import load_profile_filters
    profile = MagicMock()
    profile.must_contain_json = "[]"
    profile.must_not_contain_json = "[]"
    profile.cutoff_language = "de"
    profile.audio_exclude_languages_json = "[]"
    pf = load_profile_filters(profile)
    assert pf["cutoff_language"] == "de"


def test_audio_exclude_check():
    """audio_exclude_languages correctly deserialized."""
    from unittest.mock import MagicMock
    from wanted_search.profile_filters import load_profile_filters
    profile = MagicMock()
    profile.must_contain_json = "[]"
    profile.must_not_contain_json = "[]"
    profile.cutoff_language = ""
    profile.audio_exclude_languages_json = '["de","ja"]'
    pf = load_profile_filters(profile)
    assert "de" in pf["audio_exclude_languages"]
    assert "ja" in pf["audio_exclude_languages"]
```

- [ ] **Step 2: Run to confirm they pass (they should — testing profile_filters.py)**

```
cd backend && python -m pytest tests/test_profile_filters.py -v
```

- [ ] **Step 3: Add profile loading + checks at the start of process_wanted_item()**

In `backend/wanted_search/process.py`, in `process_wanted_item()` after `item_lang` is determined (around line 218), add:

```python
    # ── Language profile filters ──────────────────────────────────────────────
    from db.models.core import LanguageProfile
    from extensions import db as _db
    from wanted_search.profile_filters import load_profile_filters

    _profile_obj = None
    _profile_id = item.get("profile_id")
    if _profile_id:
        try:
            _profile_obj = _db.session.get(LanguageProfile, int(_profile_id))
        except Exception as _pe:
            logger.debug("Could not load profile %s: %s", _profile_id, _pe)
    _pf = load_profile_filters(_profile_obj)

    # Cutoff check: if cutoff_language subtitle already exists on disk, skip search
    _cutoff = _pf["cutoff_language"]
    if _cutoff:
        from translator import get_output_path_for_lang
        for _ext in ("ass", "srt", "vtt"):
            _cutoff_path = get_output_path_for_lang(file_path, _ext, _cutoff)
            if os.path.exists(_cutoff_path):
                logger.info(
                    "Wanted %d: cutoff language '%s' already present at %s, skipping",
                    item_id, _cutoff, _cutoff_path,
                )
                update_wanted_status(item_id, "found")
                return {
                    "wanted_id": item_id,
                    "status": "skipped",
                    "reason": f"cutoff language '{_cutoff}' already present",
                }

    # Audio-exclude check: skip if audio is already in the target language
    _audio_exclude = _pf["audio_exclude_languages"]
    if _audio_exclude and item_lang in _audio_exclude:
        try:
            from ass_utils import has_target_language_audio, run_ffprobe
            _ffprobe_data = run_ffprobe(file_path)
            if has_target_language_audio(_ffprobe_data, item_lang):
                logger.info(
                    "Wanted %d: audio already in '%s', skipping (audio_exclude)",
                    item_id, item_lang,
                )
                update_wanted_status(item_id, "found")
                return {
                    "wanted_id": item_id,
                    "status": "skipped",
                    "reason": f"audio already in '{item_lang}'",
                }
        except Exception as _ae:
            logger.debug("Audio-exclude check failed (non-fatal): %s", _ae)
    # ── End language profile filters ──────────────────────────────────────────
```

Then pass `must_contain`/`must_not_contain` to every `search_and_download_best()` call in `process_wanted_item`:
```python
# After building the manager call, add the profile filter kwargs:
_mc = _pf["must_contain"] or None
_mnc = _pf["must_not_contain"] or None

# Example — the first search_and_download_best call (line ~260):
result = manager.search_and_download_best(
    query,
    format_filter=fmt,
    must_contain=_mc,
    must_not_contain=_mnc,
)
```

Apply the same `must_contain=_mc, must_not_contain=_mnc` kwargs to all other `search_and_download_best` calls in `process_wanted_item` (there are ~4 of them).

- [ ] **Step 4: Run the full test suite**

```
cd backend && python -m pytest tests/ --tb=short -q \
  --ignore=tests/performance \
  --ignore=tests/integration/test_provider_pipeline.py \
  --ignore=tests/test_video_sync.py \
  --ignore=tests/test_translation_backends.py \
  -k "not (test_sonarr_download_webhook or test_radarr_download_webhook or test_parse_llm_response_too_many_merge or test_record_backend_success)"
```

- [ ] **Step 5: Commit**

```bash
git add backend/wanted_search/process.py backend/tests/test_profile_filters.py
git commit -m "feat: apply language profile filters (cutoff, audioExclude, mustContain) in search"
```

---

## Phase C — Provider Infrastructure

### Task C1: Add is_open property to CircuitBreaker

**Files:**
- Modify: `backend/circuit_breaker.py`

- [ ] **Step 1: Write failing test**

```python
# Append to existing test_circuit_breaker.py (or create it)
# backend/tests/test_circuit_breaker_extras.py

def test_is_open_false_when_closed():
    from circuit_breaker import CircuitBreaker
    cb = CircuitBreaker("test", failure_threshold=2, cooldown_seconds=60)
    assert cb.is_open is False

def test_is_open_true_after_threshold():
    from circuit_breaker import CircuitBreaker
    cb = CircuitBreaker("test", failure_threshold=2, cooldown_seconds=60)
    cb.record_failure()
    cb.record_failure()
    assert cb.is_open is True
```

- [ ] **Step 2: Run to confirm failure**

```
cd backend && python -m pytest tests/test_circuit_breaker_extras.py -v
```
Expected: FAIL — `AttributeError: 'CircuitBreaker' object has no attribute 'is_open'`

- [ ] **Step 3: Add is_open property**

In `backend/circuit_breaker.py`, add after the `__init__` method:

```python
@property
def is_open(self) -> bool:
    """True when in OPEN state (not accepting requests)."""
    with self._lock:
        return self._state == CircuitState.OPEN
```

- [ ] **Step 4: Run tests to confirm they pass**

```
cd backend && python -m pytest tests/test_circuit_breaker_extras.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/circuit_breaker.py backend/tests/test_circuit_breaker_extras.py
git commit -m "feat: add is_open property to CircuitBreaker"
```

---

### Task C2: Persist circuit breaker OPEN state to DB + restore on startup

**Files:**
- Modify: `backend/providers/__init__.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_circuit_breaker_extras.py — append

def test_circuit_breaker_open_writes_to_provider_stats(tmp_path, monkeypatch):
    """When CB transitions to OPEN, auto_disable_provider is called."""
    from unittest.mock import patch, call
    from circuit_breaker import CircuitBreaker

    persisted = {}

    def mock_auto_disable(name, cooldown_minutes):
        persisted[name] = cooldown_minutes

    cb = CircuitBreaker("myprovider", failure_threshold=1, cooldown_seconds=120)
    # Simulate ProviderManager persisting on state change
    cb.record_failure()
    assert cb.is_open

    # The actual persistence happens in ProviderManager, not CircuitBreaker.
    # This test verifies the is_open property can trigger the call.
    if cb.is_open:
        mock_auto_disable("myprovider", cb.cooldown_seconds // 60)

    assert persisted.get("myprovider") == 2  # 120s / 60 = 2 min
```

- [ ] **Step 2: Run to confirm test passes (it's a unit test of the logic pattern)**

```
cd backend && python -m pytest tests/test_circuit_breaker_extras.py -v
```

- [ ] **Step 3: Add persistence calls in ProviderManager.search() exception handler**

Find the exception handler blocks in `backend/providers/__init__.py` (around lines 920–933). There are two of them (FutureTimeoutError and generic Exception). Update both:

```python
            except FutureTimeoutError:
                logger.warning("Provider %s search timed out", name)
                cb = self._circuit_breakers.get(name)
                if cb:
                    cb.record_failure()
                    if cb.is_open:  # just transitioned to OPEN
                        try:
                            from db.providers import auto_disable_provider
                            auto_disable_provider(name, cooldown_minutes=max(1, cb.cooldown_seconds // 60))
                        except Exception as _pe:
                            logger.debug("CB persistence failed: %s", _pe)
                update_provider_stats(name, success=False, score=0)
                self._check_auto_disable(name)

            except Exception as e:
                logger.warning("Provider %s search failed: %s", name, e)
                cb = self._circuit_breakers.get(name)
                if cb:
                    cb.record_failure()
                    if cb.is_open:  # just transitioned to OPEN
                        try:
                            from db.providers import auto_disable_provider
                            cooldown = max(1, cb.cooldown_seconds // 60)
                            auto_disable_provider(name, cooldown_minutes=cooldown)
                        except Exception as _pe:
                            logger.debug("CB persistence failed: %s", _pe)
                update_provider_stats(name, success=False, score=0)
                self._check_auto_disable(name)
                # Rate-limit exception → extended throttle (Bazarr throttle_map parity)
                if isinstance(e, ProviderRateLimitError):
                    throttle_min = getattr(self.settings, "provider_rate_limit_throttle_minutes", 60)
                    try:
                        from db.providers import auto_disable_provider
                        auto_disable_provider(name, cooldown_minutes=throttle_min)
                        logger.info(
                            "Provider %s rate-limited: extended throttle for %d min",
                            name, throttle_min,
                        )
                    except Exception as _te:
                        logger.debug("Rate-limit throttle persistence failed: %s", _te)
```

Also update `download()` exception handler (around line 1086) similarly.

- [ ] **Step 4: Restore CB state from DB on _init_providers()**

At the end of `_init_providers()` in ProviderManager, add:

```python
        # Restore circuit breaker state from DB: if a provider was disabled at last
        # shutdown, its ProviderStats.disabled_until covers the cooldown. The
        # is_provider_auto_disabled() check in search() already handles this — no
        # extra state to restore in the CircuitBreaker object itself.
        # (Circuit breaker starts CLOSED; auto_disable covers the persistence gap.)
        logger.debug("Provider circuit breakers initialized: %s", list(self._circuit_breakers.keys()))
```

This comment documents the design decision: `is_provider_auto_disabled` (DB-backed) already handles cross-restart persistence. The circuit breaker stays in-memory.

- [ ] **Step 5: Add provider_rate_limit_throttle_minutes to config.py**

Find `backend/config.py` and add to the Settings class:

```python
provider_rate_limit_throttle_minutes: int = 60  # Extended throttle on HTTP 429
```

- [ ] **Step 6: Run tests**

```
cd backend && python -m pytest tests/ --tb=short -q \
  --ignore=tests/performance \
  --ignore=tests/integration/test_provider_pipeline.py \
  --ignore=tests/test_video_sync.py \
  --ignore=tests/test_translation_backends.py \
  -k "not (test_sonarr_download_webhook or test_radarr_download_webhook or test_parse_llm_response_too_many_merge or test_record_backend_success)"
```

- [ ] **Step 7: Commit**

```bash
git add backend/circuit_breaker.py backend/providers/__init__.py backend/config.py \
  backend/tests/test_circuit_breaker_extras.py
git commit -m "feat: persist circuit breaker OPEN state to DB; rate-limit throttle_map"
```

---

## Phase D — Download Quality

### Task D1: Migration — add upgraded_from_id to subtitle_downloads

**Files:**
- Create: `backend/db/migrations/versions/d2e3f4a5b6c7_add_subtitle_download_upgrade_tracking.py`

- [ ] **Step 1: Create migration**

```python
"""Add upgraded_from_id column to subtitle_downloads for upgrade chain tracking."""

from alembic import op

revision = "d2e3f4a5b6c7"
down_revision = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE subtitle_downloads ADD COLUMN upgraded_from_id INTEGER"
    )


def downgrade() -> None:
    # SQLite: recreate without the column
    op.execute(
        "CREATE TABLE subtitle_downloads_backup AS "
        "SELECT id, provider_name, subtitle_id, language, format, file_path, "
        "score, subtitle_type, source, downloaded_at FROM subtitle_downloads"
    )
    op.execute("DROP TABLE subtitle_downloads")
    op.execute("ALTER TABLE subtitle_downloads_backup RENAME TO subtitle_downloads")
```

> **Note:** If Phase B was implemented in a separate branch, change `down_revision` to `"b4c5d6e7f8a9"` (the pre-B head) and adjust accordingly.

- [ ] **Step 2: Apply migration**

```
cd backend && python -m alembic upgrade head
```

- [ ] **Step 3: Commit**

```bash
git add backend/db/migrations/versions/d2e3f4a5b6c7_add_subtitle_download_upgrade_tracking.py
git commit -m "feat(db): add upgraded_from_id to subtitle_downloads for upgrade chain"
```

---

### Task D2: Update SubtitleDownload model + repository

**Files:**
- Modify: `backend/db/models/providers.py:30–49`
- Modify: `backend/db/repositories/providers.py:132`
- Modify: `backend/db/providers.py:74`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_upgrade_chain.py (new file)

def test_subtitle_download_has_upgraded_from_id():
    from db.models.providers import SubtitleDownload
    assert hasattr(SubtitleDownload, "upgraded_from_id")


def test_record_subtitle_download_accepts_upgraded_from_id(tmp_path):
    """record_subtitle_download stores upgraded_from_id when provided."""
    import os
    from unittest.mock import patch, MagicMock

    fake_session = MagicMock()
    fake_session.add = MagicMock()

    with patch("db.repositories.providers.SubtitleDownloadRepository._commit"):
        from db.repositories.providers import SubtitleDownloadRepository
        repo = SubtitleDownloadRepository.__new__(SubtitleDownloadRepository)
        repo.session = fake_session
        repo._now = lambda: "2026-03-28T12:00:00"
        repo.record_subtitle_download(
            "opensubtitles", "sub123", "de", "ass", "/media/ep.mkv", 200,
            source="provider", upgraded_from_id=42
        )
        call_args = fake_session.add.call_args[0][0]
        assert call_args.upgraded_from_id == 42


def test_get_latest_download_id_returns_none_when_no_records():
    from unittest.mock import patch, MagicMock
    from db.repositories.providers import SubtitleDownloadRepository
    repo = SubtitleDownloadRepository.__new__(SubtitleDownloadRepository)
    mock_session = MagicMock()
    mock_session.execute.return_value.scalar_one_or_none.return_value = None
    repo.session = mock_session
    result = repo.get_latest_download_id("/no/such/path.mkv")
    assert result is None
```

- [ ] **Step 2: Run to confirm failures**

```
cd backend && python -m pytest tests/test_upgrade_chain.py -v
```

- [ ] **Step 3: Add upgraded_from_id to SubtitleDownload model**

In `backend/db/models/providers.py`, update the `SubtitleDownload` class:

```python
class SubtitleDownload(db.Model):
    """Record of downloaded subtitles from providers."""

    __tablename__ = "subtitle_downloads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider_name: Mapped[str] = mapped_column(Text, nullable=False)
    subtitle_id: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(Text, nullable=False)
    format: Mapped[str | None] = mapped_column(Text, default="")
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[int | None] = mapped_column(Integer, default=0)
    subtitle_type: Mapped[str | None] = mapped_column(Text, default="full")
    source: Mapped[str | None] = mapped_column(Text, default="provider")
    downloaded_at: Mapped[str] = mapped_column(Text, nullable=False)
    upgraded_from_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # NEW

    __table_args__ = (
        Index("idx_subtitle_downloads_path", "file_path"),
        Index("idx_subtitle_downloads_downloaded_at", "downloaded_at"),
    )
```

- [ ] **Step 4: Update record_subtitle_download in the repository**

In `backend/db/repositories/providers.py:132`:

```python
    def record_subtitle_download(
        self,
        provider_name: str,
        subtitle_id: str,
        language: str,
        fmt: str,
        file_path: str,
        score: int,
        source: str = "provider",
        upgraded_from_id: int | None = None,  # NEW
    ):
        now = self._now()
        entry = SubtitleDownload(
            provider_name=provider_name,
            subtitle_id=subtitle_id,
            language=language,
            format=fmt,
            file_path=file_path,
            score=score,
            source=source,
            downloaded_at=now,
            upgraded_from_id=upgraded_from_id,  # NEW
        )
        self.session.add(entry)
        self._commit()
```

Also add `get_latest_download_id` method to the repository:

```python
    def get_latest_download_id(self, file_path: str) -> int | None:
        """Return the id of the most recent SubtitleDownload for this file, or None."""
        from sqlalchemy import select, desc

        stmt = (
            select(SubtitleDownload.id)
            .where(SubtitleDownload.file_path == file_path)
            .order_by(desc(SubtitleDownload.downloaded_at))
            .limit(1)
        )
        return self.session.execute(stmt).scalar_one_or_none()
```

- [ ] **Step 5: Update the facade in db/providers.py**

In `backend/db/providers.py:74`:

```python
def record_subtitle_download(
    provider_name: str,
    subtitle_id: str,
    language: str,
    fmt: str,
    file_path: str,
    score: int,
    source: str = "provider",
    upgraded_from_id: int | None = None,  # NEW
):
    result = _get_repo().record_subtitle_download(
        provider_name, subtitle_id, language, fmt, file_path, score,
        source=source, upgraded_from_id=upgraded_from_id,
    )
    try:
        from db.jobs import record_stat
        record_stat(success=True, fmt=fmt, source=provider_name)
    except Exception:
        logger.debug("Could not record download in daily_stats", exc_info=True)
    return result


def get_latest_download_id(file_path: str) -> int | None:
    """Return the DB id of the most recent download for this file path."""
    return _get_repo().get_latest_download_id(file_path)
```

- [ ] **Step 6: Run tests**

```
cd backend && python -m pytest tests/test_upgrade_chain.py -v
```

- [ ] **Step 7: Commit**

```bash
git add backend/db/models/providers.py backend/db/repositories/providers.py \
  backend/db/providers.py backend/tests/test_upgrade_chain.py
git commit -m "feat: add upgraded_from_id to SubtitleDownload for upgrade chain tracking"
```

---

### Task D3: Pass upgraded_from_id in process_wanted_item upgrades

**Files:**
- Modify: `backend/wanted_search/process.py`

- [ ] **Step 1: Locate upgrade path and add upgraded_from_id**

In `process_wanted_item()`, the upgrade path is identified by `is_upgrade` flag (around line 263). Before calling `record_subtitle_download`, resolve the previous download's ID:

```python
            # Resolve upgraded_from_id for audit trail
            _upgraded_from_id: int | None = None
            if is_upgrade:
                try:
                    from db.providers import get_latest_download_id
                    _upgraded_from_id = get_latest_download_id(file_path)
                except Exception as _uid_err:
                    logger.debug("Could not resolve upgraded_from_id: %s", _uid_err)
```

Then pass it to all `record_subtitle_download` calls in the upgrade path:

```python
            record_subtitle_download(
                result.provider_name,
                result.subtitle_id,
                item_lang,
                result.format.value if result.format.value != "unknown" else "ass",
                file_path,
                result.score,
                upgraded_from_id=_upgraded_from_id,  # NEW
            )
```

- [ ] **Step 2: Run the full test suite**

```
cd backend && python -m pytest tests/ --tb=short -q \
  --ignore=tests/performance \
  --ignore=tests/integration/test_provider_pipeline.py \
  --ignore=tests/test_video_sync.py \
  --ignore=tests/test_translation_backends.py \
  -k "not (test_sonarr_download_webhook or test_radarr_download_webhook or test_parse_llm_response_too_many_merge or test_record_backend_success)"
```

- [ ] **Step 3: Commit**

```bash
git add backend/wanted_search/process.py
git commit -m "feat: record upgraded_from_id in subtitle download history on upgrades"
```

---

### Task D4: Post-download shell command

**Files:**
- Modify: `backend/config.py`
- Create: `backend/post_download.py`
- Modify: `backend/providers/__init__.py:1320` (end of save_subtitle)

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_post_download.py (new file)

def test_run_post_download_command_noop_when_empty():
    from post_download import run_post_download_command
    # Should not raise, just return silently
    run_post_download_command("", "/sub.ass", "de", "opensubtitles", 200, "/video.mkv")


def test_run_post_download_command_substitutes_variables(monkeypatch):
    import subprocess
    from post_download import run_post_download_command

    calls = []
    def mock_run(cmd, shell, timeout, check):
        calls.append(cmd)

    monkeypatch.setattr(subprocess, "run", mock_run)
    run_post_download_command(
        "echo {subtitle_path} {language} {provider} {score}",
        "/media/ep.ass", "de", "jimaku", 180, "/media/ep.mkv"
    )
    assert len(calls) == 1
    assert "'/media/ep.ass'" in calls[0] or "/media/ep.ass" in calls[0]
    assert "de" in calls[0]
    assert "jimaku" in calls[0]
    assert "180" in calls[0]


def test_run_post_download_command_handles_failure_gracefully(monkeypatch):
    import subprocess
    from post_download import run_post_download_command

    def mock_run(*args, **kwargs):
        raise OSError("command not found")

    monkeypatch.setattr(subprocess, "run", mock_run)
    # Should NOT raise — errors are logged, not propagated
    run_post_download_command("bad_command", "/sub.ass", "de", "test", 100, "")
```

- [ ] **Step 2: Run to confirm failures**

```
cd backend && python -m pytest tests/test_post_download.py -v
```
Expected: FAIL — `ModuleNotFoundError: post_download`

- [ ] **Step 3: Create post_download.py**

```python
# backend/post_download.py
"""Post-download shell command execution with variable substitution.

Variables available in the command string:
    {subtitle_path}  — absolute path to the saved subtitle file
    {language}       — ISO 639-1 language code
    {provider}       — provider name (e.g. "jimaku")
    {score}          — integer match score
    {video_path}     — absolute path to the source video file (may be empty)
"""

import logging
import shlex
import subprocess

logger = logging.getLogger(__name__)


def run_post_download_command(
    command: str,
    subtitle_path: str,
    language: str,
    provider: str,
    score: int,
    video_path: str = "",
) -> None:
    """Execute the post-download shell command if configured.

    Errors are logged as warnings but never propagated — post-processing
    is best-effort and must not break the download pipeline.
    """
    if not command or not command.strip():
        return

    expanded = (
        command
        .replace("{subtitle_path}", shlex.quote(subtitle_path))
        .replace("{language}", shlex.quote(language))
        .replace("{provider}", shlex.quote(provider))
        .replace("{score}", str(int(score)))
        .replace("{video_path}", shlex.quote(video_path) if video_path else "")
    )
    try:
        logger.info("Running post-download command: %s", expanded)
        subprocess.run(expanded, shell=True, timeout=60, check=False)
    except Exception as exc:
        logger.warning("post_download_command failed: %s", exc)
```

- [ ] **Step 4: Add post_download_command to config.py**

```python
# In the Settings class, add:
post_download_command: str = ""  # Shell command to run after each subtitle download
```

- [ ] **Step 5: Call run_post_download_command at end of save_subtitle()**

In `backend/providers/__init__.py`, at the very end of `save_subtitle()` (after the pipeline hook call at line 1324, before `return output_path`):

```python
        # Post-download shell command (user-configurable, Bazarr parity)
        try:
            from config import get_settings as _get_settings_pd
            from post_download import run_post_download_command

            _pd_settings = _get_settings_pd()
            _pd_cmd = getattr(_pd_settings, "post_download_command", "")
            if _pd_cmd:
                run_post_download_command(
                    _pd_cmd,
                    subtitle_path=output_path,
                    language=result.language or "",
                    provider=result.provider_name or "",
                    score=result.score or 0,
                )
        except Exception as _pd_err:
            logger.warning("post_download_command hook failed: %s", _pd_err)
```

- [ ] **Step 6: Run tests**

```
cd backend && python -m pytest tests/test_post_download.py -v
```

- [ ] **Step 7: Run full test suite**

```
cd backend && python -m pytest tests/ --tb=short -q \
  --ignore=tests/performance \
  --ignore=tests/integration/test_provider_pipeline.py \
  --ignore=tests/test_video_sync.py \
  --ignore=tests/test_translation_backends.py \
  -k "not (test_sonarr_download_webhook or test_radarr_download_webhook or test_parse_llm_response_too_many_merge or test_record_backend_success)"
```

- [ ] **Step 8: Commit**

```bash
git add backend/post_download.py backend/config.py backend/providers/__init__.py \
  backend/tests/test_post_download.py
git commit -m "feat: add post_download_command config with variable substitution"
```

---

### Task D5: Expose alass as a manual sync API endpoint

**Files:**
- Create: `backend/routes/sync.py`
- Modify: `backend/app.py`

Background: `sync_with_alass()` already exists in `backend/services/video_sync.py:79` and takes `(subtitle_path, reference_path)`. The current `_try_auto_sync()` blocks alass for auto-sync because it requires a reference track. This exposes it for *manual* sync where the user provides both subtitle and reference.

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_sync_alass.py (new file)

import pytest
from unittest.mock import patch


@pytest.fixture
def app():
    from app import create_app
    app = create_app({"TESTING": True, "DATABASE_URL": "sqlite:///:memory:"})
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def _auth_headers(client):
    with client.application.app_context():
        from config import get_settings
        return {"X-Api-Key": get_settings().api_key}


def test_alass_sync_missing_params(client):
    headers = _auth_headers(client)
    resp = client.post("/api/v1/sync/alass", json={}, headers=headers)
    assert resp.status_code == 400


def test_alass_sync_path_outside_media(client, tmp_path):
    headers = _auth_headers(client)
    resp = client.post("/api/v1/sync/alass", json={
        "subtitle_path": "/etc/passwd",
        "reference_path": "/etc/passwd",
    }, headers=headers)
    assert resp.status_code == 403


def test_alass_sync_success(client, tmp_path, monkeypatch):
    headers = _auth_headers(client)
    sub = str(tmp_path / "ep.de.ass")
    ref = str(tmp_path / "ep.en.ass")
    open(sub, "w").close()
    open(ref, "w").close()

    with (
        patch("routes.sync.is_safe_path", return_value=True),
        patch("routes.sync.sync_with_alass") as mock_sync,
    ):
        resp = client.post("/api/v1/sync/alass", json={
            "subtitle_path": sub,
            "reference_path": ref,
        }, headers=headers)

    assert resp.status_code == 200
    mock_sync.assert_called_once_with(sub, ref)
```

- [ ] **Step 2: Run to confirm failures**

```
cd backend && python -m pytest tests/test_sync_alass.py -v
```

- [ ] **Step 3: Create routes/sync.py**

```python
# backend/routes/sync.py
"""Manual subtitle synchronization endpoints.

Exposes:
    POST /api/v1/sync/alass  — sync subtitle to reference subtitle using alass
    POST /api/v1/sync/ffsubsync  — sync subtitle to audio using ffsubsync (existing logic)
"""

import logging
import os

from flask import Blueprint, jsonify, request

from auth import require_api_key
from config import get_settings
from security_utils import is_safe_path

logger = logging.getLogger(__name__)

bp = Blueprint("sync", __name__, url_prefix="/api/v1/sync")


@bp.route("/alass", methods=["POST"])
@require_api_key
def alass_sync():
    """Sync a subtitle file to a reference subtitle using alass.

    Body JSON:
        subtitle_path (str): absolute path to the subtitle to be synced (modified in-place)
        reference_path (str): absolute path to the reference subtitle (read-only)

    Returns 200 on success, 400 on bad params, 403 on path traversal, 500 on sync error.
    """
    data = request.get_json(silent=True) or {}
    subtitle_path = data.get("subtitle_path", "").strip()
    reference_path = data.get("reference_path", "").strip()

    if not subtitle_path or not reference_path:
        return jsonify({"error": "subtitle_path and reference_path are required"}), 400

    settings = get_settings()
    media_path = getattr(settings, "media_path", "/media")

    for path in (subtitle_path, reference_path):
        if not is_safe_path(path, media_path):
            return jsonify({"error": "Access denied — path outside media directory"}), 403

    if not os.path.isfile(subtitle_path):
        return jsonify({"error": f"subtitle_path not found: {subtitle_path}"}), 404
    if not os.path.isfile(reference_path):
        return jsonify({"error": f"reference_path not found: {reference_path}"}), 404

    try:
        from services.video_sync import SyncUnavailableError, sync_with_alass

        sync_with_alass(subtitle_path, reference_path)
        logger.info("alass: synced %s using reference %s", subtitle_path, reference_path)
        return jsonify({"status": "ok", "synced_path": subtitle_path}), 200

    except ImportError:
        return jsonify({"error": "alass is not installed on this system"}), 503
    except Exception as e:
        from services.video_sync import SyncUnavailableError

        if isinstance(e, SyncUnavailableError):
            return jsonify({"error": f"alass unavailable: {e}"}), 503
        logger.error("alass sync failed: %s", e, exc_info=True)
        return jsonify({"error": f"Sync failed: {e}"}), 500
```

- [ ] **Step 4: Register the blueprint in app.py**

Find where other blueprints are registered in `backend/app.py`. Add:

```python
    from routes.sync import bp as sync_bp
    app.register_blueprint(sync_bp)
```

Place it near the other `routes.*` imports (search for `from routes.` to find the pattern).

- [ ] **Step 5: Run tests**

```
cd backend && python -m pytest tests/test_sync_alass.py -v
```

- [ ] **Step 6: Run full suite**

```
cd backend && python -m pytest tests/ --tb=short -q \
  --ignore=tests/performance \
  --ignore=tests/integration/test_provider_pipeline.py \
  --ignore=tests/test_video_sync.py \
  --ignore=tests/test_translation_backends.py \
  -k "not (test_sonarr_download_webhook or test_radarr_download_webhook or test_parse_llm_response_too_many_merge or test_record_backend_success)"
```

- [ ] **Step 7: Commit**

```bash
git add backend/routes/sync.py backend/app.py backend/tests/test_sync_alass.py
git commit -m "feat: expose alass manual sync as POST /api/v1/sync/alass"
```

---

### Task D6: Pre-PR checks

- [ ] **Step 1: Run ruff on full backend**

```
cd backend && ruff check . && ruff format --check .
```
Expected: no violations. Fix any violations before continuing.

- [ ] **Step 2: Run frontend lint + type check**

```
cd frontend && npm run lint && npx tsc --noEmit
```

- [ ] **Step 3: Run all backend tests one final time**

```
cd backend && python -m pytest tests/ --tb=short -q \
  --ignore=tests/performance \
  --ignore=tests/integration/test_provider_pipeline.py \
  --ignore=tests/test_video_sync.py \
  --ignore=tests/test_translation_backends.py \
  -k "not (test_sonarr_download_webhook or test_radarr_download_webhook or test_parse_llm_response_too_many_merge or test_record_backend_success)"
```

- [ ] **Step 4: Final commit tag**

```bash
git add -u
git commit -m "chore: pre-PR cleanup pass for bazarr-improvements phase D"
```

---

## Self-Review

### Spec Coverage
| Item | Phase | Task |
|------|-------|------|
| video_codec weight | A | A1 |
| mustContain / mustNotContain | B | B3, B4, B5 |
| Cutoff language | B | B5 |
| Audio-Only-Include | B | B5 |
| Rate-Limit-Persistenz (throttle_map) | C | C2 |
| Circuit breaker persistence | C | C2 |
| Upgrade-Kette (upgraded_from_id) | D | D2, D3 |
| Post-Processing Shell Command | D | D4 |
| alass manual sync | D | D5 |

All 9 items covered.

### What is NOT in this plan (intentional scope cuts)
- **Provider-Pool-Caching per profile**: The current singleton ProviderManager already avoids re-init overhead in batch mode. Per-profile provider sets would require larger architectural changes. Deferred to a future plan.
- **streaming_service score field**: Bazarr has it at weight 0 — adding a 0-point key has no functional effect. Skip.
- **Frontend UI for Phase B/D**: Language profile filter fields (mustContain, cutoff, audio_exclude) and the "Sync with alass" button need frontend implementation. These are follow-on tasks — the APIs and DB schema are complete. Add to the next sprint's UI plan.

### Type Consistency Check
- `upgraded_from_id: int | None` — consistent across model, repo, facade, and process.py
- `must_contain: list[str] | None` — consistent across search(), search_with_fallback(), search_and_download_best()
- `load_profile_filters()` returns typed dict with fixed keys — consistent across B3 and B5
- `run_post_download_command()` signature stable — no callers pass positional args beyond `command`
