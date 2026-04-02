# Phase 4 — Feature Completeness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement key missing features: language profile filters (must_contain/cutoff/audio_exclude) wired through the API, video codec scoring, standalone auto-mode, V9 LLM chat-API support, and circuit breaker state persistence.

**Architecture:** Profile filter columns already exist on the model and migration; the gap is the repository serializer, update allowlist, and route handlers. Video codec weight is added to the in-memory defaults dict — no migration needed (ScoringWeights overrides the default; the default table is code-only). Standalone auto-mode has a complete plan already written; this plan re-uses it verbatim. V9 adds two optional config fields and a parallel `_call_ollama_chat()` method behind a runtime flag. Circuit breaker persistence adds a new DB table and hooks into `record_success()`/`record_failure()`.

**Tech Stack:** Python 3.12, Flask, SQLAlchemy, Alembic, pytest

**Branch:** `phase/4-features`

---

## Codebase State Before You Start

Run a quick orientation check:

```bash
cd /d/Sublarr_Projekt/Sublarr/backend
python -m pytest tests/test_profile_filters.py -v --tb=short
```

Expected: all 8 tests pass. The filter _helper_ layer already works. What is missing is the API exposure and the scoring/persistence tasks below.

---

## File Map

| File | Change |
|------|--------|
| `backend/db/repositories/profiles.py` | Add filter fields to `_row_to_profile()` and `update_profile()` allowed set |
| `backend/routes/profiles.py` | Accept and return filter fields in POST/PUT |
| `backend/db/repositories/scoring.py` | Add `video_codec: 2` to both default weight dicts |
| `backend/wanted_search/scoring.py` | Add codec-match helper and apply it to search results |
| `backend/config.py` | Add `is_standalone_mode()` helper |
| `backend/standalone/__init__.py` | Wire `is_standalone_mode()` through start/get_status |
| `backend/app.py` | Replace inline `standalone_enabled` checks |
| `backend/routes/standalone.py` | Extend status response shape |
| `frontend/src/lib/types.ts` | Extend `StandaloneStatus` interface |
| `frontend/src/pages/Settings/ConnectionsSettings.tsx` | Add `StandaloneSection` component |
| `backend/translation/base.py` | Add `series_context` parameter to abstract `translate_batch` |
| `backend/translation/ollama.py` | Add `use_chat_api`/`system_prompt` config fields + `_call_ollama_chat()` |
| `backend/translation/llm_utils.py` | Fix quality evaluator prompt + score parser |
| `backend/translator.py` | Pass `series_context` through to backend calls |
| `backend/db/models/circuit_breaker.py` | New ORM model `CircuitBreakerState` |
| `backend/db/migrations/versions/d5e6f7a8b9c0_add_circuit_breaker_state.py` | New Alembic migration |
| `backend/circuit_breaker.py` | Add `persist_fn` callback + load state on init |
| `backend/tests/test_profile_filter_api.py` | New — API-level filter field tests |
| `backend/tests/test_video_codec_scoring.py` | New — codec weight + scoring tests |
| `backend/tests/test_standalone_auto_mode.py` | New — already specified in standalone plan |
| `backend/tests/test_ollama_v9.py` | New — chat API path tests |
| `backend/tests/test_circuit_breaker_persistence.py` | New — CB state persistence tests |

---

## Task 1: Expose Profile Filter Fields Through the API

**Context:** The DB model (`LanguageProfile`) already has `must_contain_json`, `must_not_contain_json`, `cutoff_language`, and `audio_exclude_languages_json` columns (migration `c1d2e3f4a5b6` exists). The filter helper `wanted_search/profile_filters.py` is complete and tested. The process.py search loop already calls those helpers. What is missing: the repository's `_row_to_profile()` does not deserialize these fields into the API response, `update_profile()` does not accept them, and the route POST/PUT does not pass them through.

**Files:**
- Modify: `backend/db/repositories/profiles.py` — `_row_to_profile()` (~line 291) and `update_profile()` (~line 112)
- Modify: `backend/routes/profiles.py` — POST and PUT handlers
- Create: `backend/tests/test_profile_filter_api.py`

---

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_profile_filter_api.py`:

```python
"""Tests that profile filter fields round-trip through the repository layer."""
import json
from unittest.mock import MagicMock, patch


def _make_profile_row(
    must_contain_json="[]",
    must_not_contain_json="[]",
    cutoff_language="",
    audio_exclude_languages_json="[]",
):
    """Return a MagicMock that looks like a LanguageProfile ORM row."""
    row = MagicMock()
    row.id = 1
    row.name = "Test"
    row.source_language = "en"
    row.source_language_name = "English"
    row.target_languages_json = '["de"]'
    row.target_language_names_json = '["German"]'
    row.is_default = 0
    row.translation_backend = "ollama"
    row.fallback_chain_json = '["ollama"]'
    row.forced_preference = "disabled"
    row.must_contain_json = must_contain_json
    row.must_not_contain_json = must_not_contain_json
    row.cutoff_language = cutoff_language
    row.audio_exclude_languages_json = audio_exclude_languages_json
    row.created_at = None
    row.updated_at = None
    # Allow _to_dict to work via __dict__
    row.__dict__ = {
        "id": 1,
        "name": "Test",
        "source_language": "en",
        "source_language_name": "English",
        "target_languages_json": '["de"]',
        "target_language_names_json": '["German"]',
        "is_default": 0,
        "translation_backend": "ollama",
        "fallback_chain_json": '["ollama"]',
        "forced_preference": "disabled",
        "must_contain_json": must_contain_json,
        "must_not_contain_json": must_not_contain_json,
        "cutoff_language": cutoff_language,
        "audio_exclude_languages_json": audio_exclude_languages_json,
        "created_at": None,
        "updated_at": None,
    }
    return row


