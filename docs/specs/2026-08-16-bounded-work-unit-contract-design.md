# A unit-of-work contract for the Sublarr pipeline

**Date:** 2026-08-16
**Status:** Draft — awaiting review

## Problem

Four releases (1.11.2 through 1.12.1) have been spent on one symptom: scheduled
runs recorded as `timeout_abandoned` — "did not stop when asked". Each release
treated the job that reported the symptom. `cancel_grace_s` was raised from 60s
to 300s to 900s; a stop signal was pushed into worker threads; auto-sync was
moved off the search path. Three consecutive production sweeps on 2026-08-15/16
still ended `timeout_abandoned`.

The symptom is not a property of `wanted_search`. It follows from a missing
system rule: **nothing in Sublarr declares how long a unit of work may take**,
so no cancel grace can be chosen except by guessing against the last
measurement.

### What the code actually does

| Fact | Value | Source |
|---|---|---|
| Execution contexts that can run long work | 8 | see below |
| …that have a timeout, a grace and a history | 1 (APScheduler) | `services/scheduler/ticks.py:84` |
| …that persist work across a restart | 1 (`subtitle_automation_queue`) | `db/models/core.py` |
| JobSpecs declaring `cancel_grace_s` | 2 of 17 | `services/scheduler/__init__.py` |
| Default grace for the other 15 | `max(1, min(60, timeout_s // 10))` — capped at 60s | `services/scheduler/ticks.py:109` |
| Translation bound, per batch | 60–120s backend timeout + up to 120s slot wait | `translation/llm_base.py:84`, `translation/concurrency.py:106` |
| Translation bound, per file | **none** | `translator/manager.py:221` |
| Lines per batch | 15 | `config_settings.py:141` |
| Translation memory written | after the **whole** file succeeds | `translator/manager.py:101` |
| Search sweep parallelism | `min(4, cores - 2)` | `services/wanted_search_runner.py:72` |
| Queue drain parallelism | 1 (serial) | `services/subtitle_automation_runner.py` |
| `wanted_search` grace vs. largest reachable unit | 900s vs. unbounded | `services/scheduler/__init__.py:298` |

The eight execution contexts: APScheduler (17 jobs); the queue drain; the shared
`submit_background` pool (webhooks, batch extract) at `services/background_tasks.py:32`;
the translation `job_queue` pool (4 workers) at `app.py:352`; `HookEngine` (4)
at `app.py:434`; `WebhookDispatcher` (4) at `app.py:438`; the legacy backup
scheduler started outside APScheduler at `app_schedulers.py:42`; and the
standalone watcher.

`process_wanted_item` — the most expensive routine in the product — is reachable
from at least four of them: `wanted_search`, the Sonarr/Radarr webhook pipeline
(`routes/webhooks/__init__.py:125`), `mt_reseek`, and the manual HTTP routes.

### Four consequences

1. **`wanted_search`'s per-item unit is unbounded.** Steps 2 and 4 call
   `_translate_external_ass` inline (`wanted_search/process.py:443`). A file is
   translated 15 lines at a time; a 300–400 line episode is ~25 batches. Each
   batch is bounded; their product is not. No value of `cancel_grace_s` can be
   correct against that, including the 900s currently defended in a comment.

2. **A stop request cannot reach the translation.** Neither `translator/` nor
   `translation/` contains a single `abort_requested()`. `wanted_search/process.py`
   checks only between its four steps. Adding checks inside would still not work
   from every caller: `translation/deepl_backend.py:146` creates its own
   `ThreadPoolExecutor`, and contextvars do not cross into a pool the code
   creates itself — the trap already documented at
   `services/scheduler/cancellation.py`.

3. **Interrupting a translation destroys all of its work.**
   `_store_translations_in_cache` runs after the batch loop
   (`translator/manager.py:101`), so a run stopped at batch 20 of 25 caches
   nothing. The same is true of an ordinary failure: one bad batch discards
   every batch before it.

