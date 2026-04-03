---
phase: 1
plan: 1
subsystem: security
tags: [security, providers, ssrf, prompt-injection, streaming, filename-sanitization, webhook]
dependency_graph:
  requires: []
  provides: [validate_download_url, _validate_magic_bytes, _stream_download, prompt-injection-guard, webhook-signature-warning]
  affects: [providers/__init__.py, providers/opensubtitles.py, providers/betaseries.py, providers/titlovi.py, providers/jimaku.py, providers/napisy24.py, providers/subsdump.py, security_utils.py, translation/llm_utils.py, auth.py]
tech_stack:
  added: []
  patterns: [per-provider domain allowlist, magic-byte validation, streaming download with size cap, prompt injection escaping, glossary entry validation]
key_files:
  created: []
  modified:
    - backend/security_utils.py
    - backend/providers/__init__.py
    - backend/providers/opensubtitles.py
    - backend/providers/betaseries.py
    - backend/providers/titlovi.py
    - backend/providers/jimaku.py
    - backend/providers/napisy24.py
    - backend/providers/subsdump.py
    - backend/translation/llm_utils.py
    - backend/auth.py
    - backend/tests/test_security.py
decisions:
  - id: D1
    choice: "subsdump self-hosted: scheme-only validation"
    rationale: "subsdump is operator-deployed on any host (e.g. 192.168.x.x) — allowlisting domains would break legitimate installs; only http/https scheme enforced, private IPs explicitly allowed"
  - id: D2
    choice: "ASS format check: block only binary signatures, no header enforcement"
    rationale: "Initial implementation requiring [Script Info] header rejected valid ASS files; relaxed to binary-signature-only blocking since ASS is text-based and subtitle_sanitizer already handles malformed content"
  - id: D3
    choice: "_validate_magic_bytes wired into save_subtitle(), not download()"
    rationale: "save_subtitle() is the central choke-point where all provider content passes before being written to disk; avoids duplication across 6 individual provider download methods"
metrics:
  duration_minutes: ~60
  completed_date: 2026-04-03
  tests_added: 105
  tests_total_passing: 1020
---

# Phase 1 Plan 1: Security P1-P5 + F-05 Summary

**One-liner:** Per-provider SSRF domain allowlist, secure_filename sanitization, LLM prompt injection escaping, magic-byte format validation, 50 MB streaming cap, and webhook unsigned-request warning log.

---

## Tasks Completed

| Task | Name | Commits | Key Files |
|------|------|---------|-----------|
| 1 | P1 — validate_download_url() with domain allowlist | 56409f7, 02c33fe, b5fdb76 | security_utils.py |
| 2 | P1 — Wire validate_download_url() into all providers | 172687b | providers/__init__.py, 6 provider files |
| 3 | P2 — Filename sanitization with secure_filename() | 807c764, 4b6e8d3, 312991d | opensubtitles.py, providers/__init__.py |
| 4 | P3 — Prompt injection guard in llm_utils.py | 0b22b7b, 9cb8af3 | translation/llm_utils.py |
| 5 | P4+P5 — Magic-byte validation + 50 MB streaming cap | 8da8c2a, ee1e255, 9cb8af3 | providers/__init__.py, all 6 provider files |
| 6 | F-05 — Webhook signature warning log | 5365ac7 | auth.py |

---

## What Was Built

### Task 1: validate_download_url() (P1 SSRF guard)

Added `validate_download_url(url, provider_name)` to `security_utils.py`:
- **Per-provider domain allowlist** (`_PROVIDER_DOWNLOAD_DOMAINS`) mapping 20 providers to their allowed netloc suffixes
- **Local providers** (`embedded`, `whisper`) — always pass (no external URL)
- **Self-hosted providers** (`subsdump`) — scheme-only check (http/https), any hostname allowed including private LAN IPs
- **Unknown providers** — rejected with "unknown provider" error to prevent dynamic plugin bypass
- **All providers** — reuse existing `_BLOCKED_METADATA_HOSTS` and `_METADATA_NETWORKS` guards from `validate_service_url()`

### Task 2: Wire into provider download calls

Added URL validation in `ProviderManager.download()` immediately before `provider.download(result)` call. Also added inline validation in each individual provider's `download()` method as a defense-in-depth layer:
- `opensubtitles.py` — before `session.get(download_link)`
- `betaseries.py`, `titlovi.py`, `jimaku.py`, `napisy24.py`, `subsdump.py` — before their respective session.get calls

### Task 3: Filename sanitization (P2)