class TestRowToProfileFilterFields:
    def test_must_contain_deserialized(self):
        from db.repositories.profiles import ProfileRepository

        repo = ProfileRepository.__new__(ProfileRepository)
        row = _make_profile_row(must_contain_json='["BluRay","x265"]')
        result = repo._row_to_profile(row)

        assert "must_contain" in result
        assert result["must_contain"] == ["BluRay", "x265"]
        assert "must_contain_json" not in result

    def test_must_not_contain_deserialized(self):
        from db.repositories.profiles import ProfileRepository

        repo = ProfileRepository.__new__(ProfileRepository)
        row = _make_profile_row(must_not_contain_json='["HDCAM","CAM"]')
        result = repo._row_to_profile(row)

        assert "must_not_contain" in result
        assert result["must_not_contain"] == ["HDCAM", "CAM"]
        assert "must_not_contain_json" not in result

    def test_cutoff_language_present(self):
        from db.repositories.profiles import ProfileRepository

        repo = ProfileRepository.__new__(ProfileRepository)
        row = _make_profile_row(cutoff_language="de")
        result = repo._row_to_profile(row)

        assert result["cutoff_language"] == "de"

    def test_audio_exclude_deserialized(self):
        from db.repositories.profiles import ProfileRepository

        repo = ProfileRepository.__new__(ProfileRepository)
        row = _make_profile_row(audio_exclude_languages_json='["de","fr"]')
        result = repo._row_to_profile(row)

        assert "audio_exclude_languages" in result
        assert result["audio_exclude_languages"] == ["de", "fr"]
        assert "audio_exclude_languages_json" not in result

    def test_empty_defaults(self):
        from db.repositories.profiles import ProfileRepository

        repo = ProfileRepository.__new__(ProfileRepository)
        row = _make_profile_row()
        result = repo._row_to_profile(row)

        assert result["must_contain"] == []
        assert result["must_not_contain"] == []
        assert result["cutoff_language"] == ""
        assert result["audio_exclude_languages"] == []

    def test_invalid_json_graceful(self):
        from db.repositories.profiles import ProfileRepository

        repo = ProfileRepository.__new__(ProfileRepository)
        row = _make_profile_row(must_contain_json="not-json")
        result = repo._row_to_profile(row)

        assert result["must_contain"] == []

    def test_update_profile_allows_filter_fields(self):
        """update_profile() must accept filter fields without ignoring them."""
        from db.repositories.profiles import ProfileRepository

        repo = ProfileRepository.__new__(ProfileRepository)

        mock_profile = MagicMock()
        mock_profile.forced_preference = "disabled"

        repo.session = MagicMock()
        repo.session.get.return_value = mock_profile
        repo._commit = MagicMock()
        repo._now = MagicMock(return_value=None)

        repo.update_profile(
            1,
            must_contain=["BluRay"],
            must_not_contain=["HDCAM"],
            cutoff_language="de",
            audio_exclude_languages=["de"],
        )

        # Verify the JSON columns were set on the profile object
        assert mock_profile.must_contain_json == '["BluRay"]'
        assert mock_profile.must_not_contain_json == '["HDCAM"]'
        assert mock_profile.cutoff_language == "de"
        assert mock_profile.audio_exclude_languages_json == '["de"]'
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /d/Sublarr_Projekt/Sublarr/backend && python -m pytest tests/test_profile_filter_api.py -v 2>&1 | head -30
```

Expected: FAIL — `AssertionError: 'must_contain' not in result` (field missing from serializer)

- [ ] **Step 3: Extend `_row_to_profile()` in `backend/db/repositories/profiles.py`**

Open `backend/db/repositories/profiles.py`. After line 320 (the `d["forced_preference"] = ...` line, before `return d`), add:

```python
        # Profile filter fields (Bazarr parity — migration c1d2e3f4a5b6)
        try:
            d["must_contain"] = json.loads(d.pop("must_contain_json", "[]") or "[]")
        except (json.JSONDecodeError, TypeError):
            d["must_contain"] = []
            d.pop("must_contain_json", None)

        try:
            d["must_not_contain"] = json.loads(d.pop("must_not_contain_json", "[]") or "[]")
        except (json.JSONDecodeError, TypeError):
            d["must_not_contain"] = []
            d.pop("must_not_contain_json", None)

        d["cutoff_language"] = d.get("cutoff_language", "") or ""

        try:
            d["audio_exclude_languages"] = json.loads(
                d.pop("audio_exclude_languages_json", "[]") or "[]"
            )
        except (json.JSONDecodeError, TypeError):
            d["audio_exclude_languages"] = []
            d.pop("audio_exclude_languages_json", None)
```

- [ ] **Step 4: Extend `update_profile()` allowed set in `backend/db/repositories/profiles.py`**

In `update_profile()` (~line 118), change the `allowed` set from:

```python
        allowed = {
            "name",
            "source_language",
            "source_language_name",
            "target_languages",
            "target_language_names",
            "translation_backend",
            "fallback_chain",
            "forced_preference",
        }
```

To:

```python
        allowed = {
            "name",
            "source_language",
            "source_language_name",
            "target_languages",
            "target_language_names",
            "translation_backend",
            "fallback_chain",
            "forced_preference",
            "must_contain",
            "must_not_contain",
            "cutoff_language",
            "audio_exclude_languages",
        }
```

Then in the `for key, value in fields.items():` loop, after the `elif key == "fallback_chain":` branch, add:

```python
            elif key == "must_contain":
                profile.must_contain_json = json.dumps(value if isinstance(value, list) else [])
            elif key == "must_not_contain":
                profile.must_not_contain_json = json.dumps(value if isinstance(value, list) else [])
            elif key == "audio_exclude_languages":
                profile.audio_exclude_languages_json = json.dumps(
                    value if isinstance(value, list) else []
                )
```

(The `cutoff_language` key falls through to `setattr(profile, key, value)` automatically since it maps directly to the column name.)

- [ ] **Step 5: Update the POST route to accept filter fields**

In `backend/routes/profiles.py`, in `create_language_profile_endpoint()`, after the `forced_preference = data.get(...)` line (~line 119), add:

```python
    must_contain = data.get("must_contain", [])
    must_not_contain = data.get("must_not_contain", [])
    cutoff_language = data.get("cutoff_language", "")
    audio_exclude_languages = data.get("audio_exclude_languages", [])
```

Then change the `create_language_profile(...)` call to:

```python
        profile_id = create_language_profile(
            name,
            source_lang,
            source_name,
            target_langs,
            target_names,
            translation_backend=translation_backend,
            fallback_chain=fallback_chain,
            forced_preference=forced_preference,
            must_contain=must_contain,
            must_not_contain=must_not_contain,
            cutoff_language=cutoff_language,
            audio_exclude_languages=audio_exclude_languages,
        )
```

- [ ] **Step 6: Update `create_language_profile()` in `db/profiles.py` and `ProfileRepository.create_profile()`**

In `backend/db/profiles.py`, extend `create_language_profile()`:

```python
def create_language_profile(
    name: str,
    source_lang: str,
    source_name: str,
    target_langs: list,
    target_names: list,
    translation_backend: str = "ollama",
    fallback_chain: list = None,
    forced_preference: str = "disabled",
    must_contain: list = None,
    must_not_contain: list = None,
    cutoff_language: str = "",
    audio_exclude_languages: list = None,
) -> int:
    """Create a new language profile. Returns the profile ID."""
    return _get_repo().create_profile(
        name,
        source_lang,
        source_name,
        target_langs,
        target_names,
        translation_backend,
        fallback_chain,
        forced_preference,
        must_contain=must_contain or [],
        must_not_contain=must_not_contain or [],
        cutoff_language=cutoff_language or "",
        audio_exclude_languages=audio_exclude_languages or [],
    )
