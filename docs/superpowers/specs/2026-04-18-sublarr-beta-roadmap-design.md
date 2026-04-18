# Sublarr Beta-Roadmap — Post Phase 4a

**Date:** 2026-04-18
**Status:** Active design
**Supersedes:** [`2026-04-18-v1-competitive-parity.md`](./2026-04-18-v1-competitive-parity.md) (kept for historical reference)
**Author:** Brainstormed jointly with the maintainer in session 2026-04-18.

---

## What changed vs. the previous spec

The previous spec framed the next 4–6 weeks as "march toward V1.0.0 by closing gaps with Bazarr, Lingarr, Subservient". In the brainstorming session that produced **this** document, the maintainer corrected the premise:

> "V1 ist *nicht* bald. Wir machen weiter mit Betas, bis ich wirklich überzeugt bin."

That single statement invalidates the V1-focused phase plan. The pain-point poll that followed produced an even stronger signal:

- **No** stability complaints (a)
- **No** missing-feature complaints (b)
- **No** performance complaints (c)
- **Yes** UX-friction (d)
- **Yes** code-confidence anxiety (e)
- **Yes** observability gaps (f)
- **Yes** competition-comparison pressure (g) — *named explicitly as a bias to defend against*

Phases 6 (provider expansion), 7 (Bazarr-style scoring + language profiles) and 8 (translation provider plurality) from the previous spec were therefore identified as **parity theater driven by (g)** — not by user pain. They are preserved in the Inspiration Backlog (§4) but not actively prioritized.

Phase 5 (APScheduler rewrite) lost its main justification: there is no current scheduler-stability pain. Most of what the maintainer actually wanted from Phase 5 + 9 turned out to be observability, not infrastructure replacement. A `job_executions` table delivers it at ~10× less risk and effort.

---

## 1. Doctrine

These four lines are read **before every roadmap decision**:

> 1. Sublarr does **not** compete with Bazarr on provider count or scoring complexity.
> 2. Sublarr competes on: **anime-first metadata + fine-tuned translation + rate-limit intelligence + clean UX**.
> 3. Everything else is bonus, not obligation.
> 4. Honest reality: Sublarr has practically no external users today. There is nothing to defend. Competitive pressure is imagined.

**How the doctrine is enforced:** Whenever an item is proposed for the Active Backlog (§3), the proposer answers in writing:
- *"Which of the four moats does this strengthen?"* → if none, it goes to the Inspiration Backlog (§4) instead.
- *"Would I want this even if Bazarr did not exist?"* → if no, it goes to Inspiration.

---

## 2. Conviction criteria for V1.0.0

V1.0.0 is shipped when the maintainer is "wirklich überzeugt". Operationalised, that means **all three of the following** are simultaneously true for ≥ 14 consecutive days of personal daily use:

1. **(d) UX-friction:** No remembered "warum funktioniert das so umständlich"-moment in any flow used in the past 7 days.
2. **(e) Code-confidence:** Maintainer can open any file in `backend/` or `frontend/src/` and feel safe modifying it. No file is "scary to touch".
3. **(f) Observability:** Maintainer can answer the four sample questions from §3 Bucket C in <5 seconds each, without reading logs.

These are intentionally subjective — the maintainer is the person making the call. They are not metrics. Conviction does not require closing the Inspiration Backlog.

---

## 3. Active Backlog

Three buckets. Priority order: **B → C → A**, with limited interleaving allowed (see §6). Each item is sized so that it ships as its own `/deploy` beta release.

### Bucket B — Code Confidence (priority 1)

Addresses (e). Investing here first compounds: every later UX or observability change is cheaper after B is done. Bucket B contains zero user-visible behavior changes by design — risk floor is low.

#### B1 — God-file split

**Pain:** Eight files exceed the maintainer's own 800 LOC ceiling (`CLAUDE.md`). Each is a god-file *and* a churn hotspot, meaning every future feature lands in the same fat module and grows it further.

