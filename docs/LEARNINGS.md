# Learnings — Sublarr

> Lessons learned during development. Add new entries at the top.

## Template

| Date | Topic | Learning |
|------|-------|----------|
| YYYY-MM-DD | Topic | What was learned |

## Entries

| Date | Topic | Learning |
|------|-------|----------|
| 2026-03-19 | Security | Pentest findings F-12 and F-13 (DB creds in config API, config value validation) fixed in 0.31.0-beta via `get_safe_config()` masking and enum/length validation in `routes/config.py` |
| 2026-03-19 | Security | Dot-notation URL keys (e.g. `whisper.subgen.url`) bypassed SSRF validation — fixed by routing all URL-like config keys through `validate_service_url()` |
| 2026-03-18 | Security | Deep research revealed 6 additional threat vectors (P1-P6) beyond pentest findings — domain allowlist for provider download URLs (P1) is the highest-priority open item because DNS rebinding can bypass IP-based blocklists |
| 2026-03-18 | Security | IP-blocklists for SSRF are insufficient due to DNS rebinding attacks; domain allowlists are structurally safer because unknown domains are simply blocked |
| 2026-03-18 | Security | Bazarr (the main comparable project) has zero protections for ZIP Slip, ZIP bombs, subtitle content sanitization, rate limiting, or SSRF — Sublarr is structurally ahead but still has open gaps in provider download URL validation |
| 2026-03-18 | Security | SocketIO log handler was forwarding raw database error messages (table names, column names) to WebSocket clients — fixed by filtering `psycopg2`/SQLAlchemy errors before emission |
| 2026-03-16 | Security | Pentest revealed 16 findings across two rounds; production password `sublarr` guessed in <2 seconds from an 8-item wordlist due to absent rate limiting (F-02 + F-16) |
| 2026-03-16 | Security | Auth middleware ordering bug (F-03): when `SUBLARR_API_KEY` is set, all `/api/v1/auth/` paths were blocked before the UI auth handler could run — single-line exemption fix |
| 2026-03-16 | Architecture | `_db_lock` is a no-op shim — SQLAlchemy handles thread safety via session scoping; adding `with _db_lock:` blocks in new code is unnecessary and misleading |
| 2026-03-14 | Standalone mode | `os.walk()` does not follow symlinks by default — caused standalone scanner to miss symlinked media directories; fixed with `followlinks=True` |
| 2026-03-14 | Standalone mode | Raw SQL strings must be wrapped in `sqlalchemy.text()` — SQLAlchemy deprecation warnings were silently swallowed in production |
| 2026-03-13 | Architecture | `werkzeug.secure_filename()` alone does not reliably strip `../` in all cases — always combine with `os.path.realpath()` + prefix check as a backstop |
| 2026-03-12 | Security | ZIP Slip and git clone SSRF/RCE vectors identified in marketplace plugin installation — `safe_zip_extract()` and `validate_git_url()` added as canonical mitigations in `security_utils.py` |
| 2026-03-12 | Security | CORS wildcard `"*"` on Socket.IO was silently allowing cross-origin WebSocket connections — replaced with configurable `SUBLARR_CORS_ORIGINS` |
| 2026-03-11 | Architecture | Circuit breaker pattern (CLOSED/OPEN/HALF_OPEN) per provider prevents cascading failures when a subtitle provider goes down — also reused for translation backend isolation |
| 2026-03-11 | Performance | `@tanstack/react-virtual` virtual scroll replaced client-side pagination for Library and Wanted lists — DOM node count reduced from thousands to ~50 visible rows |