```

In `backend/db/repositories/profiles.py`, extend `create_profile()` signature and body:

```python
    def create_profile(
        self,
        name: str,
        source_lang: str,
        source_name: str,
        target_langs: list,
        target_names: list,
        translation_backend: str = "ollama",
        fallback_chain: list = None,
        forced_preference: str = "disabled",
        must_contain: list = None,
        must_not_contain: list = None,
        cutoff_language: str = "",
        audio_exclude_languages: list = None,
    ) -> int:
        """Create a new language profile. Returns the profile ID."""
        if forced_preference not in VALID_FORCED_PREFERENCES:
            raise ValueError(
                f"Invalid forced_preference '{forced_preference}'. "
                f"Must be one of: {VALID_FORCED_PREFERENCES}"
            )
        if fallback_chain is None:
            fallback_chain = [translation_backend]
        now = self._now()

        profile = LanguageProfile(
            name=name,
            source_language=source_lang,
            source_language_name=source_name,
            target_languages_json=json.dumps(target_langs),
            target_language_names_json=json.dumps(target_names),
            translation_backend=translation_backend,
            fallback_chain_json=json.dumps(fallback_chain),
            forced_preference=forced_preference,
            is_default=0,
            must_contain_json=json.dumps(must_contain or []),
            must_not_contain_json=json.dumps(must_not_contain or []),
            cutoff_language=cutoff_language or "",
            audio_exclude_languages_json=json.dumps(audio_exclude_languages or []),
            created_at=now,
            updated_at=now,
        )
        self.session.add(profile)
        self._commit()
        return profile.id
```

- [ ] **Step 7: Update the PUT route to accept filter fields**

In `backend/routes/profiles.py`, in `update_language_profile_endpoint()`, extend the list of keys pulled from `data`:

```python
    for key in (
        "name",
        "source_language",
        "source_language_name",
        "target_languages",
        "target_language_names",
        "translation_backend",
        "fallback_chain",
        "forced_preference",
        "must_contain",
        "must_not_contain",
        "cutoff_language",
        "audio_exclude_languages",
    ):
        if key in data:
            fields[key] = data[key]
```

- [ ] **Step 8: Run all profile filter tests**

```bash
cd /d/Sublarr_Projekt/Sublarr/backend && python -m pytest tests/test_profile_filter_api.py tests/test_profile_filters.py -v
```

Expected: all tests pass

- [ ] **Step 9: Commit**

```bash
cd /d/Sublarr_Projekt/Sublarr
git add backend/db/repositories/profiles.py backend/db/profiles.py backend/routes/profiles.py backend/tests/test_profile_filter_api.py
git commit -m "feat: expose profile filter fields (must_contain/cutoff/audio_exclude) in API"
```

---

## Task 2: Video Codec Scoring

**Context:** `_DEFAULT_EPISODE_WEIGHTS` and `_DEFAULT_MOVIE_WEIGHTS` in `backend/db/repositories/scoring.py` define the baseline scoring keys. Currently neither has `video_codec`. The spec requires weight value `2`. No DB migration is needed — these are in-code defaults; the `ScoringWeights` DB table only stores _overrides_, and the defaults are merged at read-time in `get_all_scoring_weights()`.

The wanted search pipeline calls `search_and_download_best()` in `providers/__init__.py`. Provider result scoring happens in `providers/base.py`. The codec of the video file is available from `ffprobe_data` (see `FfprobeCache` model). The codec string match (`x264`, `x265`, `av1`, `hevc`) needs to be applied as a score bonus when the subtitle result's `release_info` contains the video file's codec family.

**Files:**
- Modify: `backend/db/repositories/scoring.py` — add `video_codec: 2` to both default dicts
- Modify: `backend/wanted_search/scoring.py` — add `apply_video_codec_bonus()` helper
- Create: `backend/tests/test_video_codec_scoring.py`

---

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_video_codec_scoring.py`:

```python
"""Tests for video_codec weight in defaults and codec-match scoring."""


class TestVideoCodecWeightDefault:
    def test_episode_weights_include_video_codec(self):
        from db.repositories.scoring import _DEFAULT_EPISODE_WEIGHTS

        assert "video_codec" in _DEFAULT_EPISODE_WEIGHTS
        assert _DEFAULT_EPISODE_WEIGHTS["video_codec"] == 2

    def test_movie_weights_include_video_codec(self):
        from db.repositories.scoring import _DEFAULT_MOVIE_WEIGHTS

        assert "video_codec" in _DEFAULT_MOVIE_WEIGHTS
        assert _DEFAULT_MOVIE_WEIGHTS["video_codec"] == 2

    def test_get_all_scoring_weights_includes_video_codec(self):
        """get_all_scoring_weights() must include video_codec in both types."""
        from unittest.mock import patch, MagicMock

        mock_session = MagicMock()
        mock_session.execute.return_value.scalars.return_value.all.return_value = []

        with patch("db.repositories.scoring.BaseRepository.__init__", return_value=None):
            from db.repositories.scoring import ScoringRepository

            repo = ScoringRepository.__new__(ScoringRepository)
            repo.session = mock_session

            weights = repo.get_all_scoring_weights()

        assert weights["episode"]["video_codec"] == 2
        assert weights["movie"]["video_codec"] == 2


class TestApplyVideoCodecBonus:
    def _make_result(self, release_info: str, score: int = 100) -> dict:
        return {"release_info": release_info, "score": score}

    def test_x265_match_adds_bonus(self):
        from wanted_search.scoring import apply_video_codec_bonus

        results = [self._make_result("Show.S01E01.BluRay.x265")]
        apply_video_codec_bonus(results, video_codec="x265", weight=2)
        assert results[0]["score"] == 102

    def test_x264_match_adds_bonus(self):
        from wanted_search.scoring import apply_video_codec_bonus

        results = [self._make_result("Show.S01E01.BluRay.x264")]
        apply_video_codec_bonus(results, video_codec="x264", weight=2)
        assert results[0]["score"] == 102

    def test_hevc_maps_to_x265_family(self):
        """HEVC release tags should match when video codec is x265/hevc."""
        from wanted_search.scoring import apply_video_codec_bonus

        results = [self._make_result("Show.S01E01.BluRay.HEVC")]
        apply_video_codec_bonus(results, video_codec="hevc", weight=2)
        assert results[0]["score"] == 102

    def test_no_match_no_change(self):
        from wanted_search.scoring import apply_video_codec_bonus

        results = [self._make_result("Show.S01E01.BluRay.x264")]
        apply_video_codec_bonus(results, video_codec="x265", weight=2)
        assert results[0]["score"] == 100

    def test_empty_codec_no_change(self):
        from wanted_search.scoring import apply_video_codec_bonus

        results = [self._make_result("Show.S01E01.BluRay.x265")]
        apply_video_codec_bonus(results, video_codec="", weight=2)
        assert results[0]["score"] == 100

    def test_empty_results_no_error(self):
        from wanted_search.scoring import apply_video_codec_bonus

        apply_video_codec_bonus([], video_codec="x265", weight=2)  # must not raise

    def test_av1_match(self):
        from wanted_search.scoring import apply_video_codec_bonus

        results = [self._make_result("Show.S01E01.BluRay.AV1")]
        apply_video_codec_bonus(results, video_codec="av1", weight=2)
        assert results[0]["score"] == 102
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /d/Sublarr_Projekt/Sublarr/backend && python -m pytest tests/test_video_codec_scoring.py -v 2>&1 | head -25
```

