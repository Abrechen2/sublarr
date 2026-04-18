# Sublarr V1 — Competitive Parity & Launch Plan

**Date:** 2026-04-18
**Status:** Strategic plan
**Premise:** We've just shipped 0.53.1-beta (Phase 4a done). Before stamping V1, close the gaps against Bazarr, Lingarr and Subservient so Sublarr wins on every comparable axis — or is at least on par. Every gap below maps to a Phase.

---

## Competitor snapshot (2026-04-18)

| | Sublarr today | Bazarr | Lingarr | Subservient |
|---|---|---|---|---|
| Stars | — | 3928 | 756 | 45 |
| Stack | Python/Flask/React 19 | Python/Flask/Vue | C#/.NET + Hangfire | Python CLI |
| Providers | 11 | ~20 (Subliminal) | n/a | OpenSubtitles only |
| Translation | Fine-tuned Ollama | n/a | multi-provider factory | n/a |
| Scheduler | `threading.Timer` | APScheduler | **Hangfire** | cron/manual |
| Provider fault-isolation | CB + Multi-Key pool (best) | static throttle map | n/a | n/a |
| Sync quality strategy | ffsubsync+alass chain | subzero vendored | **"Smart Sync": test all, pick best** | n/a |
| Per-show profiles | priority_override + min/day | **Language Profiles** | n/a | n/a |
| Audit-log entities | activity_log | full history tables | **TranslationRequestEvent** entity | n/a |
| Live UI push | SocketIO | SocketIO | SignalR Hub | n/a |
| Anime-specific | AniDB, AnimeTosho, Jimaku, absolute-order | limited | n/a | n/a |
| Community | — | mature (9 yrs) | growing | niche |

## Gap matrix

Legend: ● = we're ahead   ◐ = parity   ○ = behind   — = not applicable

| Capability | vs Bazarr | vs Lingarr | vs Subservient | Close-the-gap owner |
|---|---|---|---|---|
| Provider count | ○ | — | — | Phase 6 |
| Provider fault-isolation | ● | — | — | keep |
| Rate-limit learning | ● | — | — | keep |
| Subtitle scoring | ○ | — | — | Phase 7 |
| Per-show language profiles | ○ | — | — | Phase 7 |
| Translation providers | — | ○ | — | Phase 8 |
| Translation quality | — | ● (fine-tuned) | — | keep |
| Job scheduling | ◐ | ○ | — | Phase 5 |
| Persistent retries | ○ | ○ | — | Phase 5 |
| Sync quality ("Smart Sync") | — | — | ○ | Phase 9 |
| Event/audit log | ○ | ○ | — | Phase 9 |
| Live UI push | ◐ | ◐ | — | keep |
| Anime features | ● | ● | ● | keep |
| Docs + wiki coverage | ○ | ◐ | ◐ | Phase 10 |
| Community presence | ○ | ◐ | ◐ | Phase 10 |

---

## Phase roadmap to competitive parity

### Phase 5 — Scheduler hardening (replaces fragile threading.Timer)
**Goal:** Replace the hand-rolled timer-based scheduler with a proper job queue and retry framework so we match Lingarr's Hangfire-level robustness.

Scope:
- Migrate `WantedSearchRunner`, `CleanupScheduler`, `UpgradeScheduler`, `TickRecovery` off `threading.Timer` onto **APScheduler** (Python equivalent of Hangfire for our scale) with a Postgres job store so jobs survive restart.
- Add retry policy per job (`max_retries`, backoff, dead-letter queue for permanent failures).
- New `/api/v1/system/jobs` endpoint + UI panel showing running / queued / failed jobs with manual retry + cancel.
- Kill the whole "timer-leak fix" bug class permanently.

Exit criteria:
- Zero `threading.Timer` in `services/` or `routes/` hot paths.
- Restarting the container mid-scan resumes the job (not loses it).
- Every existing scheduled task now visible + controllable in the UI.

Estimate: ~1 week of focused work. Touches `services/wanted_search_runner.py`, `services/cleanup_scheduler.py`, adds `services/job_runner.py` + new routes + new UI panel.

---

### Phase 6 — Provider expansion (close the Bazarr count gap)
**Goal:** Match or exceed Bazarr's provider count by vendoring the remaining useful `subliminal` provider adapters as optional plugins.

Scope:
- Port / wrap: `addic7ed_dayz` (search-only fork), `titlovi`, `greeksubs`, `wizdom`, `podnadpisi`, `feliratok`, `assrt`, `zimuku`, `sucha`, `yavka.net`.
- Adapter-layer so each provider matches our `SubtitleProvider` base class.
- Each new provider declares `rate_limits` so it flows through the Phase 1-3 budget manager.
- Per-provider quality/latency metrics in `/providers` dashboard for user-informed enable/disable.
- At least 5 of the ported providers covered by integration tests (HTTP-cassette fixtures, no live calls).

Exit criteria:
- ≥ 20 providers available out of the box. User enables in Settings → Providers.
- Every new provider honors the Phase 3 budget + Phase 4a key pool.

Estimate: ~1-2 weeks. Skeleton is cheap (adapter pattern), per-provider fiddle adds up.

---

### Phase 7 — Subtitle scoring + per-show language profiles (close Bazarr parity)
**Goal:** Match Bazarr's "Language Profiles" — per-show configuration of which languages to search, forced/HI preference, score threshold, provider whitelist.

Scope:
- Extend `SeriesSettings` (already has `priority_override`, `min_attempts_per_day`) with `language_profile_id` FK.
- New `LanguageProfile` entity: `{name, languages: [{code, forced, hi}], cutoff_score, must_contain, must_not_contain, upgrade_on_better_score}`.
- Scoring engine replaces our current ad-hoc score with a Bazarr-style composite (release-match + hash-match + fps-match + forced-match + provider-rank + bonus/malus rules).
- Settings UI for profile CRUD + assignment to series (drag-drop or dropdown).
- Profiles apply in both scheduled search AND manual search paths.