**Files:**
| File | LOC | Churn (6w) |
|---|---|---|
| `backend/routes/cleanup.py` | 1105 | medium |
| `backend/providers/__init__.py` | 893 | **37 commits** |
| `backend/providers/search_coordinator.py` | 878 | medium |
| `backend/routes/wanted/extract.py` | 863 | medium |
| `backend/config.py` | 846 | **44 commits** |
| `backend/routes/standalone.py` | 816 | low |
| `frontend/src/pages/SeriesDetail.tsx` | 965 | 22 commits |
| `frontend/src/hooks/useSystemApi.ts` | 834 | medium |

**Approach:** One file per `/deploy` cycle. For each: (a) identify natural seams (route groups, lifecycle phases, domain boundaries); (b) extract submodules; (c) keep the public import surface unchanged so callers do not need to be touched; (d) add a regression test that exercises the public surface.

**Acceptance:** All 8 files are below 600 LOC (giving 200 LOC headroom). No public API change. Existing test suite is green.

**Cross-cutting (per §5):** Rollback = git revert (no schema). Feature-flag = N/A (internal refactor). Metric = `files_over_800_loc` count drops to 0, monitored by a CI check. Migration notes = N/A. Docs = `CLAUDE.md` references to those files updated if needed.

#### B2 — Churn-hotspot boundary hardening

**Pain:** Three files attract a disproportionate share of all commits (`config.py`: 44, `providers/__init__.py`: 37, `app.py`: 20 in the last 6 weeks). Even if their LOC is reduced by B1, the *churn* signal means they will keep growing unless their **boundaries** are protected.

**Approach:**
- `config.py`: separate the *settings schema* (Pydantic models) from the *settings access pattern* (`getattr` with defaults, validation hooks). Add an explicit "how to add a config field" section in `CLAUDE.md`.
- `providers/__init__.py`: introduce a `provider_registry.py` with a single registration entry point. Each new provider plugs in via the registry, not by editing the bundle module.
- `app.py`: extract Flask setup steps (extensions, blueprints, error handlers) into focused factory helpers under `app_factory/`.

**Acceptance:** A new provider can be added in *one* file. A new config field can be added in *one* model. App factory helpers are independently testable.

**Cross-cutting:** Rollback = git revert. Flag = N/A (internal). Metric = "files added per new provider/config-field" measured on the next time we add one (target: 1). Docs = `CLAUDE.md` updated with the new how-to sections.

#### B3 — Migration safety net

**Pain:** Maintainer has ≥ 4 explicit memory entries about Alembic anti-patterns that have caused incidents (`autocommit_block` + `CONCURRENTLY`, missing `IF NOT EXISTS`, forgotten `exc_info=True`, duplicate revision IDs). The next future maintainer (incl. future-self after a context reset) will hit them again.

**Approach:** Static linter that scans `backend/db/migrations/versions/*.py` for known anti-patterns and fails CI on a hit. Initial rules:
- `op.execute("CREATE INDEX CONCURRENTLY")` requires no surrounding transaction.
- `op.create_index(...)` and `op.create_table(...)` require `if_not_exists=True` if the model is also in `db.Model.metadata`.
- `op.f("...")` references must exist in the schema (catches stale rename refs).
- Each migration must have a `down_revision` and a `revision` distinct from every other revision file.
- Each Alembic-wrapping `try/except` in production code uses `exc_info=True`.

**Approach (cont):** Rules are a small Python script `tools/check_migrations.py`, hooked into `ruff` workflow.

**Acceptance:** Linter catches all 4 historical incidents on a fixture corpus. CI step added.

**Cross-cutting:** Rollback = remove linter step. Flag = N/A. Metric = "post-migration prod incidents per quarter" (target: 0). Docs = `backend/db/migrations/README.md` (new file) explains the rules.

#### B4 — Dead-code sweep

**Pain:** No baseline measurement exists today. Maintainer's anxiety about "if I touch X, do I break Y?" is partly fed by uncertainty about what is *unused*. Dead code in test suites also slows runs without earning value.