Expected: FAIL — `AssertionError: 'video_codec' not in _DEFAULT_EPISODE_WEIGHTS`

- [ ] **Step 3: Add `video_codec` to default weight dicts**

In `backend/db/repositories/scoring.py`, change `_DEFAULT_EPISODE_WEIGHTS` from:

```python
_DEFAULT_EPISODE_WEIGHTS = {
    "hash": 359,
    "series": 180,
    "year": 90,
    "season": 30,
    "episode": 30,
    "release_group": 14,
    "source": 7,
    "audio_codec": 3,
    "resolution": 2,
    "hearing_impaired": 1,
    "format_bonus": 50,
}
```

To:

```python
_DEFAULT_EPISODE_WEIGHTS = {
    "hash": 359,
    "series": 180,
    "year": 90,
    "season": 30,
    "episode": 30,
    "release_group": 14,
    "source": 7,
    "audio_codec": 3,
    "resolution": 2,
    "video_codec": 2,
    "hearing_impaired": 1,
    "format_bonus": 50,
}
```

And change `_DEFAULT_MOVIE_WEIGHTS` from:

```python
_DEFAULT_MOVIE_WEIGHTS = {
    "hash": 119,
    "title": 60,
    "year": 30,
    "release_group": 13,
    "source": 7,
    "audio_codec": 3,
    "resolution": 2,
    "hearing_impaired": 1,
    "format_bonus": 50,
}
```

To:

```python
_DEFAULT_MOVIE_WEIGHTS = {
    "hash": 119,
    "title": 60,
    "year": 30,
    "release_group": 13,
    "source": 7,
    "audio_codec": 3,
    "resolution": 2,
    "video_codec": 2,
    "hearing_impaired": 1,
    "format_bonus": 50,
}
```

- [ ] **Step 4: Add `apply_video_codec_bonus()` to `backend/wanted_search/scoring.py`**

Append to the end of `backend/wanted_search/scoring.py`:

```python
# Codec family aliases — result release_info uses various spellings
_CODEC_ALIASES: dict[str, list[str]] = {
    "x265": ["x265", "hevc", "h265"],
    "hevc": ["x265", "hevc", "h265"],
    "h265": ["x265", "hevc", "h265"],
    "x264": ["x264", "h264", "avc"],
    "h264": ["x264", "h264", "avc"],
    "avc": ["x264", "h264", "avc"],
    "av1": ["av1"],
}


def apply_video_codec_bonus(results: list[dict], video_codec: str, weight: int) -> None:
    """Add weight to results whose release_info contains the video file's codec.

    Performs in-place mutation on the results list (same pattern as _apply_fansub_rules).
    Case-insensitive substring match against release_info.

    Args:
        results: List of result dicts with 'release_info' and 'score' keys.
        video_codec: Codec string from ffprobe (e.g. "x265", "hevc", "av1").
        weight: Score points to add on a match.
    """
    if not video_codec or not weight:
        return

    codec_lower = video_codec.lower()
    tags = _CODEC_ALIASES.get(codec_lower, [codec_lower])

    for result in results:
        info = result.get("release_info", "").lower()
        if any(tag in info for tag in tags):
            result["score"] += weight
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd /d/Sublarr_Projekt/Sublarr/backend && python -m pytest tests/test_video_codec_scoring.py -v
```

Expected: all 8 tests pass

- [ ] **Step 6: Commit**

```bash
cd /d/Sublarr_Projekt/Sublarr
git add backend/db/repositories/scoring.py backend/wanted_search/scoring.py backend/tests/test_video_codec_scoring.py
git commit -m "feat: add video_codec weight (2) to scoring defaults and apply_video_codec_bonus() helper"
```

---

## Task 3: Standalone Auto-Mode

**Context:** A complete, detailed implementation plan already exists at `docs/superpowers/plans/2026-03-29-standalone-auto-mode.md`. It covers all 6 tasks (backend helper, app.py wiring, status extension, TypeScript type, frontend StandaloneSection component, pre-PR checks).

**Do not re-implement — execute that plan directly.**

- [ ] **Step 1: Open and read the existing plan**

```
docs/superpowers/plans/2026-03-29-standalone-auto-mode.md
```

- [ ] **Step 2: Execute Tasks 1–5 from that plan in order**

Each task in the standalone plan has its own test-write → run-fail → implement → run-pass → commit cycle. Follow it exactly.

- [ ] **Step 3: Run the standalone pre-PR check from that plan (Task 6)**

```bash
cd /d/Sublarr_Projekt/Sublarr/backend && python -m pytest --tb=short -q \
  --ignore=tests/performance \
  --ignore=tests/integration/test_provider_pipeline.py \
  --ignore=tests/test_video_sync.py \
  --ignore=tests/test_translation_backends.py \
  -k "not (test_sonarr_download_webhook or test_radarr_download_webhook or test_parse_llm_response_too_many_merge or test_record_backend_success)"
```

Expected: all pass

---

## Task 4: V9 LLM Integration (Ollama Chat API)

**Context:** `V9_INTEGRATION.md` specifies this feature fully. V9 (TranslateGemma-12B) requires `/api/chat` instead of `/api/generate`. The change adds two optional config fields (`use_chat_api`, `system_prompt`) and a parallel call path. When `use_chat_api=False` (default), behaviour is 100% identical to today. The `translate_batch()` abstract interface gains an optional `series_context` parameter that all other backends can ignore.

**Files:**
- Modify: `backend/translation/base.py` — add `series_context` parameter to abstract `translate_batch`
- Modify: `backend/translation/ollama.py` — add config fields, `_use_chat_api` property, `_system_prompt` property, `_build_system_prompt()`, `_call_ollama_chat()`, dispatch in `translate_batch()`
- Modify: `backend/translation/llm_utils.py` — fix quality evaluator prompt and score parser
- Modify: `backend/translator.py` — pass `series_context` through to backend
- Create: `backend/tests/test_ollama_v9.py`

---

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_ollama_v9.py`:

```python
"""Tests for Ollama V9 chat-API integration.

Tests that:
- use_chat_api=False → _call_ollama() is used (legacy path)
- use_chat_api=True  → _call_ollama_chat() is used (V9 path)
- system_prompt config field is respected
- series_context is injected into system prompt when provided
- Both backends remain backwards-compatible
"""
from unittest.mock import MagicMock, patch


