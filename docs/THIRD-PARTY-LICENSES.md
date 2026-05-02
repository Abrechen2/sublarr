# Third-Party Licenses

This document lists every third-party component shipped or invoked by
Sublarr, together with its license and a compatibility note against
Sublarr's own license.

## Sublarr's License

Sublarr is licensed under **GPL-3.0-or-later** — see
[`LICENSE`](../LICENSE).

## Compatibility Rules

Anything in this document must be **GPL-3.0 compatible**. The matrix
distinguishes three integration kinds:

| Kind | Effect on us |
|---|---|
| **Static link / bundled** (npm `dependencies`, Python `pip install`) | License must be GPL-3 compatible at link-time. Permissive (MIT/BSD/Apache-2.0/ISC), LGPL-2.1+, GPL-3.0 are all OK. |
| **Subprocess invocation** (CLI binaries we exec) | License does not propagate. Even GPL-3 standalone binaries called via subprocess do not affect Sublarr's licensing. |
| **Optional / lazy import** (Python deps imported inside try/except) | Same rules as static link, applied at runtime if the dep is present. |

**Allowlist used by `license-checker` pre-deploy gate (frontend):**
```
MIT;BSD-2-Clause;BSD-3-Clause;Apache-2.0;ISC;LGPL-2.1-or-later;LGPL-2.1+;
GPL-3.0;GPL-3.0-or-later;MPL-2.0;0BSD;Unlicense;CC-BY-4.0;BSD;CC0-1.0
```
Anything outside this set fails CI and triggers a manual review.

---

## Backend — Python (`backend/requirements.txt`)

| Package | Version | License | SPDX | Compat |
|---|---|---|---|---|
| flask | 3.1.3 | BSD-3-Clause | `BSD-3-Clause` | ✅ |
| flask-socketio | 5.6.1 | MIT | `MIT` | ✅ |
| flask-limiter | 4.1.1 | MIT | `MIT` | ✅ |
| Flask-SQLAlchemy | 3.1.1 | BSD-3-Clause | `BSD-3-Clause` | ✅ |
| Flask-Migrate | 4.1.0 | MIT | `MIT` | ✅ |
| SQLAlchemy | 2.0.46 | MIT | `MIT` | ✅ |
| alembic | 1.18.4 | MIT | `MIT` | ✅ |
| anthropic | ≥0.39 | MIT | `MIT` | ✅ |
| apispec | ≥6.9.0 | MIT | `MIT` | ✅ |
| apispec-webframeworks | ≥1.0.0 | MIT | `MIT` | ✅ |
| flask-swagger-ui | ≥4.0.0 | MIT | `MIT` | ✅ |
| gunicorn | 23.0.0 | MIT | `MIT` | ✅ |
| pysubs2 | 1.7.3 | MIT | `MIT` | ✅ |
| requests | 2.32.4 | Apache-2.0 | `Apache-2.0` | ✅ |
| PlexAPI | ≥4.18.0 | MIT | `MIT` | ✅ |
| pydantic | 2.10.6 | MIT | `MIT` | ✅ |
| pydantic-settings | 2.7.1 | MIT | `MIT` | ✅ |
| python-dotenv | 1.0.1 | BSD-3-Clause | `BSD-3-Clause` | ✅ |
| simple-websocket | 1.1.0 | MIT | `MIT` | ✅ |
| rarfile | 4.2 | ISC | `ISC` | ✅ |
| deepl | ≥1.20.0 | MIT | `MIT` | ✅ |
| openai | ≥1.0.0 | Apache-2.0 | `Apache-2.0` | ✅ |
| google-cloud-translate | ≥3.10.0 | Apache-2.0 | `Apache-2.0` | ✅ |
| apprise | 1.9.2 | BSD-2-Clause | `BSD-2-Clause` | ✅ |
| prometheus-client | 0.25.0 | Apache-2.0 AND BSD-2-Clause | `Apache-2.0 AND BSD-2-Clause` | ✅ |
| psutil | 6.1.0 | BSD-3-Clause | `BSD-3-Clause` | ✅ |
| APScheduler | ≥3.10,<4 | MIT | `MIT` | ✅ |
| beautifulsoup4 | ≥4.12.0 | MIT | `MIT` | ✅ |
| bcrypt | 4.2.1 | Apache-2.0 | `Apache-2.0` | ✅ |
| click | ≥8.1,<9 | BSD-3-Clause | `BSD-3-Clause` | ✅ |
| lxml | ≥5.1.0 | BSD-3-Clause | `BSD-3-Clause` | ✅ |
| watchdog | ≥6.0.0 | Apache-2.0 | `Apache-2.0` | ✅ |
| guessit | ≥3.8.0 | **LGPL-3.0-or-later** | `LGPL-3.0-or-later` | ✅ (LGPL-3 ⇄ GPL-3 fully compatible) |
| psycopg2-binary | 2.9.10 | LGPL-3.0-or-later | `LGPL-3.0-or-later` | ✅ |
| redis | 7.1.0 | MIT | `MIT` | ✅ |
| rq | 2.6.1 | BSD-3-Clause | `BSD-3-Clause` | ✅ |
| setuptools | ≥70,<81 | MIT | `MIT` | ✅ |
| ffsubsync | ≥0.4.26 | MIT | `MIT` | ✅ |
| chardet | ≥5.2.0 | **LGPL-2.1-or-later** | `LGPL-2.1-or-later` | ✅ |
| dogpile.cache | ≥1.3.0 | MIT | `MIT` | ✅ |
| pysrt | ≥1.1.2 | **GPL-3.0** | `GPL-3.0` | ✅ same license as Sublarr |
| stevedore | ≥5.2.0 | Apache-2.0 | `Apache-2.0` | ✅ |