**Approach:**
- Backend: `vulture backend/ --min-confidence 80` (curated allowlist for dynamic-import patterns).
- Frontend: `knip` + `ts-prune`.
- Sweep is one-shot, but the tools land in CI as **non-blocking** reports first (so the maintainer sees deltas without it stopping deploys), then converted to blocking after the first clean baseline.

**Acceptance:** First sweep removes ≥ 200 dead exports/lines (estimate; actual depends on findings). CI report emitted on every PR.

**Cross-cutting:** Rollback = git revert. Flag = N/A. Metric = `dead_code_count` reported per CI run. Docs = none required (tool README suffices).

#### B5 — Mutation testing for security paths

**Pain:** `security_utils.py`, `archive_utils.py`, `subtitle_sanitizer.py` are the modules where a silent test-pass is most expensive (path traversal, ZIP bomb, Lua injection). Today's tests cover happy-paths well; mutation testing will surface whether they catch *malicious* paths.

**Approach:** `mutmut run` against those three modules, gated to those modules to keep runtime bounded. Mutation score target ≥ 90 % for these files. Add tests for any surviving mutants.

**Acceptance:** Mutation score ≥ 90 % on the three files. Reported in CI weekly (not per-PR — too slow).

**Cross-cutting:** Rollback = remove the weekly job. Flag = N/A. Metric = mutation score per module, trended. Docs = `backend/tests/README.md` notes the mutation-test commitment.

---

### Bucket C — Observability (priority 2)

Addresses (f). Each item answers one of the maintainer's 4 sample questions in <5 seconds.

#### C1 — Job-execution log + live status panel

**Question answered:** *"Wann lief die letzte Automation? Lief die Auto-Extraction?"*

**Approach:**
- New table `job_executions(id, job_name, started_at, finished_at, status, error_msg, metadata_json)`. Append-only, weekly retention sweep.
- Existing `threading.Timer`-based jobs (`WantedSearchRunner`, `CleanupScheduler`, `UpgradeScheduler`, `TickRecovery`, `AutoExtractor`) wrap their tick body with `record_execution(job_name)` context manager that writes one row per run.
- New endpoint `GET /api/v1/system/jobs/recent?job_name=...` returns last N executions per job with start/end/duration/status.
- New dashboard widget "Scheduler" lists every recurring job: name, last run timestamp, last duration, last status (green/red/yellow), next-scheduled-at (if known).
- The `threading.Timer` design **stays unchanged**. We add observability *next to* it, not under it. This is the deliberate replacement of old Phase 5 (APScheduler).

**Acceptance:** Maintainer can answer "wann lief die Automation?" by glancing at the dashboard. Restart of the container does not lose the historical executions (table persists; only "next-scheduled-at" recomputes from in-memory timers).