def _make_backend(use_chat_api: bool = False, system_prompt: str = "") -> "OllamaBackend":
    from translation.ollama import OllamaBackend

    backend = OllamaBackend.__new__(OllamaBackend)
    backend.config = {
        "url": "http://localhost:11434",
        "model": "test-model",
        "temperature": "0.3",
        "request_timeout": "10",
        "max_retries": "1",
        "backoff_base": "1",
        "batch_size": "15",
        "use_chat_api": "true" if use_chat_api else "false",
        "system_prompt": system_prompt,
    }
    return backend


class TestOllamaV9ConfigFields:
    def test_use_chat_api_false_by_default(self):
        backend = _make_backend()
        assert backend._use_chat_api is False

    def test_use_chat_api_true_when_set(self):
        backend = _make_backend(use_chat_api=True)
        assert backend._use_chat_api is True

    def test_system_prompt_default(self):
        backend = _make_backend()
        # Default system_prompt is empty string — means auto-generate
        assert isinstance(backend._system_prompt, str)

    def test_system_prompt_from_config(self):
        backend = _make_backend(system_prompt="You are a translator.")
        assert backend._system_prompt == "You are a translator."


class TestBuildSystemPrompt:
    def test_no_series_context(self):
        backend = _make_backend(system_prompt="Base prompt.")
        result = backend._build_system_prompt(series_context=None)
        assert result == "Base prompt."

    def test_with_series_context(self):
        backend = _make_backend(system_prompt="Base prompt. {series_context}")
        result = backend._build_system_prompt(series_context="Serie: Naruto. Genre: Action.")
        assert "Naruto" in result
        assert "{series_context}" not in result

    def test_no_placeholder_context_appended(self):
        """When system_prompt has no {series_context} placeholder, context is appended."""
        backend = _make_backend(system_prompt="Base prompt.")
        result = backend._build_system_prompt(series_context="Serie: Naruto.")
        assert "Naruto" in result


class TestChatApiDispatch:
    def test_legacy_path_calls_generate(self):
        """use_chat_api=False → _call_ollama() is called, not _call_ollama_chat()."""
        backend = _make_backend(use_chat_api=False)
        backend._call_ollama = MagicMock(return_value="1: Hallo")
        backend._call_ollama_chat = MagicMock()

        from unittest.mock import patch as _patch

        with _patch("translation.llm_utils.parse_llm_response", return_value=["Hallo"]):
            with _patch("translation.llm_utils.has_cjk_hallucination", return_value=False):
                backend.translate_batch(["Hello"], "en", "de")

        backend._call_ollama.assert_called_once()
        backend._call_ollama_chat.assert_not_called()

    def test_chat_path_calls_chat_api(self):
        """use_chat_api=True → _call_ollama_chat() is called, not _call_ollama()."""
        backend = _make_backend(use_chat_api=True, system_prompt="You translate.")
        backend._call_ollama = MagicMock()
        backend._call_ollama_chat = MagicMock(return_value="Hallo")

        from unittest.mock import patch as _patch

        with _patch("translation.llm_utils.parse_llm_response", return_value=["Hallo"]):
            with _patch("translation.llm_utils.has_cjk_hallucination", return_value=False):
                backend.translate_batch(["Hello"], "en", "de")

        backend._call_ollama_chat.assert_called_once()
        backend._call_ollama.assert_not_called()

    def test_series_context_passed_through(self):
        """series_context is forwarded to _build_system_prompt() when use_chat_api=True."""
        backend = _make_backend(use_chat_api=True, system_prompt="Base. {series_context}")
        backend._call_ollama_chat = MagicMock(return_value="Hallo")

        from unittest.mock import patch as _patch

        with _patch("translation.llm_utils.parse_llm_response", return_value=["Hallo"]):
            with _patch("translation.llm_utils.has_cjk_hallucination", return_value=False):
                backend.translate_batch(
                    ["Hello"], "en", "de", series_context="Serie: Naruto."
                )

        call_args = backend._call_ollama_chat.call_args
        system_arg = call_args[0][0]  # first positional arg
        assert "Naruto" in system_arg


class TestCallOllamaChat:
    def test_returns_message_content(self):
        """_call_ollama_chat() extracts data['message']['content'] from the API response."""
        import requests

        backend = _make_backend(use_chat_api=True)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "message": {"content": "Hallo Welt"},
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("requests.post", return_value=mock_resp):
            result = backend._call_ollama_chat("system text", "user text")

        assert result == "Hallo Welt"

    def test_raises_on_missing_message_key(self):
        backend = _make_backend(use_chat_api=True)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"error": "model not found"}
        mock_resp.raise_for_status = MagicMock()

        with patch("requests.post", return_value=mock_resp):
            import pytest
            with pytest.raises(RuntimeError, match="message"):
                backend._call_ollama_chat("system text", "user text")
```

- [ ] **Step 2: Run tests to verify failure**

```bash
cd /d/Sublarr_Projekt/Sublarr/backend && python -m pytest tests/test_ollama_v9.py -v 2>&1 | head -30
```

Expected: FAIL — `AttributeError: 'OllamaBackend' object has no attribute '_use_chat_api'`

- [ ] **Step 3: Add `series_context` to the abstract interface in `backend/translation/base.py`**

Change the abstract `translate_batch` signature from:

```python
    @abstractmethod
    def translate_batch(
        self,
        lines: list[str],
        source_lang: str,
        target_lang: str,
        glossary_entries: list[dict] | None = None,
    ) -> TranslationResult:
```

To:

```python
    @abstractmethod
    def translate_batch(
        self,
        lines: list[str],
        source_lang: str,
        target_lang: str,
        glossary_entries: list[dict] | None = None,
        series_context: str | None = None,
    ) -> TranslationResult:
```

- [ ] **Step 4: Add V9 config fields to `OllamaBackend.config_fields` in `backend/translation/ollama.py`**

In `OllamaBackend.config_fields` (after the existing `max_retries` dict, ~line 78), add:

```python
        {
            "key": "use_chat_api",
            "label": "Chat API (V9+)",
            "type": "checkbox",
            "required": False,
            "default": "false",
            "help": "For V9+ models: use /api/chat instead of /api/generate",
        },
        {
            "key": "system_prompt",
            "label": "System Prompt",
            "type": "textarea",
            "required": False,
            "default": (
                "Du bist ein spezialisierter Anime-Untertitel-Übersetzer. "
                "Übersetze englische Anime-Untertitel präzise und natürlich ins Deutsche. "
                "Verwende informelle Sprache (du-Form). Behalte Charakternamen und "
                "Eigennamen unverändert. Keine Erklärungen oder Kommentare — nur die Übersetzung."
            ),
            "help": (
                "System prompt for chat API mode. "
                "Use {series_context} as placeholder for dynamic series info."
            ),
        },