Exit criteria:
- User can define 3+ profiles, assign per-show, and the scheduler respects them.
- Scoring composite matches Bazarr's defaults within ±2 score points on a fixture sample.
- Existing behaviour preserved for series without an assigned profile.

Estimate: ~2 weeks. Meaty data-model change + frontend.

---

### Phase 8 — Translation provider plurality (close Lingarr gap)
**Goal:** Factory-pattern for translation backends. Fine-tuned Ollama stays the default; DeepL / OpenAI / Claude / Google / LibreTranslate become pluggable options so power-users with existing API subscriptions can opt in.

Scope:
- `TranslationProvider` abstract base with `translate_batch(lines: list[str], src, tgt, glossary) -> list[str]` contract.
- Adapters: `OllamaProvider` (existing logic, refactored), `DeepLProvider`, `OpenAIProvider`, `ClaudeProvider`, `GoogleProvider`, `LibreTranslateProvider`.
- Per-adapter settings (API key, model, endpoint) behind the same provider-keys-pool pattern as subtitle providers.
- Automatic fallback: primary adapter fails → next-in-chain retries with backoff.
- UI: Settings → Translation → Provider dropdown + add-key dialog (reuse `KeyEditDialog`).

Exit criteria:
- User can switch translation provider at runtime without restart.
- Existing Ollama-using installs unaffected (default, backwards compatible).
- Multi-provider fallback proven in integration test (primary raises → secondary succeeds).

Estimate: ~1 week. Mostly mechanical adapter writing + a small settings UI.

---

### Phase 9 — Sync quality + audit event log (close Subservient + Lingarr gaps)
**Goal:** Port Subservient's "Smart Sync" strategy as an optional mode, and introduce a Lingarr-style `translation_event` / `download_event` audit log.

Scope:
- **Smart Sync**: post-processing mode that runs ffsubsync on every matched subtitle candidate for a file, picks the one with the smallest residual offset, discards the rest. Opt-in via `post_processing.smart_sync = true`.
- **Event log**: new tables `translation_events` + `download_events` capturing every stage transition with metadata (provider, key_id, duration, score, error). Replaces/augments `activity_log` for these two domains.
- New UI panel Activity → Audit Log (per-event filter + drill-down).

Exit criteria:
- Smart Sync demonstrably picks a better-synced subtitle than First-Match on a test fixture where the top-ranked result has worse sync than the 3rd-ranked.
- Every download + translation fires at least 4 events (queued, started, completed_or_failed, finalized), visible in the audit UI.

Estimate: ~1 week.

---

### Phase 10 — Validation + launch polish (was the original "Phase 5 Validation")
**Goal:** Production-validate everything and prepare V1 launch artefacts.

Scope:
- Low-end ProxMox CT (1 CPU, 512MB) runs full rotation for 7 days without errors.
- Migration dry-run: backup prod DB → apply all migrations on staging → run 48h → diff `activity_log`.
- Wiki coverage: every new setting since v0.50 documented via `wiki_audit_settings.py`.
- CHANGELOG aggregated → GitHub v1.0.0 release notes.
- `README.md` rewrite: differentiate from Bazarr/Lingarr/Subservient in the opening 5 lines.
- Demo video (5 min screen-record) covering install + first search + budget dashboard + translation.
- Docker Hub listing for public discovery (mirror the GHCR image).
- Draft Reddit/r/selfhosted post + HackerNews "Show HN" draft.

Exit criteria:
- Low-end CT passes.
- Wiki gap-audit returns 0 findings.
- v1.0.0 release published with working demo video.
- Reddit post live, linked from README.

Estimate: ~1 week.

---

## Sequencing + dependencies

```
Phase 5 (scheduler)  ─┐
                      ├─► Phase 7 (profiles, needs robust scheduler)
Phase 6 (providers) ──┤
                      ├─► Phase 9 (audit log + smart sync)
Phase 8 (translation) ┘

                                   Phase 10 (validation + launch)
                                         ▲
                         all of 5-9 ─────┘
```

**Critical path:** Phase 5 → Phase 7 → Phase 9 → Phase 10 (~4 weeks).
**Parallel:** Phase 6 + Phase 8 can run alongside 5/7/9.

Total: **5–6 weeks** of focused work if done serially, **3–4 weeks** if parallelised.

---

## What we explicitly do NOT build (anti-scope)

- **Multi-instance Redis pub/sub budget sharing** — Phase 4b territory, speculative until someone runs multi-Sublarr.
- **Cost tracking of translation providers** — too provider-specific, reconsider post-V1.
- **Mobile app** — out of scope, responsive web UI is sufficient.
- **Plex integration beyond badge** — Plex's sub-picker is good enough for its users; we're not competing there.
- **Voice-to-subtitle (whisper)** — already covered by separate Sublar_LLM_Finetuning ecosystem + external whisper integration. Keep out of core.

---

## After V1.0 — what comes next (informational)

- **V1.1 — Multi-instance Redis sharing** (Phase 4b originally deferred).
- **V1.2 — Cost/utilization tracking** + billing page for paid provider tiers.
- **V1.3 — Plugin marketplace** (custom provider + post-processor plugins).

---

## Success definition for V1 launch

By V1.0.0:
1. Every gap ● in the gap matrix above is closed (min: ◐ parity).
2. Sublarr provider count ≥ 20.
3. Sublarr passes all integration tests on low-end CT for 7 days.
4. Wiki covers 100% of settings.
5. Reddit `r/selfhosted` post receives no "how is this different from Bazarr?" comments unanswered within 24h.
