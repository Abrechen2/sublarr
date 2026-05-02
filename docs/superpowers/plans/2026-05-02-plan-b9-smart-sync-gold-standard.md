# Plan B9 — Smart Sync (Gold Standard)

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development to implement this plan
> task-by-task.

**Spec:** `docs/superpowers/specs/2026-05-02-gold-standard-editor-sync-design.md`
**Prior:** B7 shipped as 0.70.0-beta — sequential-fallback orchestrator
+ audit log; B8 ships the Waveform Editor that B9 reuses for the
Diff-View overlay.
**Baseline:** 0.83.0-beta (after B8) → 0.84.0-beta.
**Scope:** Tier 1 + Tier 2. Tier 3 (WhisperX anchor engine) deferred.

**Goal:** Move the orchestrator from sequential-fallback to **parallel-pick-best** with a confidence score, surface a **diff preview** before
applying any sync result, give users a **manual run** with engine
selector, persist **per-show engine policies**, support **selective
apply** (lock-lines), and let users **revert** any historical sync.

---

## Pre-Flight

- [ ] **Pre-1: Verify B8 acceptance has shipped**

  This plan reuses the Waveform component for the diff overlay. If B8
  is not yet on master, this plan does not start.

- [ ] **Pre-2: Confirm `subaligner` install path on Cardinal**

  Subaligner downloads a ~50 MB DNN model on first use to
  `~/.subaligner`. We need that to land on `/config/models` instead
  (so it persists across container rebuilds).

  Test:
  ```bash
  docker run --rm sublarr:0.83.0-beta python -c \
    "import subaligner; print(subaligner.__version__)"
  ```
  If the import works inside the container, proceed; else add to
  `requirements.txt` and rebuild a test image first.

---

## File Structure

### Create
- `backend/services/sync_engines/parallel_orchestrator.py` —
  `ParallelSyncOrchestrator` class.
- `backend/services/sync_engines/confidence.py` — confidence-score
  helper.
- `backend/services/sync_engines/subaligner_engine.py` — DNN engine
  wrapper.
- `backend/services/sync_engines/revert.py` — restore subtitle bytes
  from `sync_job_runs.subtitle_bytes_before`.
- `backend/db/migrations/versions/2026_05_XX-<rev>_add_sync_diff_columns.py`
- `backend/tests/test_parallel_orchestrator.py`
- `backend/tests/test_confidence_score.py`
- `backend/tests/test_subaligner_engine.py`
- `backend/tests/test_revert_sync.py`
- `frontend/src/components/sync/SyncDiffView.tsx` — diff table +
  waveform overlay + apply/cancel.
- `frontend/src/components/sync/SyncRunButton.tsx` — manual run
  trigger (used in Library episode/movie pages).
- `frontend/src/components/sync/SyncEngineChainEditor.tsx` —
  drag-sortable list to reorder/disable engines.
- `frontend/src/api/syncRun.ts` — manual-run API client.

### Modify
- `backend/services/sync_engines/orchestrator.py` — extract a
  `SequentialSyncOrchestrator` (keep current behaviour) and split a
  shared `BaseOrchestrator` interface.
- `backend/services/sync_engines/__init__.py` — export
  `ParallelSyncOrchestrator`, `get_orchestrator(mode)`.
- `backend/services/sync_engines/events.py` — add `confidence` and
  `subtitle_bytes_before` to `write_sync_job_run`.
- `backend/db/models/core.py` — add columns to `SyncJobRun`,
  `SeriesSettings`, `MovieSettings`.
- `backend/routes/sync_engines.py` — add:
  - `POST /api/v1/sync/run` (manual run with engine selector)
  - `POST /api/v1/sync/apply/<run_id>` (apply persisted result)
  - `POST /api/v1/sync/revert/<run_id>` (restore pre-sync bytes)
  - `GET /api/v1/sync/preview/<run_id>` (diff view data)
- `backend/services/video_sync.py` — branch on configured `mode`.
- `backend/config_settings.py` — new fields:
  `sync_orchestrator_mode: Literal["sequential", "parallel"] = "sequential"`,
  `sync_min_confidence: float = 0.65`,
  `sync_parallel_max_concurrent: int = 2`.
- `frontend/src/pages/Settings/SyncEnginesTab.tsx` — add mode toggle
  + `SyncEngineChainEditor`.
- `frontend/src/api/syncEngines.ts` — extend types.
- `frontend/src/i18n/locales/{de,en}/settings.json` — new keys.
- `docs/THIRD-PARTY-LICENSES.md` — add `subaligner` row.