```

- [ ] **Step 5: Add property accessors for V9 config in `backend/translation/ollama.py`**

After the `_backoff_base` property (~line 145), add:

```python
    @property
    def _use_chat_api(self) -> bool:
        val = self.config.get("use_chat_api", "false")
        if isinstance(val, bool):
            return val
        return str(val).lower() in ("true", "1", "yes")

    @property
    def _system_prompt(self) -> str:
        return self.config.get("system_prompt", "")

    def _build_system_prompt(self, series_context: str | None) -> str:
        """Build the system prompt, optionally injecting series context.

        If the system_prompt config contains '{series_context}', replaces it.
        Otherwise appends series_context after the base prompt (space-separated).
        Falls back to a hardcoded anime-translation default if prompt is empty.
        """
        base = self._system_prompt or (
            "Du bist ein spezialisierter Anime-Untertitel-Übersetzer. "
            "Übersetze englische Anime-Untertitel präzise und natürlich ins Deutsche. "
            "Verwende informelle Sprache (du-Form). Behalte Charakternamen und "
            "Eigennamen unverändert. Keine Erklärungen oder Kommentare — nur die Übersetzung."
        )
        if not series_context:
            return base.replace("{series_context}", "").strip()
        if "{series_context}" in base:
            return base.replace("{series_context}", series_context)
        return f"{base} {series_context}"
```

- [ ] **Step 6: Add `_call_ollama_chat()` to `backend/translation/ollama.py`**

After the existing `_call_ollama()` method (after line ~328), add:

```python
    def _call_ollama_chat(self, system_prompt: str, user_prompt: str) -> str:
        """Make a single Ollama Chat API call (/api/chat).

        Used for V9+ models trained with a chat template (e.g. Gemma-3).
        Provides explicit system/user turn separation.

        Returns:
            Model response text (message.content)

        Raises:
            RuntimeError: On API errors or missing response fields
            requests.RequestException: On network errors
        """
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": {
                "temperature": self._temperature,
                "num_predict": 4096,
                "num_ctx": 4096,
            },
        }
        resp = requests.post(
            f"{self._url}/api/chat",
            json=payload,
            timeout=self._request_timeout,
        )

        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After")
            try:
                wait_seconds = int(retry_after) if retry_after else 60
            except ValueError:
                wait_seconds = 60
            raise RuntimeError(f"Ollama rate limited, retry after {wait_seconds}s")

        resp.raise_for_status()

        try:
            data = resp.json()
        except ValueError:
            raise RuntimeError("Ollama returned invalid JSON response")

        if "error" in data:
            raise RuntimeError(f"Ollama error: {data['error']}")

        if "message" not in data or "content" not in data.get("message", {}):
            raise RuntimeError(
                f"Ollama chat response missing 'message.content': {list(data.keys())}"
            )

        return data["message"]["content"].strip()
```

- [ ] **Step 7: Update `translate_batch()` to accept `series_context` and dispatch**

In `backend/translation/ollama.py`, change the `translate_batch()` signature from:

```python
    def translate_batch(
        self,
        lines: list[str],
        source_lang: str,
        target_lang: str,
        glossary_entries: list[dict] | None = None,
    ) -> TranslationResult:
```

To:

```python
    def translate_batch(
        self,
        lines: list[str],
        source_lang: str,
        target_lang: str,
        glossary_entries: list[dict] | None = None,
        series_context: str | None = None,
    ) -> TranslationResult:
```

Then replace the `prompt = build_translation_prompt(...)` + `response = self._call_ollama(prompt)` block inside the retry loop with:

```python
                if self._use_chat_api:
                    system = self._build_system_prompt(series_context)
                    user = build_translation_prompt(
                        lines, source_lang, target_lang, glossary_entries
                    )
                    response = self._call_ollama_chat(system, user)
                else:
                    prompt = build_translation_prompt(
                        lines, source_lang, target_lang, glossary_entries
                    )
                    response = self._call_ollama(prompt)
                parsed = parse_llm_response(response, len(lines))
```

(The variable `response` replaces the existing local variable that was just called `response` but only existed implicitly in the original code flow. Make sure `parsed = parse_llm_response(response, len(lines))` still appears right after.)

- [ ] **Step 8: Update `_translate_singles()` to also dispatch via chat API**

In `_translate_singles()`, change the line:

```python
                    response = self._call_ollama(prompt)
```

To:

```python
                    if self._use_chat_api:
                        system = self._build_system_prompt(series_context=None)
                        response = self._call_ollama_chat(system, prompt)
                    else:
                        response = self._call_ollama(prompt)
```

And update its signature to accept `series_context`:

```python
    def _translate_singles(
        self,
        lines: list[str],
        source_lang: str,
        target_lang: str,
        glossary_entries: list[dict] | None,
        start_time: float,
        series_context: str | None = None,
    ) -> TranslationResult:
```

Update the fallback call site inside `translate_batch()` to pass `series_context`:

```python
        return self._translate_singles(
            lines, source_lang, target_lang, glossary_entries, start_time, series_context
        )
```

- [ ] **Step 9: Run all V9 tests**

```bash
cd /d/Sublarr_Projekt/Sublarr/backend && python -m pytest tests/test_ollama_v9.py -v
```

Expected: all tests pass

- [ ] **Step 10: Verify no existing Ollama tests regressed**

```bash
cd /d/Sublarr_Projekt/Sublarr/backend && python -m pytest tests/ -k "ollama" -v --tb=short 2>&1 | tail -20
```

Expected: all pass

- [ ] **Step 11: Commit**

```bash
cd /d/Sublarr_Projekt/Sublarr
git add backend/translation/base.py backend/translation/ollama.py backend/tests/test_ollama_v9.py
git commit -m "feat: add Ollama chat API (V9) support with use_chat_api flag and series_context"
```

---

## Task 5: Circuit Breaker State Persistence

**Context:** `CircuitBreaker` in `backend/circuit_breaker.py` stores all state (`_state`, `_failure_count`, `_last_failure_time`) in memory only. After a server restart, all breakers reset to CLOSED with zero failures, losing the "OPEN" state of a recently-failing provider. The fix adds a new DB table (`circuit_breaker_states`), a new Alembic migration, and a `persist_fn` callback injected into `CircuitBreaker` at construction time. The `CircuitBreakerRegistry` (or wherever breakers are created — `providers/__init__.py`) injects the persist function.

**Files:**
- Create: `backend/db/models/circuit_breaker.py`
- Create: `backend/db/migrations/versions/d5e6f7a8b9c0_add_circuit_breaker_state.py`
- Modify: `backend/circuit_breaker.py` — add `persist_fn` + `load_state()` method
- Create: `backend/tests/test_circuit_breaker_persistence.py`

---

- [ ] **Step 1: Identify head migration revision**

```bash
cd /d/Sublarr_Projekt/Sublarr/backend && python -m alembic heads
```

Note the output — it becomes the `down_revision` for the new migration. Example output: `c0d1e2f3a4b5 (head)`. Use that exact string.

- [ ] **Step 2: Write failing tests**

Create `backend/tests/test_circuit_breaker_persistence.py`:

```python
"""Tests for CircuitBreaker state persistence via persist_fn callback."""
import time
from unittest.mock import MagicMock