Applied `werkzeug.secure_filename()` at two layers:
- **`opensubtitles.py`**: sanitizes `file_name` from the `/download` API response before `os.path.splitext()`
- **`providers/__init__.py` `save_subtitle()`**: sanitizes `result.filename` before constructing the output path

### Task 4: Prompt injection guard (P3)

Added to `translation/llm_utils.py`:
- `_escape_subtitle_line(line)` — replaces `\r\n`, `\r`, `\n` with `\\n` so injected newlines cannot create additional numbered entries in the prompt
- `_is_valid_glossary_entry(entry)` — rejects entries where source or target term exceeds 100 chars or contains newline/CR characters
- Both applied in `build_prompt_with_glossary()` before prompt construction

### Task 5: Magic-byte validation + streaming cap (P4+P5)

Added to `providers/__init__.py`:
- `_validate_subtitle_content(content, fmt)` — blocks PE (`MZ`), ELF (`\x7fELF`), Mach-O, and Java class magic bytes; detects binary noise via null-byte density (>5%) and control-char ratio (>10%); wired into `save_subtitle()` before format detection
- `_stream_download(response, chunk_size)` — Content-Length preflight + per-chunk accumulation with 50 MB (`_MAX_SUBTITLE_SIZE`) hard cap; raises `RuntimeError` on overflow
- All 6 provider `download()` methods updated to pass `stream=True` and use `_stream_download()` instead of `.content`

### Task 6: Webhook signature warning (F-05)

Added to `auth.py` in the webhook exemption block:
- Emits `logger.warning` when a request to `/api/v1/webhook/*` arrives without `X-Signature` or `X-Bazarr-Signature` headers
- Warning includes path and remote_addr for incident response
- Does not block the request (behavioral parity maintained, security visibility added)

---

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Private LAN IP rejection for self-hosted subsdump**
- **Found during:** Task 1
- **Issue:** Initial implementation of `validate_download_url()` used the same `_METADATA_NETWORKS` IP guard for self-hosted providers, which blocked `192.168.x.x` addresses — where subsdump actually runs in production
- **Fix:** Self-hosted provider path now explicitly skips the IP range check; only scheme validation applies
- **Files modified:** `backend/security_utils.py`
- **Commits:** 02c33fe, b5fdb76

**2. [Rule 1 - Bug] Over-strict ASS format magic-byte check**
- **Found during:** Task 5
- **Issue:** Initial implementation required `[Script Info]` at start of ASS content, but valid ASS files can start with BOM or other valid section headers; tests failed on real ASS content
- **Fix:** Removed ASS-specific header enforcement; magic-byte validation now only blocks known binary signatures (PE, ELF, Mach-O, Java) and high null-byte/control-char density
- **Files modified:** `backend/providers/__init__.py`
- **Commits:** ee1e255

**3. [Rule 1 - Bug] opensubtitles exception type inconsistency**
- **Found during:** Task 3
- **Issue:** `opensubtitles.download()` was raising bare `RuntimeError` while other providers raise `ProviderError`; existing tests expected `ProviderError`
- **Fix:** Standardized opensubtitles exceptions to `ProviderError`; updated test mocks for betaseries/titlovi to match streaming context manager pattern
- **Files modified:** `backend/providers/opensubtitles.py`, `backend/tests/test_new_providers_batch2.py`
- **Commits:** 4b6e8d3, 312991d

**4. [Rule 2 - Missing critical functionality] Webhook warning checks both X-Signature variants**
- **Found during:** Task 6
- **Issue:** Plan specified checking only `X-Signature`; Bazarr uses `X-Bazarr-Signature` for its webhook calls — warning would fire for all Bazarr webhooks falsely
- **Fix:** Warning only fires when NEITHER `X-Signature` NOR `X-Bazarr-Signature` is present
- **Files modified:** `backend/auth.py`, `backend/tests/test_security.py`

---

## Test Results

- **Security test suite:** 127 passed, 2 skipped
- **Full pre-PR suite:** 1020 passed, 3 skipped, 0 failures
- **Frontend:** 0 errors (9 pre-existing warnings unchanged)
- **Ruff:** No violations on all modified files

---

## Self-Check: PASSED

All modified files verified present in worktree. All commits verified in git log.

Key files:
- `backend/security_utils.py` — `validate_download_url()` added
- `backend/providers/__init__.py` — `_validate_subtitle_content()`, `_stream_download()`, URL validation in `download()`, filename sanitization in `save_subtitle()`
- `backend/translation/llm_utils.py` — `_escape_subtitle_line()`, `_is_valid_glossary_entry()` added
- `backend/auth.py` — webhook unsigned-request warning added
- `backend/tests/test_security.py` — 105 new tests added (127 total passing)
