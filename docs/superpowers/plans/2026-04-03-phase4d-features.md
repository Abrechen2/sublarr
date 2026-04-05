# Phase 4D — Download Tracking & Post-Processing: Gap Closure Plan

> **For agentic workers:** Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the remaining gaps in two already-partially-implemented Bazarr-parity features: `upgraded_from_id` audit trail and the post-download shell hook. Both features have substantial existing implementation — this plan fills the precise missing pieces only.

**Architecture:**
- Both features have their core layers (model, migration, repo, service) already in place and tested.
- Gap 1: `upgraded_from_id` is absent from the per-episode history response (the `get_episode_history` query selects specific columns and omits it).
- Gap 2: The post-download command is missing `{media_type}` variable substitution, the `post_processing_enabled` boolean guard, and the `{path}` alias for `{subtitle_path}`. The `download_manager` call-site also does not pass `media_type`.

**Tech Stack:** Python 3.12, Flask, SQLAlchemy, pytest — no new dependencies.

**Branch:** `phase/4d-features`

---

## Orientation: What Already Exists

Run before starting. All should pass.

```bash
cd D:/Sublarr_Projekt/Sublarr/backend
python -m pytest tests/test_upgrade_chain.py tests/test_post_download.py -v --tb=short
```

Expected: 8 tests pass. These cover the existing functionality; do not modify them.

---

## File Map

| File | Change |
|------|--------|
| `backend/db/repositories/cache.py` | Add `upgraded_from_id` to `get_episode_history()` SELECT columns |
| `backend/post_download.py` | Add `{media_type}` and `{path}` substitution; add `media_type` param |
| `backend/config.py` | Add `post_processing_enabled: bool = False` setting |
| `backend/providers/download_manager.py` | Pass `media_type` to `run_post_download_command`; check `post_processing_enabled` |
| `backend/tests/test_upgrade_chain.py` | Add test for `upgraded_from_id` in episode history response |
| `backend/tests/test_post_download.py` | Add tests for `{media_type}`, `{path}` alias, and `post_processing_enabled` guard |

---

## Task 1 — `upgraded_from_id` in episode history response

### Context

`get_episode_history()` in `backend/db/repositories/cache.py` (line ~167) builds its SELECT with an explicit column list:

```python
select(
    SubtitleDownload.provider_name,
    SubtitleDownload.format,
    SubtitleDownload.score,
    SubtitleDownload.downloaded_at,
)
```

This omits `upgraded_from_id`. The `/history` paginated endpoint already returns it (via `_to_dict` which uses all columns). This task fixes the per-episode history endpoint.

### Steps

- [ ] **RED:** Open `backend/tests/test_upgrade_chain.py`. Add a test at the bottom:

  ```python
  def test_episode_history_includes_upgraded_from_id():
      """get_episode_history entries must include upgraded_from_id field."""
      from unittest.mock import MagicMock, patch
      from datetime import UTC, datetime

      mock_session = MagicMock()
      # Simulate one SubtitleDownload row with upgraded_from_id=7
      mock_row = MagicMock()
      mock_row.provider_name = "jimaku"
      mock_row.format = "ass"
      mock_row.score = 200
      mock_row.downloaded_at = datetime(2026, 4, 3, 12, 0, tzinfo=UTC)
      mock_row.upgraded_from_id = 7
      mock_session.execute.return_value.all.return_value = [mock_row]

      with patch("db.repositories.base.db") as mock_db:
          mock_db.session = mock_session
          from db.repositories.cache import CacheRepository
          repo = CacheRepository.__new__(CacheRepository)
          repo._local = __import__("threading").local()
          entries = repo.get_episode_history("/media/ep.mkv")

      assert len(entries) >= 1
      dl_entry = next(e for e in entries if e.get("action") == "download")
      assert "upgraded_from_id" in dl_entry
      assert dl_entry["upgraded_from_id"] == 7
  ```

- [ ] Run: `python -m pytest tests/test_upgrade_chain.py::test_episode_history_includes_upgraded_from_id -v` — expect FAIL (KeyError or assertion).

- [ ] **GREEN:** Open `backend/db/repositories/cache.py`. In `get_episode_history()`, add `SubtitleDownload.upgraded_from_id` to the SELECT:

  ```python
  dl_rows = self.session.execute(
      select(
          SubtitleDownload.provider_name,
          SubtitleDownload.format,
          SubtitleDownload.score,
          SubtitleDownload.downloaded_at,
          SubtitleDownload.upgraded_from_id,   # ADD THIS
      )
      .where(SubtitleDownload.file_path.like(like_pattern))
      .order_by(SubtitleDownload.downloaded_at.desc())
      .limit(50)
  ).all()
  ```

  In the `for r in dl_rows:` loop, add the field to the result dict:

  ```python
  {
      "action": "download",
      "provider_name": r.provider_name,
      "format": r.format,
      "score": r.score,
      "date": r.downloaded_at,
      "status": "completed",
      "error": "",
      "upgraded_from_id": r.upgraded_from_id,  # ADD THIS
  }
  ```