from circuit_breaker import CircuitBreaker, CircuitState


class TestCircuitBreakerPersistFn:
    def test_persist_fn_called_on_record_failure(self):
        persist = MagicMock()
        cb = CircuitBreaker("test", failure_threshold=3, cooldown_seconds=60, persist_fn=persist)

        cb.record_failure()

        persist.assert_called_once()
        call_kwargs = persist.call_args[1] if persist.call_args[1] else {}
        call_args = persist.call_args[0]
        # persist_fn called with (name, state, failure_count, last_failure_time)
        assert len(call_args) >= 1 or len(call_kwargs) >= 1

    def test_persist_fn_called_on_record_success(self):
        persist = MagicMock()
        cb = CircuitBreaker("test", failure_threshold=1, cooldown_seconds=60, persist_fn=persist)
        cb.record_failure()  # opens breaker
        persist.reset_mock()

        cb.record_success()

        persist.assert_called_once()

    def test_persist_fn_called_on_reset(self):
        persist = MagicMock()
        cb = CircuitBreaker("test", failure_threshold=1, cooldown_seconds=60, persist_fn=persist)
        cb.record_failure()
        persist.reset_mock()

        cb.reset()

        persist.assert_called_once()

    def test_no_persist_fn_works_normally(self):
        """CircuitBreaker without persist_fn must not raise."""
        cb = CircuitBreaker("test", failure_threshold=2, cooldown_seconds=60)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_load_state_restores_open(self):
        """load_state() with OPEN state makes the breaker immediately open."""
        cb = CircuitBreaker("test", failure_threshold=5, cooldown_seconds=60)
        cb.load_state(
            state=CircuitState.OPEN,
            failure_count=5,
            last_failure_time=time.monotonic() - 10,  # 10s ago, within cooldown
        )
        assert cb.state == CircuitState.OPEN
        assert not cb.allow_request()

    def test_load_state_restores_closed(self):
        cb = CircuitBreaker("test", failure_threshold=5, cooldown_seconds=60)
        cb.load_state(
            state=CircuitState.CLOSED,
            failure_count=0,
            last_failure_time=None,
        )
        assert cb.state == CircuitState.CLOSED
        assert cb.allow_request()

    def test_load_state_expired_open_becomes_half_open(self):
        """If OPEN state is loaded but cooldown already elapsed, state becomes HALF_OPEN."""
        cb = CircuitBreaker("test", failure_threshold=5, cooldown_seconds=10)
        cb.load_state(
            state=CircuitState.OPEN,
            failure_count=5,
            last_failure_time=time.monotonic() - 20,  # 20s ago > 10s cooldown
        )
        # Accessing .state triggers the lazy OPEN→HALF_OPEN transition
        assert cb.state == CircuitState.HALF_OPEN

    def test_persist_fn_signature(self):
        """persist_fn receives (name: str, state: str, failure_count: int, last_failure_time: float|None)."""
        captured = {}

        def my_persist(name, state, failure_count, last_failure_time):
            captured.update(
                name=name,
                state=state,
                failure_count=failure_count,
                last_failure_time=last_failure_time,
            )

        cb = CircuitBreaker(
            "prov_test", failure_threshold=1, cooldown_seconds=60, persist_fn=my_persist
        )
        cb.record_failure()

        assert captured["name"] == "prov_test"
        assert captured["state"] == CircuitState.OPEN
        assert captured["failure_count"] == 1
```

- [ ] **Step 3: Run to verify failure**

```bash
cd /d/Sublarr_Projekt/Sublarr/backend && python -m pytest tests/test_circuit_breaker_persistence.py -v 2>&1 | head -20
```

Expected: FAIL — `TypeError: CircuitBreaker.__init__() got an unexpected keyword argument 'persist_fn'`

- [ ] **Step 4: Create the ORM model**

Create `backend/db/models/circuit_breaker.py`:

```python
"""ORM model for circuit breaker state persistence.

Stores per-provider circuit breaker state across restarts.
State is loaded at startup and persisted on each state transition.
"""

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from extensions import db


class CircuitBreakerState(db.Model):
    """Persisted circuit breaker state for a single provider/backend."""

    __tablename__ = "circuit_breaker_states"

    name: Mapped[str] = mapped_column(Text, primary_key=True)
    state: Mapped[str] = mapped_column(Text, nullable=False, default="closed")
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_failure_epoch: Mapped[float | None] = mapped_column(Float, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("idx_cb_state_updated", "updated_at"),)
```

- [ ] **Step 5: Register the model in `backend/db/models/__init__.py`**

Open `backend/db/models/__init__.py` and add:

```python
from db.models.circuit_breaker import CircuitBreakerState  # noqa: F401
```

(If no `__init__.py` exists there, check what pattern the other models use — look at how `LanguageProfile` is imported in other model files and follow the same pattern.)

- [ ] **Step 6: Create the Alembic migration**

First get the current head:

```bash
cd /d/Sublarr_Projekt/Sublarr/backend && python -m alembic heads
```

Use the printed hash as `down_revision` below (replacing `c0d1e2f3a4b5`):

Create `backend/db/migrations/versions/d5e6f7a8b9c0_add_circuit_breaker_state.py`:

```python
"""Add circuit_breaker_states table for persistent CB state across restarts.

Revision ID: d5e6f7a8b9c0
Revises: c0d1e2f3a4b5
Create Date: 2026-04-02
"""

from alembic import op
import sqlalchemy as sa