---

## Task 1: Schema migration

- [ ] **Step 1: Find alembic head**

  ```bash
  cd backend && python -m alembic heads
  ```
  Record as `<PRIOR_HEAD>`.

- [ ] **Step 2: Generate revision**

  ```bash
  python -c "import secrets; print(secrets.token_hex(6))"
  ```

- [ ] **Step 3: Write migration**

  ```python
  # add_sync_diff_columns.py
  def upgrade():
      op.add_column("sync_job_runs",
          sa.Column("confidence", sa.Float, nullable=True))
      op.add_column("sync_job_runs",
          sa.Column("subtitle_bytes_before", sa.LargeBinary, nullable=True))
      op.add_column("sync_job_runs",
          sa.Column("applied", sa.Boolean, nullable=False, server_default="0"))
      op.add_column("series_settings",
          sa.Column("preferred_sync_engines", sa.JSON, nullable=True))
      op.add_column("movie_settings",
          sa.Column("preferred_sync_engines", sa.JSON, nullable=True))

  def downgrade():
      op.drop_column("movie_settings", "preferred_sync_engines")
      op.drop_column("series_settings", "preferred_sync_engines")
      op.drop_column("sync_job_runs", "applied")
      op.drop_column("sync_job_runs", "subtitle_bytes_before")
      op.drop_column("sync_job_runs", "confidence")
  ```

- [ ] **Step 4: Update ORM models** in `db/models/core.py`.

- [ ] **Step 5: Test migration**

  ```bash
  cd backend && python -m alembic upgrade head && python -m alembic downgrade -1 && python -m alembic upgrade head
  ```
  Both directions clean on SQLite + PostgreSQL.

---

## Task 2: Confidence score

- [ ] **Step 1: Define metric**

  Audio-energy-vs-cue-activation cross-correlation:

  ```
  audio_envelope = downsample(extract_audio_track(video), to=10Hz)
  cue_activation[t] = 1 if any cue covers t else 0
  confidence = pearson_corrcoef(audio_envelope, cue_activation)
  → clamp to [0, 1]
  ```

  Helper signature:
  ```python
  def compute_confidence(
      video_path: str,
      synced_cues: list[Cue],
      audio_track_index: int = 0,
  ) -> float:
      ...
  ```

- [ ] **Step 2: Implementation**

  Use the existing `audio_visualizer.extract_audio_track` to get the
  WAV. `numpy` is already a transitive dep (via several others — verify
  in `requirements.txt`; if not, add `numpy>=1.26`). Compute envelope
  via `np.abs(samples).reshape(-1, window).mean(axis=1)`. Build
  `cue_activation` from cue list. Compute `np.corrcoef`.

- [ ] **Step 3: Edge cases**

  - No cues → confidence = 0.0
  - All cues outside video duration → confidence = 0.0
  - Audio extraction fails → confidence = `None` (not 0; downstream
    treats `None` as "unknown")

- [ ] **Step 4: Tests**

  - High-correlation fixture (synthetic): cues placed exactly at audio
    peaks → confidence > 0.8
  - Random-shifted cues: confidence < 0.3
  - Empty cue list: confidence == 0.0
  - Failed audio: confidence is None

---

## Task 3: Parallel orchestrator

- [ ] **Step 1: Refactor `BaseOrchestrator`**

  Extract `Orchestrator` ABC with `sync(subtitle, video) -> SyncResult`.
  Rename existing class to `SequentialSyncOrchestrator`.

- [ ] **Step 2: Implement `ParallelSyncOrchestrator`**

  ```python
  class ParallelSyncOrchestrator(BaseOrchestrator):
      def __init__(
          self,
          engines: list[BaseSyncEngine],
          sanity_threshold_ms: int = 60_000,
          min_confidence: float = 0.65,
          max_concurrent: int = 2,
      ): ...

      def sync(self, subtitle_path, video_path) -> SyncResult:
          with ThreadPoolExecutor(max_workers=self.max_concurrent) as pool:
              futures = {pool.submit(e.sync, subtitle_path, video_path): e
                         for e in self.engines if e.is_available()}
              results = []
              for fut in as_completed(futures):
                  engine = futures[fut]
                  result = self._collect(fut, engine, subtitle_path, video_path)
                  if result is not None:
                      results.append((engine, result))
          # Pick winner
          scored = [(e, r, compute_confidence(video_path, r.cues)) for e, r in results]
          # Drop sub-threshold
          scored = [s for s in scored if s[2] is not None and s[2] >= self.min_confidence]
          if not scored:
              return SyncResult(ok=False, ...)
          # Highest confidence wins; tie-break by smaller |offset_ms|
          scored.sort(key=lambda x: (-x[2], abs(x[1].offset_ms)))
          return scored[0][1]
  ```

