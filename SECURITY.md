# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in Sublarr, please report it privately via
[GitHub Security Advisories](https://github.com/Abrechen2/Sublarr/security/advisories/new).

**Do not** open a public issue for security vulnerabilities.

Please include:
1. Description of the vulnerability
2. Steps to reproduce
3. Affected version(s)
4. Potential impact

We aim to acknowledge reports within 48 hours and provide a fix within 7 days for critical issues.

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.0.x | Yes — current stable |
| 0.9x-beta | Best-effort — please upgrade to 1.0 |
| < 0.31.x | No — missing critical security fixes |

## Security Architecture

### Authentication

Sublarr supports two authentication mechanisms:

1. **API Key Authentication** — Set via `SUBLARR_API_KEY` environment variable. All `/api/v1/` endpoints require the key in the `X-Api-Key` header. Enforced by a global `before_request` hook in `auth.py`.

2. **UI Session Authentication** — Browser-based login with bcrypt-hashed passwords. Session cookies use `HttpOnly`, `SameSite=Lax` flags. Minimum password length: 8 characters.

**Important:** At least one authentication mechanism must be enabled. If both `SUBLARR_API_KEY` is empty and UI auth is disabled, a startup warning is logged and all endpoints are publicly accessible.

### Rate Limiting

- Login endpoint: 5 requests/minute per IP
- API key auth failures: 20 failures/60s per IP
- Powered by `flask-limiter` with in-memory or Redis backend

### Input Validation

- **Path traversal prevention:** `is_safe_path()` applied on all file/path endpoints. Validates paths resolve within allowed directories using `os.path.realpath()`.
- **SSRF protection:** `validate_service_url()` blocks `file://`, `ftp://`, cloud metadata IPs (169.254.x.x), link-local addresses, and custom blocked hosts. Applied to all config URL fields and webhook URLs.
- **Git URL validation:** `validate_git_url()` enforces HTTPS-only and domain allowlist (`github.com`, `gitlab.com`, `codeberg.org`) for plugin installations.
- **Config validation:** Enum fields validate against allowed values, string fields enforce max length (4096 chars).

### Injection Prevention

- **SQL Injection:** All database queries use SQLAlchemy ORM with parameterized queries. No raw SQL with user input.
- **XSS Prevention:** Subtitle files are sanitized before display — ASS/SSA files have Lua scripts and drawing commands stripped, SRT/VTT files have HTML tags sanitized.
- **Command Injection:** No user-supplied data reaches shell calls. External tools (mkvmerge, ffmpeg) receive arguments as list parameters, not shell strings.
- **Prompt Injection:** LLM translation inputs have subtitle lines escaped to prevent embedded newlines from manipulating the prompt structure.

### File Handling

- **ZIP bomb protection:** 50 MB max uncompressed size, 100:1 compression ratio limit via `safe_zip_extract()`.
- **ZIP Slip prevention:** All archive members validated against the target directory before extraction.
- **Subtitle sanitization:** ASS/SSA Lua script stripping, drawing-mode removal, SRT/VTT HTML tag sanitization.

### Cryptography

- **Password hashing:** bcrypt via `werkzeug.security.generate_password_hash()` / `check_password_hash()`
- **Timing-safe comparison:** `hmac.compare_digest()` for API key and webhook signature verification
- **Webhook signatures:** HMAC-SHA256 with per-instance secret keys

### HTTP Security Headers

Applied to all responses via `@app.after_request`:
- `X-Frame-Options: DENY`
- `X-Content-Type-Options: nosniff`
- `Referrer-Policy: same-origin`
- `Content-Security-Policy` (script-src self, style-src self unsafe-inline)
- `Permissions-Policy` (camera=(), microphone=(), geolocation=())

### Network Security

- **Webhook URL validation:** Blocks RFC1918 ranges and localhost to prevent SSRF
- **Provider download URLs:** Domain allowlist per provider to prevent SSRF via compromised provider APIs
- **Docker container:** Runs as non-root user (`sublarr`), single exposed port (5765)

### Circuit Breaker

Per-provider and per-backend failure isolation using a CLOSED → OPEN → HALF_OPEN state machine with configurable threshold and cooldown. Prevents cascading failures from affecting the entire system.

## Penetration Testing History

Sublarr has undergone three rounds of authorized penetration testing:

| Round | Date | Version | Tester | Findings |
|-------|------|---------|--------|----------|
| 1 | 2026-03-16 | 0.30.0-beta | Kali Linux | 11 findings (F-01 to F-11) |
| 2 | 2026-03-16 | 0.30.0-beta | Kali Linux | 5 findings (F-12 to F-16) |
| 3 | 2026-03-22 | 0.34.0-beta | BlackArch | 9 findings (F-17 to F-25) |

### Resolution Status

| Severity | Total | Fixed | Accepted | Open |
|----------|-------|-------|----------|------|
| CRITICAL | 4 | 4 | 0 | 0 |
| HIGH | 5 | 5 | 0 | 0 |
| MEDIUM-HIGH | 4 | 4 | 0 | 0 |
| MEDIUM | 5 | 4 | 1 (F-05) | 0 |
| LOW | 4 | 2 | 2 (F-08, F-15) | 0 |
| INFO | 3 | 0 | 3 | 0 |

All CRITICAL, HIGH, and MEDIUM-HIGH findings have been fixed as of v0.35.0-beta.

## Accepted Risks

| ID | Description | Rationale |
|----|-------------|-----------|
| F-05 | Webhook middleware exemption | By design — webhook paths use per-handler HMAC verification instead of global API key auth. Documented in `auth.py`. |
| F-08 | Socket.IO handshake unauthenticated | EIO4 open frame leaks only transport parameters (pingTimeout, pingInterval). Namespace connect is correctly rejected without auth. |
| F-15 | Internal network topology in config | Sublarr is an internal self-hosted tool. Config endpoint is auth-gated. Internal IPs in config values are expected and necessary for operation. |

## Confirmed Safe

The following attack vectors have been tested and confirmed mitigated:

- SQL Injection (parameterized queries)
- Path Traversal (`is_safe_path()` on all file endpoints)
- Command Injection (no user data in shell calls)
- ZIP Slip (`safe_zip_extract()` validates all members)
- CORS Misconfiguration (no wildcard origin, no credentials)
- CSRF (JSON-only POST endpoints, CORS blocks cross-origin)
- Timing Attacks (`hmac.compare_digest()`)
- HTTP TRACE (disabled, returns 405)

## Security Configuration Checklist

For production deployments:

- [ ] Set `SUBLARR_API_KEY` to a strong random value (32+ chars)
- [ ] Enable UI auth with a strong password (8+ chars)
- [ ] Use a reverse proxy with HTTPS termination
- [ ] Restrict network access to trusted networks
- [ ] Set `SUBLARR_LOG_LEVEL=WARNING` to reduce log verbosity
- [ ] Regularly update to the latest version
- [ ] Review Docker container permissions (PUID/PGID)
