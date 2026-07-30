# Sublarr — Roadmap

> The current release line is **v1.9.x**. This page describes direction, not a
> commitment — items may shift, merge, or drop. The full release history lives
> in the [CHANGELOG](CHANGELOG.md).

---

## Where Sublarr stands

The core pipeline — search, scoring, download, *arr integration, standalone
mode, subtitle tooling — has been stable since 1.0 and has grown steadily
through the 1.x line. Sublarr is now leaving the pure "feature phase": the
most-requested capabilities either exist, or exist as open pull requests.

The next chapter is therefore **not 50 new features**. It is finishing,
surfacing, and documenting what is already built — with four themes:
**transparency, monitoring, extensibility, and developer experience** — on top
of an uncompromising reliability baseline.

## Guiding principles

1. **Reliability before features.** A subtitle manager must never damage a
   library. Data-integrity bugs preempt all feature work (see #156, #159).
2. **A deterministic, explainable core.** Scoring and selection stay
   rule-based and reproducible. Every automatic decision must be inspectable
   after the fact.
3. **Quality over quantity.** Prefer consolidating existing mechanisms over
   adding parallel ones. New configuration surface needs to earn its
   maintenance cost.
4. **AI assists, it never acts.** AI features explain, flag, and suggest —
   they never modify files or influence scores on their own (see
   [AI direction](#ai-direction) below).

---

## 🧱 Now — Consolidation

Roughly in priority order. Several items are open PRs that need review,
rebasing, and merge coordination rather than new code.

### Data integrity first

- **Ungated remux in the wanted search** (#159) and **hardlink-aware remux**
  (#160) — fixed by #171; the top-priority merge.
- **Repair tool for HI-removal damage** (#156) — promised, still open.
- **Migration discipline** — unify the diverged Alembic heads (a merge
  revision ships with the decision-log PR) so startup auto-upgrade works
  reliably again, and keep the chain linear from here on.

### Transparency: the decision log stack

Answering *"why was exactly this subtitle chosen?"* end-to-end:

- **Decision log** (#172) — record the full selection pipeline per search
  (provider skips/hits, filter funnel with per-candidate rejection reasons,
  download attempts, final pick) and expose it in History and Wanted.
- **Score breakdown everywhere** (#173) — persist the per-component breakdown
  and surface it consistently; no score points outside the breakdown.
- **History reasons, rollback & dry run** (#170) — "why is this entry here"
  column, one-click rollback, and a wanted **dry-run preview** (what *would*
  Sublarr do, without touching disk or DB).

Follow-ups once landed: retention/pruning for stored decision logs, docs.

### Profiles & scoring rules — then freeze

The "different strategies for anime / movies / TV" request, solved with
profile- and rule-mechanics in the proven *arr style rather than a generic
rule engine:

- **Per-profile provider selection + scoring presets** (#168)
- **Release-group tier ranking** (#164)
- **User-defined regex scoring rules** (#166) — Sonarr-release-profile-style
- **Per-series format requirement (ASS-only)** (#169)

After these land, rule mechanics are intentionally **frozen**: global weights,
presets, tiers, regex rules, fansub preferences and the penalty pipeline
already interact — the decision log exists precisely to keep that debuggable.
New rule surface only when decision logs demonstrate a real, recurring need.

### Monitoring in the app

- **Library & provider health dashboard** (#170) — missing/failed/unmatched
  totals plus per-provider health (circuit-breaker state ⋈ hit rate) as an
  in-app `/health` page; no Grafana required.
- Follow-up: surface queue depths (whisper, translation) on the same page.
- Historical trends (success rate over time, latency) stay in the bundled
  Grafana dashboards (`monitoring/grafana`) — the app shows *state*, Grafana
  shows *history*.

---

## 🔭 Next — Extensibility & developer experience

### Integrations & API

Outgoing webhooks (HMAC-signed, retried), a machine-readable event catalog,
WebSockets, health/statistics endpoints and OpenAPI already exist. Remaining:

- **Generated event reference** — the event catalog
  (`backend/events/catalog.py`) is the single source of truth; generate the
  public event/payload documentation from it instead of writing it by hand.
- **Wanted list export** (#175) — CSV/JSON export for external tooling.
- Explicit non-goal: **SSE**. WebSockets already cover live updates; a second
  streaming channel is maintenance without benefit.

### Extensibility

- **Custom HTTP/JSON provider** (#165) — connect private subtitle servers or
  any REST API through pure configuration, no plugin code required. Expected
  to absorb much of the raw "provider plugin" demand.
- **Plugin system: prove it before growing it.** Loader, manifest validation,
  hot reload, template and marketplace routes exist — but the official
  registry is empty. Before extending plugins to translators/notifiers/sync
  modules: publish real provider plugins, write the tutorial, fill the
  registry. If the custom HTTP provider satisfies the demand instead, keep
  the plugin surface deliberately small.
- Plugins run unsandboxed (same trust model as Bazarr) — any marketplace
  promotion must state this prominently. This is a security posture, not a
  feature gap.

### Developer experience

- Generated event reference (above) and the documented custom-provider
  contract (`docs/CUSTOM_PROVIDER_API.md`, #165).
- A plugin tutorial that goes beyond the bundled template.
- An architecture overview diagram for contributors.
- Explicit non-goal: hand-maintained **SDKs** — the OpenAPI spec is the
  contract; client code can be generated from it.

---

## 🤖 AI direction

AI stays a complement, never the core. The role that fits Sublarr is an
**explanation and suggestion layer on top of the deterministic pipeline** —
making the app more understandable and the tools more accessible, without
ever touching files or scores on its own.

### Guardrails (non-negotiable)

1. **AI reads, AI never writes.** Output is a badge, a hint, or a diff
   proposal the user applies — never an automatic file modification. (#156 is
   the standing reminder of why.)
2. **Local-first.** Ollama by default; cloud backends opt-in, routed through
   the existing cost tracker and prompt-safety layer.
3. **Advisory, never blocking.** A negative AI verdict flags, it never
   discards — the `dubtitle_verify` pattern.
4. **No chatbot.** AI results surface in existing UI patterns (badges,
   tooltips, diff views, modals).

### Candidate features, in order

1. **"Explain this" on the decision log** — turn the structured decision log
   (#172) into a localized plain-language explanation on demand. Read-only,
   zero risk, the single best synergy between transparency and AI.
2. **Subtitle quality badge** — sample ~30 cues per downloaded file; a local
   LLM rates MT likelihood, OCR artifacts, grammar density, encoding damage →
   green/yellow/red badge next to the existing MT/trust badges. The upgrade
   system keeps deciding by its own rules; at most, a red verdict marks the
   item as wanting an upgrade (the `mt_provisional` pattern: keep + keep
   seeking).
3. **OCR review as diffs** — after batch OCR, an LLM pass proposes
   corrections for suspect lines, shown in the editor's existing diff view;
   the user applies them.
4. **Glossary bootstrap** — propose per-series glossary entries (character
   names, honorifics, recurring terms) for the user to confirm; the most
   direct lever for graduating LLM translation from "experimental".
5. **Sync plausibility** — Whisper spot-checks at a few points of the file,
   flag "likely wrong cut / offset ~1.2 s" with a one-click ffsubsync/alass
   action.
6. **Title-match assistant** — LLM as a tie-breaker for ambiguous provider
   matches (romaji/alternate titles, season collapse) — in **manual search
   only**, never in the automatic path.

### Explicit AI non-goals

- AI-adjusted scoring — it would destroy the explainability the decision log
  provides; the score stays deterministic.
- Fully automatic AI correction pipelines — advisory diffs only.
- LLM-generated dashboard summaries — the health statistics speak for
  themselves.

---

## Ongoing

- **Provider maintenance** — keep the 21+ providers working as upstream APIs
  and sites change; add high-value providers on request.
- **Performance at scale** — smooth behaviour on very large libraries,
  faster scans, leaner resource use.
- **Translation maturity** — improve quality and reliability (glossaries,
  context windows) until LLM translation can graduate from "experimental".
- **Quality-of-life UI** — accessibility, mobile, waveform-editor polish,
  organic migration of legacy styles to the design-token system.
- **Community-requested features** — prioritised from GitHub
  Issues/Discussions and Discord feedback.

Have an idea? Open a
[Discussion](https://github.com/Abrechen2/sublarr/discussions) or
[Issue](https://github.com/Abrechen2/sublarr/issues).

---

## How to Contribute

See [sublarr.de/docs/development/contributing](https://sublarr.de/docs/development/contributing/)
for how to submit features, bug reports, and pull requests.