**Cross-cutting:** Rollback = drop the table + revert wrappers (Down-Migration). Flag = `SUBLARR_JOB_LOG_ENABLED` (default on; opt-out). Metric = panel-rendered count per session (proves it's actually used). Migration notes = "new table `job_executions`, no data loss on revert" in CHANGELOG. Docs = new wiki page `Operations / Scheduler`.

#### C2 — Backlog forecast widget

**Question answered:** *"Wie lange noch, bis alle Items mindestens einmal gesucht sind?"*

**Approach:**
- Aggregator service computes: `unsearched_count = wanted_items WHERE last_search_at IS NULL OR last_search_at < window_start`; `recent_throughput = COUNT(distinct wanted_id) FROM job_executions WHERE job_name='wanted_search' AND started_at > now() - interval '6h' / 6h`.
- ETA = `unsearched_count / recent_throughput`. Surface confidence band based on the variance of the last 14 days' throughput.
- Endpoint `GET /api/v1/system/forecast`. Widget on dashboard: "X items waiting, current rate Y/h, ETA ≈ Zh".
- Honest about uncertainty: if `recent_throughput` is 0, show "stalled" rather than infinity.

**Acceptance:** Maintainer can answer "wie lange noch" without opening any other page. Widget displays "stalled" correctly when scheduler is paused.

**Cross-cutting:** Rollback = revert. Flag = N/A (read-only widget). Metric = forecast accuracy: log predicted vs. actual completion time over a 30-day window, target |error| < 25 %. Migration notes = depends on C1 (`job_executions` exists). Docs = same wiki page as C1.

#### C3 — Coverage inventory

**Question answered:** *"Wie viele Subs fehlen pro Sprache?"*

**Approach:**
- Aggregator: per-language, per-show, per-season coverage map. Compute from `subtitles JOIN episodes JOIN series` grouped by `(series_id, season, language)`.
- Endpoint `GET /api/v1/library/coverage?group_by=language|series|season`.
- Dashboard widget: bar chart "Englisch 99 %, Deutsch 78 %, Japanisch 12 %". Drill-down to per-series view shows which series pull the average down.
- Cached aggregate refreshed every 10 min; on-demand refresh button for the impatient.

**Acceptance:** Maintainer sees gap distribution at a glance. Drill-down identifies the biggest gap-causing series in <2 clicks.

**Cross-cutting:** Rollback = revert. Flag = N/A. Metric = panel-rendered count per session. Migration notes = none (read-only on existing tables). Docs = wiki page `Library / Coverage`.

---

### Bucket A — UX Hardening (priority 3)

Addresses (d). UX work goes last because (a) Bucket B makes refactors safer and (b) Bucket C produces data that tells us *which* UX flows are objectively painful, not just felt-painful.

#### A1 — Design-system enforcement

**Pain:** "Keine Paddings um Text und Buttons" — symptom of an unenforced design system. CSS values are sprinkled inline / per-component; tokens exist (`mockups/concept-final.html` per memory) but are not applied consistently.

**Approach:**
- Inventory current spacing/typography/color usage with a custom audit script (`tools/css_audit.ts`) — flags any literal value (px, rem, hex) outside an allowlist of CSS variables.
- Add a stylelint rule `declaration-strict-value` configured to allow only token references for `padding`, `margin`, `font-size`, `color`, `background-color`, `border-radius`.
- Sweep every page until the audit is clean.

**Acceptance:** CSS audit reports 0 violations. Visual regression: maintainer reviews each major page screenshot before/after, confirms "feels right".

**Cross-cutting:** Rollback = revert. Flag = N/A (visual). Metric = audit-violation count (target: 0). Migration notes = N/A. Docs = `docs/DESIGN.md` (new) describes token system + `CLAUDE.md` adds rule.

#### A2 — Settings IA refactor

**Pain:** *"Setting-Seite ist sehr schlimm vom Nutzen her — umständlich und schwer zu verstehen."* 13+ tabs, 700+ LOC per tab, no in-page search, inconsistent FormGroup patterns.

**Approach:**
- Information-architecture redesign: group tabs into **5 top-level sections** (Library, Providers, Translation, Automation, System). Each section has 1–3 sub-tabs max.
- Add **"Search settings…"** field at the top of the Settings page: fuzzy-matches setting names, jumps to + highlights the matching field.
- Standardize on the existing locked components (`SettingsSection`, `FormGroup`, `Input` per memory) — refactor any tab that diverges.
- Each tab gets a one-line summary at the top ("This page controls how Sublarr connects to Sonarr/Radarr").

**Acceptance:** Maintainer can find any setting in <5 sec. Each tab follows the same component patterns. No tab exceeds 600 LOC (giving 200 LOC headroom).

**Cross-cutting:** Rollback = git revert (no schema). Flag = N/A — IA change is global. Metric = (subjective) maintainer's "find any setting in <5 sec" passes. Migration notes = none (no settings semantics changed). Docs = wiki Settings pages reorganised to mirror new IA.

#### A3 — Experimental-UI sweep

**Pain:** *"UI ist noch sehr experimentell an manchen Stellen."* Some pages polished, others raw; inconsistency is visible to any user.

**Approach:**
- Page-by-page audit: per page, decide **polish** (bring up to baseline) or **gate** (hide behind `?experimental=1` query flag until polished).
- Polish baseline checklist: passes A1 audit; uses standard navigation header; loading states present; empty states present; error states present.
- Pages currently suspect (need maintainer triage): `Trash`, `Onboarding` (792 LOC), `History`, `Standalone` flow.

**Acceptance:** Every page reachable from the main navigation passes the baseline checklist. Anything below baseline is behind `?experimental=1`.

**Cross-cutting:** Rollback = revert (or unhide). Flag = `?experimental=1` query parameter for raw pages. Metric = ratio of pages-at-baseline / pages-total = 1.0. Migration notes = N/A. Docs = `docs/UX-BASELINE.md` (new) defines the checklist.

---

## 4. Inspiration Backlog

These items are preserved from the previous spec because the ideas are sound — they just do not address current pain. They are pulled from this list **only when** a real (a)–(f) pain emerges that they would solve. Pulling an item requires re-running the §1 doctrine check.

| ID | Source | Idea | Pull trigger |
|---|---|---|---|
| **I1** | old Phase 6 | Vendor 10+ additional `subliminal` provider adapters | A real user reports a missing provider for a real subtitle they need |
| **I2** | old Phase 7 | Bazarr-style language profiles (per-show language × forced × HI × score-cutoff × must-contain) | Maintainer or a user finds Sublarr's per-show controls insufficient for a specific real workflow |
| **I3** | old Phase 8 | Multi-provider translation (DeepL / OpenAI / Claude / Google / LibreTranslate) | Ollama becomes inadequate for a real workload (cost, latency, quality) |
| **I4** | old Phase 5 | Replace `threading.Timer` with APScheduler / Hangfire-equivalent | Timer-leak bug recurs **and** C1's `job_executions` data shows scheduler is the bottleneck |
| **I5** | old Phase 9 | Smart-Sync (run ffsubsync on every candidate, pick best) | Maintainer or user reports that the current sync-quality choice is wrong on a measurable fraction of episodes |
| **I6** | old Phase 7 | Composite scoring engine (release × hash × fps × forced × provider-rank × bonus/malus) | Current scoring picks a measurably worse subtitle than a human would on a fixture corpus |
| **I7** | B1 plan 2026-04-18 | Replace mixin pattern with composition for `ProviderManager` collaborators (SearchCoordinator, ConfigResolver, StatusReporter as injected attributes rather than base classes) | Any single mixin grows past ~400 LOC OR a mixin method-name collision forces MRO-sensitive changes. Current mixin pattern (SearchCoordinatorMixin alone is 878 LOC) is the warning signal. |

The Inspiration Backlog is *not* a TODO list. It is a "reasoned-about-and-deferred" list. Items can be deleted from it if the trigger does not arise within ~12 months — the cost of revisiting the idea fresh is lower than the cost of carrying stale plans.

---

## 5. Cross-cutting framework

Every Active Backlog item (Buckets B / C / A) must explicitly satisfy these five points before it counts as shipped. Rule from the brainstorming session: **"alle 5 verpflichtend, mit Ausnahme Punkt 2 (Feature-Flag) für rein interne Refactorings ohne Verhaltensänderung"**.

1. **Rollback plan.** How does the change come back out if it misbehaves in prod? Code revert is rarely sufficient: schema changes need explicit Down-Migration; data migrations need a documented Restore path. The plan is part of the commit message.
2. **Feature flag.** If user-facing or behaviour-changing, the change ships behind an env var (`SUBLARR_*`) or a `config_entries` row. Default is the *old* behaviour. Internal refactors that change zero observable behaviour are exempt — they instead require an extra-thorough test pass (B-bucket items typically fall here).
3. **Observability metric.** *One* metric, recorded in prod, that proves the change had its intended effect. Examples: B1 → `files_over_800_loc` count; A2 → maintainer's "<5 sec to find any setting" subjective pass; C1 → panel-render count per session. The metric is named in the spec for the item.
4. **Migration notes in CHANGELOG.** When DB or config is touched: the `/deploy` workflow already drafts changelog entries, but the maintainer adds an explicit "Up:" / "Down:" block describing the schema delta and how to revert it. This avoids the "I forgot how to roll this back" trap.
5. **Docs-with-code.** The wiki is updated in the same commit (or a follow-up commit on the same day) — never deferred to a "docs sprint". `python wiki_audit_features.py` reports 0 findings before the deploy. New wiki pages are listed in CHANGELOG.

A spec checklist for each Active Backlog item is therefore: "Rollback: …; Flag: …; Metric: …; Migration notes: …; Docs: …". Items that cannot fill all five lines are not yet ready to start.

---

## 6. Sequencing & cadence

**Priority order:** B → C → A. Within a bucket, the order is whatever the maintainer's energy supports. Across buckets, limited interleaving is allowed — e.g. ship 2 B-items, then 1 C-item, then return to B — but the next B-item should never be started while a higher-priority B-item is in-flight.

**Cadence:** Each item is one or more `/deploy` beta releases. No big-bang. Every release goes through the maintainer's existing `/deploy` skill: ruff/lint/tests gate → version bump → CHANGELOG → Docker build → push to GHCR → Cardinal pull → health check.

**Re-evaluation:** After all 11 Active Backlog items ship, the maintainer re-checks §2 conviction criteria. If "convinced", V1.0.0 launches with a separate launch spec (Reddit, HN, demo video, etc — the marketing-side stuff that the previous spec misclassified as engineering). If not convinced, a new round of pain-poll + bucket-scoping produces a fresh active backlog.

**Solo-maintainer reality:** Estimate is *not* given in weeks. Solo work is too variable to estimate reliably and committing to weeks creates artificial pressure that drives shortcuts. The maintainer ships when each item is right.

---

## 7. Anti-scope (explicit)

Items intentionally **not** in this roadmap:

- **No V1 launch artefacts** (Reddit post, Hacker News draft, demo video, Docker Hub mirror) until the maintainer is convinced. Marketing follows conviction; conviction does not follow marketing.
- **No competitive-feature-checkbox work.** Provider-count parity with Bazarr, scoring-engine parity with Bazarr, translation-provider parity with Lingarr — all preserved in §4 Inspiration but not active priority.
- **No multi-instance / Redis pub-sub work** (was previously deferred to V1.1). Speculative until two Sublarr instances run in production.
- **No mobile app.** Responsive web is the bar.
- **No Plex integration beyond the existing badge.** Plex's own subtitle picker is sufficient for Plex users.
- **No voice-to-subtitle (Whisper) in core.** Sister project `Sublar_LLM_Finetuning` covers that domain; users can integrate Whisper externally.
- **No feature flagging frameworks.** The §5 cross-cutting flag requirement is satisfied by env vars or `config_entries` rows. Adding a third-party flag system would itself be a Bucket-B-grade investment with no current pain.

---

## 8. Open questions for the next session

These are deliberately *not* resolved in this spec — they belong in the writing-plans phase or to specific item designs:

1. **B1 sequencing within the bucket** — which god-file first? Suggestion: `config.py` (highest churn = highest reward), but maintainer's call.
2. **C1 retention policy** — how many days of `job_executions` to keep before pruning? Suggestion: 30 days, configurable.
3. **A2 IA grouping** — the proposed 5 top-level sections are a starting point, not gospel. The actual grouping deserves its own brainstorming round before implementation.
4. **B5 mutation-testing CI cost** — if mutation runs blow past acceptable runtime, may need to scope further (specific functions, not full files).
5. **A3 page triage** — which pages are "experimental" requires walking through them with the maintainer, page by page. Best done during the A3 implementation kickoff, not now.

These will surface as TODO entries in the implementation plan that follows this spec.

---

## Appendix — How to use this document

- **Before adding** anything to §3 Active Backlog: pass the §1 doctrine check.
- **Before deferring** anything to §4 Inspiration Backlog: state in writing why it does not address (a)–(f).
- **Before shipping** an Active Backlog item: confirm all 5 §5 cross-cutting deliverables.
- **Before the V1.0.0 spec is written**: confirm §2 conviction criteria are met for ≥ 14 consecutive days.
- **Quarterly**: re-read §1 doctrine. The (g) bias does not stay defeated; it returns. The doctrine is a vaccine, not a cure.