- [ ] **Step 3: Audit each engine result**

  Every engine result writes its own `sync_job_runs` row, including
  losers. The winning row gets `applied=True` only after the user
  confirms in the diff view (see Task 5).

- [ ] **Step 4: Resource pressure check**

  Before submitting all engines, check `psutil.cpu_percent(interval=0.1)`.
  If > 80%, fall back to sequential. Log a warning.

- [ ] **Step 5: Tests**

  - 2 mock engines, both succeed, different offsets → winner is the
    one with higher confidence.
  - 1 succeeds, 1 raises → winner = the success.
  - Both succeed but both below `min_confidence` → returns ok=False.
  - CPU pressure simulated → falls back to sequential.

---

## Task 4: subaligner engine

- [ ] **Step 1: Add to requirements**

  ```
  subaligner>=0.3.7  # MIT, optional sync engine (lazy import)
  ```

  In `services/sync_engines/subaligner_engine.py`:
  ```python
  class SubalignerEngine(BaseSyncEngine):
      name = "subaligner"
      timeout_s = 180

      def is_available(self) -> bool:
          try:
              import subaligner  # noqa
              return True
          except ImportError:
              return False

      def sync(self, subtitle_path: str, video_path: str) -> SyncResult:
          from subaligner.predictor import Predictor
          # ... wrap the synchronous call, capture offset_ms
  ```

- [ ] **Step 2: Model cache directory**

  Subaligner downloads weights to `~/.subaligner` by default. Override
  via env: `SUBALIGNER_WEIGHTS_DIR=/config/models/subaligner`. Set this
  in `Dockerfile` and `docker-compose.yml` documentation.

- [ ] **Step 3: First-run UX**

  If model not yet downloaded, show a settings notice: "First run will
  download a ~50 MB model to /config/models. Cardinal must have outbound
  https." Include in `docs/THIRD-PARTY-LICENSES.md`:
  ```
  | subaligner | MIT | https://github.com/baxtree/subaligner |
  ```

- [ ] **Step 4: Tests**

  - `is_available()` False when import fails (mock it).
  - `sync()` with mocked `Predictor` returns valid SyncResult.
  - Real-engine integration test marked `@pytest.mark.integration` and
    skipped in default `task test`.

---

## Task 5: Diff preview API

- [ ] **Step 1: GET preview endpoint**

  ```python
  @bp.route("/sync/preview/<int:run_id>", methods=["GET"])
  @require_auth
  def get_preview(run_id):
      run = SyncJobRun.query.get_or_404(run_id)
      original = decompress(run.subtitle_bytes_before)
      synced = read(run.subtitle_path)
      diff = compute_cue_diff(original, synced)  # list of {idx, before, after, delta_ms}
      return jsonify({
          "run": serialize(run),
          "diff": diff,
          "confidence": run.confidence,
          "video_path": run.video_path,
          "subtitle_path": run.subtitle_path,
      })
  ```

- [ ] **Step 2: cue diff helper**

  In `services/sync_engines/diff.py`:
  ```python
  def compute_cue_diff(before_bytes: bytes, after_bytes: bytes
                      ) -> list[dict]:
      before = pysubs2.SSAFile.from_string(before_bytes.decode())
      after = pysubs2.SSAFile.from_string(after_bytes.decode())
      # Pair by line index (assumes line count unchanged — sync engines
      # don't insert/delete lines)
      ...
  ```
  If line counts differ (defensive), fall back to a fuzzy pairing
  by text + nearest-time.

- [ ] **Step 3: POST apply / revert**

  ```python
  @bp.route("/sync/apply/<int:run_id>", methods=["POST"])
  @require_auth
  def apply_sync(run_id):
      run = SyncJobRun.query.get_or_404(run_id)
      if run.applied:
          return jsonify({"error": "already applied"}), 409
      # The synced bytes are already at run.subtitle_path; we just mark
      # applied=True. The pre-sync bytes remain in the row for revert.
      run.applied = True
      db.session.commit()
      return jsonify({"ok": True})

  @bp.route("/sync/revert/<int:run_id>", methods=["POST"])
  @require_auth
  def revert_sync(run_id):
      run = SyncJobRun.query.get_or_404(run_id)
      if not run.subtitle_bytes_before:
          return jsonify({"error": "no original bytes stored"}), 410
      with open(run.subtitle_path, "wb") as f:
          f.write(zlib.decompress(run.subtitle_bytes_before))
      run.applied = False
      db.session.commit()
      return jsonify({"ok": True})
  ```

