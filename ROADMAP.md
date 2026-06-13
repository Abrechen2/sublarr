# Sublarr — Roadmap

> The current release is **v1.0.0**. This page describes direction, not a
> commitment — items may shift, merge, or drop. The full release history lives
> in the [CHANGELOG](CHANGELOG.md).

---

## ✅ v1.0.0 — Stable Release

Sublarr 1.0 marks the point where the core subtitle-management pipeline is
considered stable for everyday use.

**What's stable**

- **Subtitle search & download** — 21 providers + embedded extraction, parallel
  search, per-provider circuit breakers, API-budget-aware key pooling
- **ASS-first scoring** — format / dialect / sync-quality / uploader-trust
  scoring with transparent per-component breakdowns
- **Language profiles** — `mustContain` / `mustNotContain`, cutoff, audioExclude,
  per-series/film overrides
- **\*arr & media-server integration** — Sonarr/Radarr webhooks, multi-instance,
  Jellyfin/Emby/Plex/Kodi library refresh, AniDB absolute-order handling
- **Standalone mode** — filesystem watching + NFO metadata, no *arr required
- **Subtitle tools** — Aegisub-class waveform editor, ffsubsync/alass sync,
  format conversion, post-processing pipeline, batch OCR, safe stream removal
- **Wanted & automation** — event-driven scanning, APScheduler-backed job admin
  (run-now / pause / resume / edit-trigger / history), upgrade system
- **Operations** — PostgreSQL & Redis support, Prometheus metrics, structured
  JSON logging, OpenAPI/Swagger at `/api/docs`, multi-arch Docker (amd64+arm64),
  Unraid Community Applications templates
- **Security** — path-traversal guards on all file endpoints, SSRF validation,
  ZIP-bomb/ZIP-slip protection, subtitle sanitization (Lua/HTML stripping),
  bcrypt auth + rate limiting, hardened CSP, atomic subtitle writes

**Experimental in 1.0**

- **LLM translation** (Ollama / DeepL / Google / LibreTranslate / OpenAI-compatible)
  remains experimental — quality varies by model, language pair, and content.
  Disabled by default; EN→DE anime is the best-tested path.

---

## 🔭 Beyond 1.0

Direction for the 1.x line, roughly in priority order. Concrete scope is decided
per release.

- **Reliability & polish** — continued hardening of the most-used paths, edge-case
  fixes surfaced by real-world libraries, and test-coverage growth
- **Provider maintenance** — keep existing providers working as upstream APIs and
  sites change; add high-value providers on request
- **Performance at scale** — smoother behaviour on very large libraries
  (500+ series), faster scans, leaner resource use
- **Translation maturity** — improving translation quality and reliability until
  it can graduate from "experimental"
- **Quality-of-life UI** — ongoing accessibility, mobile, and workflow
  improvements; organic migration of legacy inline styles to the design-token system
- **Community-requested features** — prioritised from GitHub Issues / Discussions
  and Discord feedback

Have an idea? Open a
[Discussion](https://github.com/Abrechen2/sublarr/discussions) or
[Issue](https://github.com/Abrechen2/sublarr/issues).

---

## How to Contribute

See [sublarr.de/docs/development/contributing](https://sublarr.de/docs/development/contributing/)
for how to submit features, bug reports, and pull requests.