4. **Webhook work is ungoverned and invisible.** `_webhook_auto_pipeline` runs
   the same pipeline on a pool thread with no timeout, no cancellation event, no
   persistence and no history row. The abort checks in `process.py` are inert
   there, because no event is bound. On 2026-08-15 this made a
   `timeout_abandoned` verdict impossible to close: work continuing after a
   cancel was indistinguishable from concurrent webhook work — because genuine,
   ungoverned webhook work was running.

**In one sentence:** Sublarr has one expensive pipeline and eight ways to start
it, and governance is attached to the starter rather than to the work.

## What this design promises

Three guarantees, in priority order.

**G1 — Bounded.** Every expensive operation declares a maximum duration over the
*whole* operation, not over its smallest component.

**G2 — Stoppable.** A stop request takes effect within one declared unit. Not
immediately — `ffsubsync` and `ffmpeg` are subprocesses — but within an interval
known in advance.

**G3 — Survivable.** Interrupted work is either cleanly discarded or recorded so
the next attempt resumes rather than restarts.

The guarantees are enforced by a test, not by discipline. Each expensive
operation exposes its ceiling as a module constant; each `JobSpec` declares which
operations it can reach; a test asserts that a job's grace is at least the
largest unit it can reach. The test fails on first introduction — for
`wanted_search`, for `subtitle_automation` and for the 15 jobs on the 60s
default. That is the point: it writes the debt down instead of hiding it.

## Stage A — the work carries its own bound

### A1. Cache each batch as it completes

Move `_store_translations_in_cache` from after the loop into it, per chunk.

The number of database writes does not change: it is already one write per line
(`translator/cache.py:55`), only their timing moves. What changes:

- An interrupted translation keeps its finished work.
- **The existing translation memory becomes the resume mechanism.** No progress
  column, no partial output file, no new state.
- The ordinary failure path improves: a bad batch 21 no longer discards 1–20.

A1 lands first and alone. It is a strict improvement with no behaviour change,
and it is what makes a deadline affordable — without it, "stop at the deadline"
means "discard up to 25 batches of LLM work", and nobody will enable it.

Known property, unchanged by A1 but made more visible: the cache is keyed by
source language, target language and source line — **not** by backend. Switching
translation backends returns previously cached lines. This is already true for
completed files; after A1 it is also true for interrupted ones.

Second known property, and the real cost of A1. `_apply_translation_cache`
removes cache hits *before* chunking (`translator/manager.py:50`), so
`_translate_in_batches` only ever sees the uncached subset and
`build_chunks` draws lookback/lookahead from that subset — not from the
original neighbours. A resumed translation therefore translates its tail with
context taken from the tail. Today an interrupted file caches nothing, so its
retry is a clean full pass with full context; after A1 it is not.

This is a trade, and it is worth taking: a seam whose context is thinner
against nine batches of paid LLM work thrown away. It is not free, and if
seam quality ever proves to matter, the follow-up is to let the chunker see
cached lines as *context* without re-translating them — a change to
`build_chunks` and the cache split, not to A1.

**Status: implemented 2026-08-16.** Each verified batch is written by
`_cache_batch` from inside the loop; the bulk write after the loop is gone, so
no line is stored twice.

### A2. A deadline over the whole file

`_translate_in_batches` takes an absolute deadline and checks it at
`translator/manager.py:221`, between chunks, where `all_translated` is a complete
prefix of the file. On expiry it raises a distinct error carrying how far it got.

### A3. The stop signal is a parameter, not a contextvar

The checkpoint at the same location reads an explicitly passed signal. This is a
deliberate departure from the existing `cancellation` mechanism: a parameter
cannot fail to cross a pool boundary, and the pool boundary is exactly where the
existing mechanism has failed twice. `abort_requested()` stays as-is for the
sweep loops where it already works.

### A4. Declared units, and the test that checks them

Each expensive operation exposes `MAX_UNIT_S`. Each `JobSpec` declares the
operations it can reach. A test asserts `effective_cancel_grace_s >= max reachable
MAX_UNIT_S`. Jobs that cannot yet satisfy it are listed explicitly in the test as
known debt, with the reason — so the list shrinks visibly rather than silently.

### A5. Remove the self-created pools