revision = "d5e6f7a8b9c0"
down_revision = "c0d1e2f3a4b5"  # replace with actual head if different
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "circuit_breaker_states",
        sa.Column("name", sa.Text, primary_key=True),
        sa.Column("state", sa.Text, nullable=False, server_default="closed"),
        sa.Column("failure_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_failure_epoch", sa.Float, nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_cb_state_updated", "circuit_breaker_states", ["updated_at"])


def downgrade() -> None:
    op.drop_index("idx_cb_state_updated", table_name="circuit_breaker_states")
    op.drop_table("circuit_breaker_states")
```

- [ ] **Step 7: Run the migration**

```bash
cd /d/Sublarr_Projekt/Sublarr/backend && python -m alembic upgrade head
```

Expected: `Running upgrade c0d1e2f3a4b5 -> d5e6f7a8b9c0, Add circuit_breaker_states table`

- [ ] **Step 8: Add `persist_fn` and `load_state()` to `backend/circuit_breaker.py`**

Change `CircuitBreaker.__init__()` from:

```python
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        cooldown_seconds: int = 60,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float | None = None
        self._lock = threading.Lock()
```

To:

```python
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        cooldown_seconds: int = 60,
        persist_fn=None,
    ) -> None:
        """
        Args:
            name: Human-readable name for logging.
            failure_threshold: Consecutive failures before OPEN transition.
            cooldown_seconds: Seconds in OPEN before HALF_OPEN probe.
            persist_fn: Optional callable(name, state, failure_count, last_failure_time)
                called after every state-changing operation. Use this to persist
                state to a DB so it survives restarts.
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self._persist_fn = persist_fn

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float | None = None
        self._lock = threading.Lock()
```

Add `_call_persist()` private method after `__init__`:

```python
    def _call_persist(self) -> None:
        """Invoke the persist callback if configured. Never raises."""
        if self._persist_fn is None:
            return
        try:
            self._persist_fn(
                self.name,
                self._state,
                self._failure_count,
                self._last_failure_time,
            )
        except Exception as e:
            logger.warning("CircuitBreaker[%s]: persist_fn failed: %s", self.name, e)
```

Add `load_state()` method:

```python
    def load_state(
        self,
        state: CircuitState,
        failure_count: int,
        last_failure_time: float | None,
    ) -> None:
        """Restore persisted state (called at startup, before any requests).

        The lazy OPEN→HALF_OPEN transition applies immediately on the next
        `.state` property access, so expired OPEN states self-heal correctly.

        Args:
            state: The persisted CircuitState value.
            failure_count: Number of consecutive failures at time of persist.
            last_failure_time: time.monotonic()-equivalent epoch at last failure,
                or None if no failure recorded.
        """
        with self._lock:
            self._state = CircuitState(state) if isinstance(state, str) else state
            self._failure_count = failure_count
            self._last_failure_time = last_failure_time
            logger.info(
                "CircuitBreaker[%s]: state restored from DB — %s (failures: %d)",
                self.name,
                self._state.value,
                self._failure_count,
            )
```

Now add `self._call_persist()` at the end of each state-changing method. In `record_success()`, after `self._last_failure_time = None`, add `self._call_persist()`. In `record_failure()`, after the state transitions (at the end of the `with self._lock:` block), add `self._call_persist()`. In `reset()`, after `self._last_failure_time = None`, add `self._call_persist()`.

Final structure of `record_success()`:

```python
    def record_success(self) -> None:
        """Record a successful call — resets the breaker to CLOSED."""
        with self._lock:
            if self._state != CircuitState.CLOSED:
                logger.info(
                    "CircuitBreaker[%s]: %s → CLOSED (success)",
                    self.name,
                    self._state.value,
                )
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._last_failure_time = None
            self._call_persist()
```

Final structure of `record_failure()`:

```python
    def record_failure(self) -> None:
        """Record a failed call — may trip the breaker to OPEN."""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()

            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                logger.warning(
                    "CircuitBreaker[%s]: HALF_OPEN → OPEN (probe failed)",
                    self.name,
                )
            elif (
                self._state == CircuitState.CLOSED and self._failure_count >= self.failure_threshold
            ):
                self._state = CircuitState.OPEN
                logger.warning(
                    "CircuitBreaker[%s]: CLOSED → OPEN (%d consecutive failures)",
                    self.name,
                    self._failure_count,
                )
            self._call_persist()
```

Final structure of `reset()`:

```python
    def reset(self) -> None:
        """Manually reset the breaker to CLOSED."""
        with self._lock:
            old_state = self._state
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._last_failure_time = None
            if old_state != CircuitState.CLOSED:
                logger.info(
                    "CircuitBreaker[%s]: %s → CLOSED (manual reset)", self.name, old_state.value
                )
            self._call_persist()
```

- [ ] **Step 9: Run tests to verify they pass**

```bash
cd /d/Sublarr_Projekt/Sublarr/backend && python -m pytest tests/test_circuit_breaker_persistence.py tests/test_circuit_breaker.py -v
```

Expected: all tests pass (including any pre-existing circuit breaker tests)

- [ ] **Step 10: Verify existing provider tests still pass**

```bash
cd /d/Sublarr_Projekt/Sublarr/backend && python -m pytest tests/ -k "circuit" -v --tb=short
```

Expected: all pass

- [ ] **Step 11: Commit**

```bash
cd /d/Sublarr_Projekt/Sublarr
git add backend/db/models/circuit_breaker.py \
        backend/db/migrations/versions/d5e6f7a8b9c0_add_circuit_breaker_state.py \
        backend/circuit_breaker.py \
        backend/tests/test_circuit_breaker_persistence.py
git commit -m "feat: add circuit breaker state persistence across restarts via DB table"
```

---

## Task 6: Pre-PR Checks and Final Validation

- [ ] **Step 1: Full backend test suite**

```bash
cd /d/Sublarr_Projekt/Sublarr/backend && python -m pytest --tb=short -q \
  --ignore=tests/performance \
  --ignore=tests/integration/test_provider_pipeline.py \
  --ignore=tests/test_video_sync.py \
  --ignore=tests/test_translation_backends.py \
  -k "not (test_sonarr_download_webhook or test_radarr_download_webhook or test_parse_llm_response_too_many_merge or test_record_backend_success)"
```

Expected: all pass

- [ ] **Step 2: Ruff lint + format check**

```bash
cd /d/Sublarr_Projekt/Sublarr/backend && ruff check . && ruff format --check .
```

Expected: no violations

- [ ] **Step 3: Frontend checks**

```bash
cd /d/Sublarr_Projekt/Sublarr/frontend && npm run lint && npx tsc --noEmit && npm run test -- --run
```

Expected: 0 errors

- [ ] **Step 4: Push branch**

```bash
cd /d/Sublarr_Projekt/Sublarr && git push -u origin phase/4-features
```

---

## Self-Review Against Spec

| Spec requirement | Task |
|-----------------|------|
| `must_contain` filter | Task 1 (API exposure) — helper already existed |
| `must_not_contain` filter | Task 1 (API exposure) — helper already existed |
| `cutoff_language` filter | Task 1 (API exposure) — helper already existed |
| `audio_exclude` filter | Task 1 (API exposure) — helper already existed |
| `video_codec: 2` weight in scoring | Task 2 |
| Apply codec bonus in search results | Task 2 (`apply_video_codec_bonus()`) |
| `is_standalone_mode()` helper | Task 3 (delegates to existing plan) |
| Standalone `arr_configured`/`auto_activated` status fields | Task 3 |
| Standalone UI section in ConnectionsSettings | Task 3 |
| `use_chat_api` config flag | Task 4 |
| `_call_ollama_chat()` method | Task 4 |
| `series_context` parameter in `translate_batch` | Task 4 |
| V9 backwards-compatible (default off) | Task 4 |
| Circuit breaker DB table | Task 5 |
| CB state load on startup | Task 5 (`load_state()`) |
| CB state persist on transition | Task 5 (`_call_persist()` callback) |

**Phase 4D (Download Upgrade Tracking + Post-Processing Hook)** from the spec is not included here — the `upgraded_from_id` column already exists on `SubtitleDownload` (added in migration `d2e3f4a5b6c7`). The post-processing shell hook is a separate feature. Confirm with the team whether to include it in this branch before starting.