- [ ] **Step 4: Pre-sync bytes capture**

  Modify the orchestrator to read+compress (`zlib.compress(level=9)`)
  the subtitle file *before* engines run, and pass through to the
  audit row writer. Cap at 256 KB (typical subtitle is < 100 KB);
  larger files write `None` and the revert UI shows "no backup
  stored — file too large".

---

## Task 6: Manual run + engine-picker UI

- [ ] **Step 1: POST /sync/run endpoint**

  Body: `{ "subtitle_path": "...", "video_path": "...", "engines": ["alass"] | "auto" | null }`.
  - `null` or `"auto"` → use configured mode (sequential or parallel)
    + the show's `preferred_sync_engines` if set.
  - List of names → run only those engines (in parallel if `mode=parallel`,
    else sequential in given order).

  Returns `{ "run_id": ..., "confidence": ..., "preview_url": "..." }`
  but does **not** apply yet.

- [ ] **Step 2: SyncRunButton component**

  Drop into Library episode + movie detail pages. Click → modal:
  - Engine picker (multi-select; defaults to show's policy if set,
    else mode default)
  - "Run sync" button
  - On success → opens `SyncDiffView`

- [ ] **Step 3: Tests**

  - Component test: render button, click, mock API, assert diff view
    opens.

---

## Task 7: SyncDiffView component (frontend)

- [ ] **Step 1: Layout**

  Two-pane modal:
  - Left: Diff table — `idx | before | after | delta`, sortable; rows
    where `|delta| > 200ms` highlighted in red, > 50ms in amber.
  - Right: Reused `WaveformEditor` from B8 with **two** region layers —
    original (gray) + synced (teal). User can play through and hear.

- [ ] **Step 2: Apply / Cancel**

  Apply button calls `POST /sync/apply/<run_id>` and closes modal.
  Cancel just closes (the bytes are still in `subtitle_path`; we mark
  the run as `applied=False` and the next run from the user can use
  revert if they want to roll back the path-overwrite).

  **Open question:** does the orchestrator overwrite `subtitle_path`
  *before* the user confirms, or only on apply? **Decision:** writes a
  side-car `<file>.synced.<run_id>.<ext>`, and `apply` renames it over
  the original (preserving the pre-sync bytes that were captured in
  Task 5). This way "Cancel" leaves the on-disk file untouched.
  Update Task 5 step 4 accordingly.

- [ ] **Step 3: Selective apply (Tier 2)**

  Add a per-row checkbox `[x] include`. Apply uses only ticked rows;
  others keep their pre-sync timestamps. Implemented as a backend
  helper that merges old+new cues by index before writing.

- [ ] **Step 4: Tests**

  - Render with 5 cues, 2 over the threshold → assert highlighted.
  - Click Apply → POST hit.
  - Click Cancel → no POST.
  - Selective apply with row 3 unchecked → backend merge keeps row 3
    pre-sync, others new.

---

## Task 8: Per-show / per-movie engine policy

- [ ] **Step 1: ORM + repository**

  Add `preferred_sync_engines: list[str] | None` to `SeriesSettings`
  and `MovieSettings`. Repository methods `set_preferred_engines(...)`
  and `get_preferred_engines(...)`.

- [ ] **Step 2: Settings page integration**

  In the existing `Library → Series → Settings` modal, add a
  multi-select "Preferred Sync Engines" with a "(use global default)"
  option.

- [ ] **Step 3: Orchestrator override**

  When `sync(subtitle, video)` runs with a known series/movie id,
  read the preferred list and pass into `get_orchestrator()`. Falls
  back to global if `None`.

- [ ] **Step 4: Tests**

  - Set series → `["alass"]`. Trigger sync. Assert only alass ran
    (single row in `sync_job_runs`).
  - Set series → null. Assert default chain.

---

## Task 9: Sync chain editor (frontend)

- [ ] **Step 1: Drag-sortable list**

  In `SyncEnginesTab.tsx`, replace the read-only `<ol>` with a
  drag-sortable list. Use `@dnd-kit/sortable` (MIT, already a dep —
  verify; if not add). Each item shows the engine, its availability
  badge, an enabled/disabled toggle.