Two sites: `translation/deepl_backend.py:146` (`max_workers=1`) and
`dedup_engine.py:151` (`max_workers=4`). Note what the first one is for: it
enforces its timeout with `future.result(timeout=60)`, which stops *waiting*
while the thread runs on. Under load that leaks threads.

**Order within A:** A1 → A2 + A3 → A4 → A5.

**A does not fix:** webhook work still has no persistence and no history. That is
Stage B.

## Stage B — one place for expensive work

### The constraint that shapes B

The search sweep is currently the parallel translation engine: up to four items
at once, each possibly mid-translation. The queue drain is serial. Moving
expensive work into the drain unchanged would cut translation throughput
fourfold. B must not be a throughput regression.

### B1. The row owns the intent; a bounded pool owns the execution

The queue row remains the durable statement "this file owes work", with retry,
backoff and restart-survival. The drain stops executing in its own thread and
instead runs claimed rows through a bounded pool sized like the sweep's, with a
per-task-type ceiling: sync stays at 1 (`sync_subprocess_lock` is already a
`BoundedSemaphore(1)`), translation gets the pool.

B1 must land with or before B2.

### B2. The search enqueues instead of carrying

Steps 2 and 4 stop calling `_translate_external_ass` and write a
`sidecar_translate` row instead — the task type already exists, introduced in
1.11.3 for exactly this shape. The search step ends after the download.

This is the payoff: `wanted_search`'s unit falls from *unbounded* to *one provider
search (`provider_search_timeout = 30`) plus one download*. Only then is its
cancel grace a meaningful number, and a small one.

### B3. The webhook enqueues instead of running

`_webhook_auto_pipeline` writes a row instead of starting a daemon thread.
Webhook work gains persistence, retry, history and the run label. The
`webhook_delay_minutes` wait (default 5) becomes a future `next_retry_at` rather
than a pool thread held asleep per import.

B3 lands last: same mechanism as B2, but the webhook path has no safety net
today, so it should inherit experience from B2 rather than lead.

### B4. The job row must tell the truth

`create_job` (`db/jobs.py:18`) only writes a database row; it does not dispatch.
Steps 2 and 4 create one and then translate on the search thread, so the UI shows
work as queued that never was. Either the row is created when the drain actually
starts, or the enqueue is real.

### Deliberately out of scope

Merging the two queue systems. `job_queue` (`app.py:352`, Redis-capable, 4
workers) keeps user-initiated translations: interactive work must not queue
behind a 2000-item backlog. Two queues with clearly different jobs are more
honest than one queue with two priorities.

## Verification

Each step is proven, not asserted.

| Step | Proof |
|---|---|
| A1 | Interrupt a multi-batch translation; assert completed batches are in the cache and a re-run performs only the remaining batches. |
| A2 | Deadline already in the past → the loop stops after the current chunk and raises with a batch count. |
| A3 | Run the checkpoint from inside a self-created `ThreadPoolExecutor` and assert it still sees the stop. This is the test that would have caught the 2026-08 contextvar failures. |
| A4 | The test itself. Its initial failure list is the record of what is not yet bounded. |
| B1 | Throughput measurement: N queued translations, wall-clock before and after, against the sweep's current four-way parallelism. |
| B2 | On the RC instance against the production mirror: a `wanted_search` run that overruns must record `timeout`, not `timeout_abandoned`. This is the outstanding proof from 1.12.1. |
| B3 | Restart the container mid-webhook-import; the work must still complete afterwards. Today it is lost. |

Two claims from the existing code must be re-measured rather than trusted: the
`subtitle_automation` grace currently fails 5 runs in 12, and the "~16 minutes"
figure for a translation is an observation, not a bound.

## Risks

**Latency.** A translation no longer happens during the search but in following
drain ticks. For a 2000-item first run this is the same work, differently
scheduled. For a single new episode via webhook it adds up to one drain interval
(default 2 minutes).

**A partially cached file under changed settings.** See A1: cache keys exclude
the backend. Changing backend and re-running returns previously cached lines.
Pre-existing, but A1 widens the window in which it is observable.

**The A4 test will be red on arrival.** That is intended, but it means the test
must ship with an explicit, reasoned exemption list, or it will simply be
disabled by the next person who sees it fail.