- [ ] Run: `python -m pytest tests/test_upgrade_chain.py -v` — expect all 4 tests pass.

- [ ] Run full pre-commit checks:

  ```bash
  cd D:/Sublarr_Projekt/Sublarr/backend
  ruff check . && ruff format --check .
  python -m pytest tests/test_upgrade_chain.py -v --tb=short -q
  ```

- [ ] Commit:

  ```bash
  git add backend/db/repositories/cache.py backend/tests/test_upgrade_chain.py
  git commit -m "feat: expose upgraded_from_id in episode history response"
  ```

---

## Task 2 — Post-download shell hook: `{media_type}`, `{path}` alias, `post_processing_enabled`

### Context

`backend/post_download.py` currently substitutes: `{subtitle_path}`, `{language}`, `{provider}`, `{score}`, `{video_path}`.

The Bazarr-parity spec requires:
- `{path}` — alias for `{subtitle_path}` (same value, different name expected by many Bazarr scripts)
- `{media_type}` — `"series"` or `"movie"` depending on context
- `post_processing_enabled` boolean guard in `config.py` (analogous to how `translation_enabled` gates that feature)

`download_manager.py` currently calls `run_post_download_command` without passing `media_type`, so the function needs a new optional `media_type: str = ""` parameter.

### Steps

- [ ] **RED:** Open `backend/tests/test_post_download.py`. Add tests at the bottom:

  ```python
  def test_run_post_download_command_substitutes_media_type(monkeypatch):
      import subprocess
      from post_download import run_post_download_command

      calls = []

      def mock_run(cmd, shell, timeout, check):
          calls.append(cmd)

      monkeypatch.setattr(subprocess, "run", mock_run)
      run_post_download_command(
          "echo {media_type}", "/media/ep.ass", "de", "jimaku", 180,
          media_type="series"
      )
      assert len(calls) == 1
      assert "series" in calls[0]


  def test_run_post_download_command_path_alias(monkeypatch):
      """{path} must expand to the subtitle file path."""
      import subprocess
      from post_download import run_post_download_command

      calls = []

      def mock_run(cmd, shell, timeout, check):
          calls.append(cmd)

      monkeypatch.setattr(subprocess, "run", mock_run)
      run_post_download_command(
          "notify {path}", "/media/ep.ass", "de", "jimaku", 180
      )
      assert "/media/ep.ass" in " ".join(calls[0])


  def test_post_processing_enabled_guards_command(monkeypatch):
      """When post_processing_enabled is False, command must NOT run."""
      import subprocess
      from post_download import run_post_download_command

      calls = []

      def mock_run(*args, **kwargs):
          calls.append(args)

      monkeypatch.setattr(subprocess, "run", mock_run)
      # enabled=False (default) — pass it explicitly
      run_post_download_command(
          "echo hello", "/sub.ass", "de", "test", 100, enabled=False
      )
      assert calls == []
  ```

- [ ] Run: `python -m pytest tests/test_post_download.py -v` — new tests FAIL.

- [ ] **GREEN — `backend/config.py`:** Add `post_processing_enabled` right after the existing `post_download_command` line (line ~200):

  ```python
  # Post-download shell command
  post_download_command: str = ""  # Shell command to run after each subtitle download
  post_processing_enabled: bool = False  # Must be explicitly enabled; gate for post_download_command
  ```

- [ ] **GREEN — `backend/post_download.py`:** Update the function signature and body:

  ```python
  def run_post_download_command(
      command: str,
      subtitle_path: str,
      language: str,
      provider: str,
      score: int,
      video_path: str = "",
      media_type: str = "",   # "series" | "movie" | ""
      enabled: bool = True,   # pass post_processing_enabled from settings
  ) -> None:
      """Execute the post-download shell command if configured and enabled.

      Errors are logged as warnings but never propagated — post-processing
      is best-effort and must not break the download pipeline.

      Variables:
          {subtitle_path}  — absolute path to the saved subtitle file
          {path}           — alias for {subtitle_path} (Bazarr compat)
          {language}       — ISO 639-1 language code
          {provider}       — provider name (e.g. "jimaku")
          {score}          — integer match score
          {media_type}     — "series" | "movie" | ""
          {video_path}     — video file path (may be empty)
      """
      if not enabled:
          return
      if not command or not command.strip():
          return

      expanded = (
          command.replace("{subtitle_path}", subtitle_path)
          .replace("{path}", subtitle_path)           # Bazarr alias
          .replace("{language}", language)
          .replace("{provider}", provider)
          .replace("{score}", str(int(score)))
          .replace("{media_type}", media_type)
          .replace("{video_path}", video_path)
      )
      try:
          argv = shlex.split(expanded)
      except ValueError as exc:
          logger.warning("post_download_command: invalid shell syntax, skipping: %s", exc)
          return
      try:
          logger.info("Running post-download command: %s", argv)
          subprocess.run(argv, shell=False, timeout=60, check=False)  # noqa: S603
      except subprocess.TimeoutExpired:
          logger.warning("post_download_command timed out after 60 s")
      except Exception as exc:
          logger.warning("post_download_command failed: %s", exc)
  ```