### Vendored

- **Subliminal 2.2.0** — vendored under `backend/providers/_vendor/`.
  Original license: **MIT** (https://github.com/Diaoul/subliminal).
  Vendor copy preserves `LICENSE` file; modifications documented in
  `backend/providers/_vendor/CHANGES.md` (if any).

### Optional / lazy imports added in Plan B8

| Package | Version | License | SPDX | Compat |
|---|---|---|---|---|
| scenedetect | ≥0.6.6,<1.0 | BSD-3-Clause | `BSD-3-Clause` | ✅ Lazy-imported in `services/scene_detector.py` — graceful degradation if absent. Added in 0.83.0-beta cycle (Task 2). |

### Optional / lazy imports added in Plan B9

| Package | License | SPDX | Compat |
|---|---|---|---|
| subaligner | MIT | `MIT` | ✅ |
| numpy (if not already transitive) | BSD-3-Clause | `BSD-3-Clause` | ✅ |

---

## Frontend — npm (`frontend/package.json`, production deps only)

Summary as of 2026-05-02 (`license-checker --production --summary`,
excluding the Sublarr workspace itself):

| License | Count |
|---|---|
| MIT | 344 |
| ISC | 42 |
| Apache-2.0 | 28 |
| BSD-3-Clause | 10 |
| BSD-2-Clause | 7 |
| 0BSD | 2 |
| MPL-2.0 | 1 |
| `MIT AND ISC` | 1 |
| `BSD` (unspecified variant) | 1 |
| Compound (LGPL-2.1+ AND others) | 1 |

**All entries above are GPL-3 compatible.**

Notable production dependencies for Plan B8 / B9:

| Package | License | Used for |
|---|---|---|
| `wavesurfer.js@7.x` | BSD-3-Clause | Waveform editor base |
| `wavesurfer.js/plugins/regions` | BSD-3-Clause | Drag-resize regions (B8) |
| `wavesurfer.js/plugins/spectrogram` | BSD-3-Clause | Spectrogram (B8) |
| `react-hotkeys-hook` (verify) | MIT | Keyboard shortcuts (B8) |
| `@dnd-kit/sortable` (verify) | MIT | Sortable engine chain (B9) |
| `@tanstack/react-query` | MIT | API client |
| `axios` | MIT | API client |
| `lucide-react` | ISC | Icons |
| `i18next` / `react-i18next` | MIT | i18n |

### Manual verifications

These packages were flagged as `UNKNOWN` or non-SPDX strings by
`license-checker` and were verified manually:

| Package | Declared | Actual upstream | SPDX |
|---|---|---|---|
| `parse-cache-control@1.0.1` | "BSD" (unspecified) | MIT — see https://github.com/roryf/parse-cache-control/blob/master/LICENSE | `MIT` |
| `frontend@0.0.0` | UNLICENSED | Sublarr workspace itself; covered by repo `LICENSE` (GPL-3.0) | `GPL-3.0-or-later` |

### Compound-license entries

`fontkit` (and similar font tooling) ships under
`LGPL-2.1-or-later AND (FTL OR GPL-2.0-or-later) AND MIT AND
MIT-Modern-Variant AND ISC AND NTP AND Zlib AND BSL-1.0`. This is the
union of upstream font-format readers; **all components are GPL-3
compatible** because LGPL-2.1-or-later, MIT, ISC, NTP, Zlib, and BSL-1.0
are all permissive or weak-copyleft. FTL (FreeType License) and
GPL-2.0-or-later use an alternation — for our purposes we choose the
GPL-2.0-or-later track, which combines with our GPL-3-or-later as
GPL-3-or-later.

---

## External Binaries (subprocess invocations)

These are not linked to Sublarr — we exec them as separate processes.
GPL/LGPL of these binaries does **not** propagate to Sublarr.

| Binary | License | Source | How invoked |
|---|---|---|---|
| `ffmpeg` | LGPL-2.1+ (default build) or GPL-2.0+ (with `--enable-gpl`) | https://ffmpeg.org/ | subprocess: `ffmpeg`, `ffprobe` |
| `alass-cli` | GPL-3.0 | https://github.com/kaegi/alass | subprocess (sync engine) |
| `mkvmerge` (when present) | GPL-2.0 | https://mkvtoolnix.download/ | subprocess (Plan B6 post-processing) |

---

## Asset Provenance (no copy from Aegisub / SubtitleEdit)

Sublarr's UI does **not** include code, icon glyphs, audio fixtures, or
artwork copied from:

- **Aegisub** (BSD-3-Clause partial / Various) — only feature
  inspirations are taken (e.g., the Medusa-style keyboard map convention
  S/D/F/G; keyboard interaction conventions are not copyrightable).
- **SubtitleEdit** (GPL-3.0 partial / Various) — only feature inspirations.
- **Bazarr / Lingarr / Subzero** — independent codebase, no shared code.

Sublarr's frontend icons come from `lucide-react` (ISC). Test fixtures
under `backend/tests/fixtures/` and `frontend/src/__tests__/fixtures/`
are either generated by Sublarr or sourced from public-domain creative
commons libraries; the provenance file
`backend/tests/fixtures/PROVENANCE.md` (TODO if missing) lists the source
of every binary fixture.

---

## Tier-3 Components (deferred — compliance plan)

These are mentioned in `Plan B8` and `Plan B9` as Tier-3 future work.
If/when they are picked up, the following compliance steps are required
before merge:

### `@ffmpeg/ffmpeg` (ffmpeg.wasm) — Plan B8 Tier 3

- License: MIT bindings + LGPL-2.1+ FFmpeg core (compiled with
  `--disable-gpl`).
- Compliance:
  1. Bundle `LICENSE.txt` and `LICENSE.LGPL2.1.txt` alongside the
     `.wasm` blob in the static `dist/` output.
  2. Add a "Third-Party Licenses" link in the About modal pointing to
     this file.
  3. LGPL §6 obligation: provide a way for the user to relink with a
     modified FFmpeg — satisfied by the public source mirror at
     https://github.com/ffmpegwasm/ffmpeg.wasm. Document in this
     section.

### WhisperX — Plan B9 Tier 3

- License: BSD-2-Clause (https://github.com/m-bain/whisperX).
- Compliance:
  - Pure Python lib, optional dep — same handling as `subaligner`.
  - Heavy GPU dep (CUDA preferred, CPU usable but slow). May be
    deferred in favor of `stable-ts` (MIT,
    https://github.com/jianfch/stable-ts).

---

## Maintenance

This file is regenerated and reviewed:
- **On every Plan-phase deploy** — ` /deploy` skill checks that this
  file's last-modified date is newer than the most recent change to
  `requirements.txt` or `package.json`.
- **By the pre-deploy `license-checker` gate** — any unknown SPDX
  flagged by frontend tooling fails CI until added here.
- **Manually for backend deps** — `pip-licenses` is in the dev tooling
  but its output is curated into this document by hand (the global
  Python env can leak unrelated packages from other projects).

Last regenerated: 2026-05-02 (Plan B8 Pre-Flight).