- [ ] **Step 2: Persist on commit**

  On drag end, call `PATCH /api/v1/sync/engines` with `{ "order": [...], "disabled": [...] }`.
  Server stores in `config_entries`.

- [ ] **Step 3: Mode toggle**

  Toggle "Run engines in: [sequential | parallel]" persists via the
  `sync_orchestrator_mode` config field.

- [ ] **Step 4: Tests**

  - Drag swap two engines, assert PATCH body matches new order.
  - Disable engine, assert it's omitted from runtime chain on next
    `GET /sync/engines`.

---

## Task 10: Documentation + release prep

- [ ] **Step 1: User-guide updates**

  - `SublarrWeb/src/content/docs/docs/user-guide/settings/sync-engines.md`:
    new sections "Parallel mode", "Confidence score", "Diff preview",
    "Per-show engine policy", "Subaligner setup".
  - `SublarrWeb/src/content/docs/docs/getting-started/upgrade-guide.md`:
    0.84.0-beta entry.

- [ ] **Step 2: CHANGELOG**

  Add 0.84.0-beta section to `Sublarr/CHANGELOG.md`:
  - Parallel-pick-best orchestrator with confidence scoring
  - Diff preview before apply
  - Manual sync run with engine selector
  - Per-show / per-movie engine policy
  - Subaligner DNN engine (optional)
  - Audit-log revert
  - Sync chain editor in Settings

- [ ] **Step 3: License-checker pass**

  Pre-deploy gate from B8 must stay green. New entry:
  - `subaligner` — MIT — `docs/THIRD-PARTY-LICENSES.md`

- [ ] **Step 4: Deploy**

  Use the `deploy` skill (auto-bumps to 0.84.0-beta, builds, pushes,
  pulls on Cardinal).

---

## Future Work (Tier 3, not in this plan)

- **WhisperX anchor engine** — real LLM-grounded re-anchor. Cardinal
  is CPU-only Unraid; WhisperX needs CUDA for usable performance.
  Two viable paths:
  1. Proxy through the Mac mini Ollama instance (which already runs
     Whisper-derivatives) — needs an HTTP wrapper.
  2. Use `stable-ts` (lighter, MIT, CPU-feasible at 0.5–1× realtime)
     with a one-engine "anchor mode" that tags scene boundaries.

  Decision deferred until Phase B10 — only ship if a real anime episode
  fixture demonstrates a measurable improvement over alass+ffsubsync's
  current parallel result.

- **Streaming sync** — for very long files (movies > 2h), break into
  chunks, sync per chunk, stitch. Today everything is whole-file. Open
  research, no clear win for the typical 24-min anime use case.

- **GPU-accelerated alass** — `alass` has a CUDA branch upstream. Out
  of scope for a CPU-only homelab.

---

## License Audit (final)

| Component | License | Compatible with GPL-3 (Sublarr) | Source |
|---|---|---|---|
| `subaligner` (new) | MIT | ✅ | https://github.com/baxtree/subaligner |
| `numpy` (likely already, verify) | BSD-3-Clause | ✅ | https://github.com/numpy/numpy |
| `@dnd-kit/sortable` (verify) | MIT | ✅ | https://github.com/clauderic/dnd-kit |
| `pysubs2` (existing) | MIT | ✅ | already audited |
| Diff helpers (in-repo) | GPL-3.0 | ✅ | new code |

If `@dnd-kit/sortable` or `numpy` are not yet in the lockfile, both add
cleanly to the existing license matrix without raising compatibility
concerns. The pre-deploy gate (`license-checker --onlyAllow=...`)
catches any surprise transitive that breaks the matrix.

---

## Acceptance Test Plan

1. In `Settings → Sync Engines`, switch mode to **Parallel**.
2. From `Library → Episode → Sync`, click "Run sync" with all engines
   selected. Both `alass` and `ffsubsync` rows appear in the run table
   within ~2 minutes, each with a confidence score.
3. The UI opens the **Diff View**: 4 cues over the 200 ms threshold
   highlighted red.
4. Reused waveform shows original cues in gray, new cues in teal —
   clearly visible.
5. Click **Apply**. Synced sidecar renames over original. Audit row
   `applied=true`.
6. Now click **Revert** in the audit history. Original bytes restored.
7. Set series-level policy to `["alass"]`. Trigger another sync. Only
   one row appears.
8. Run `task lint && task test:backend && task test:frontend` — green.
9. `npx license-checker --production` — green.
10. Deploy 0.84.0-beta via `/deploy` skill.