- [ ] **GREEN — `backend/providers/download_manager.py`:** Update the `run_post_download_command` call site (line ~344) to pass `media_type` and `enabled`. The `save_subtitle` function receives `series_id: int | None` — use that to infer media_type:

  ```python
  if _pd_cmd:
      try:
          _pd_enabled = getattr(_pd_settings, "post_processing_enabled", False)
          _pd_media_type = "series" if series_id is not None else "movie"
          run_post_download_command(
              _pd_cmd,
              subtitle_path=output_path,
              language=result.language or "",
              provider=result.provider_name or "",
              score=result.score or 0,
              media_type=_pd_media_type,
              enabled=_pd_enabled,
          )
      except Exception as _pd_err:
          logger.warning("post_download_command hook failed: %s", _pd_err)
  ```

  Remove the old `if _pd_cmd:` guard that skips the call — `run_post_download_command` now handles the `enabled` check internally, but the outer `if _pd_cmd:` block can remain as a fast-path skip.

- [ ] Run: `python -m pytest tests/test_post_download.py -v` — all 7 tests pass.

- [ ] Run full pre-commit checks:

  ```bash
  cd D:/Sublarr_Projekt/Sublarr/backend
  ruff check . && ruff format --check .
  python -m pytest tests/test_post_download.py tests/test_upgrade_chain.py -v --tb=short -q
  ```

- [ ] Commit:

  ```bash
  git add backend/post_download.py backend/config.py \
          backend/providers/download_manager.py \
          backend/tests/test_post_download.py
  git commit -m "feat: add {media_type}/{path} variables and post_processing_enabled guard to shell hook"
  ```

---

## Task 3 — Full regression check

- [ ] Run the complete test suite with standard ignores:

  ```bash
  cd D:/Sublarr_Projekt/Sublarr/backend
  python -m pytest --tb=short -q \
    --ignore=tests/performance \
    --ignore=tests/integration/test_provider_pipeline.py \
    --ignore=tests/test_video_sync.py \
    --ignore=tests/test_translation_backends.py \
    -k "not (test_sonarr_download_webhook or test_radarr_download_webhook or test_parse_llm_response_too_many_merge or test_record_backend_success)"
  ```

- [ ] Confirm no regressions. If failures occur, fix before proceeding.

- [ ] Merge branch to master:

  ```bash
  git checkout master
  git merge --no-ff phase/4d-features -m "feat: phase 4D — download tracking & post-processing gap closure"
  git push
  ```

---

## Acceptance Criteria

### Feature 1: `upgraded_from_id`

- [ ] `GET /api/v1/episodes/<id>/history` response entries include `"upgraded_from_id": <int|null>` field
- [ ] `GET /api/v1/history` (paginated) continues to include `upgraded_from_id` (already works — no change needed)
- [ ] When a subtitle is upgraded, the new `subtitle_downloads` row has `upgraded_from_id = <id of replaced row>`
- [ ] All 4 `test_upgrade_chain.py` tests pass

### Feature 2: Post-processing shell hook

- [ ] `SUBLARR_POST_PROCESSING_ENABLED=false` (default) means no subprocess is ever launched, even if `post_download_command` is set
- [ ] `SUBLARR_POST_PROCESSING_ENABLED=true` with a command runs the command after each subtitle save
- [ ] `{media_type}` expands to `"series"` when `series_id` is not None, `"movie"` otherwise
- [ ] `{path}` expands to the same value as `{subtitle_path}`
- [ ] All 7 `test_post_download.py` tests pass

---

## Notes

- `{video_path}` remains as-is (empty string in most calls — reserved for future use when video path is available at download time)
- The timeout stays at 60 s (the original implementor chose this over 30 s; it is not a bug)
- Wiki settings page (`SublarrWiki/en/user-guide/settings/`) should be updated to document `post_processing_enabled` and the new `{media_type}` / `{path}` variables — do this as a follow-up after the code ships
