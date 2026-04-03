---
phase: 5
title: "Wiki & Dokumentation"
version_target: "0.39.0-beta"
created: 2026-04-03
status: planned
---

# Phase 5: Wiki & Dokumentation

## Ziel

Strukturierte Nutzerdokumentation für Sublarr v0.38.x aufbauen: drei neue Wiki-Seiten (Post-Processing, Circuit Breaker, Ollama Chat API), Route-Docstrings in `auth_ui.py` und `media.py` vervollständigen, und `home.md` mit v0.38.x Features aktualisieren.

Alle Wiki-Dateien werden direkt in Git committed. Wiki.js synct automatisch via `main` branch (5-Minuten-Delay).

---

## Waves

```
Wave 1 (parallel): Plan A + Plan B + Plan C
  Plan A — Wiki: Post-Processing + Circuit Breaker
  Plan B — Wiki: Ollama Chat API + home.md Update
  Plan C — Backend: Route Docstrings (auth_ui.py + media.py)
```

Alle drei Plans sind voneinander unabhängig. Keine shared files.

---

## Plan A — Wiki: Post-Processing & Circuit Breaker

**Wave:** 1
**Files:**
- `D:/Sublarr_Projekt/SublarrWiki/en/user-guide/post-processing.md` (neu)
- `D:/Sublarr_Projekt/SublarrWiki/en/user-guide/advanced/circuit-breaker.md` (neu)
- `D:/Sublarr_Projekt/SublarrWiki/en/home.md` (Tabelleneintrag ergänzen)

### Task A1: Post-Processing Dokumentationsseite

**Quellcode-Grundlage (bereits gelesen):**
- `backend/post_download.py` — `run_post_download_command()`, Shell-Ausführung via `subprocess.run(shell=False)`, 60s Timeout, Error wird nur geloggt (nie propagiert)
- `backend/config.py` — `post_processing_enabled: bool = False`, `post_download_command: str = ""`

**Erstelle:** `D:/Sublarr_Projekt/SublarrWiki/en/user-guide/post-processing.md`

Inhalt (Wiki.js-kompatibles Markdown, kein MDX/JSX):

```markdown
---
title: Post-Processing
description: Execute a shell command after every subtitle download
published: true
date: 2026-04-03
---

# Post-Processing

Sublarr can run a shell command automatically after every successful subtitle
download. This lets you notify Plex, rename files, or trigger any automation
without requiring a plugin.

> **Disabled by default.** Post-processing must be explicitly enabled in
> Settings → Automation before the command is executed.

## Enable Post-Processing

1. Go to **Settings → Automation**
2. Toggle **Post-Processing** on
3. Enter your command in the **Post-Download Command** field
4. Click **Save**

## Available Variables

Variables are substituted into the command string before execution.

| Variable | Example value | Description |
|---|---|---|
| `{subtitle_path}` | `/media/anime/Naruto.srt` | Absolute path to the saved subtitle file |
| `{path}` | `/media/anime/Naruto.srt` | Alias for `{subtitle_path}` (Bazarr compatibility) |
| `{language}` | `de` | ISO 639-1 language code |
| `{provider}` | `jimaku` | Provider name that supplied the subtitle |
| `{score}` | `93` | Integer match score (0–100) |
| `{media_type}` | `series` | `series`, `movie`, or empty string |
| `{video_path}` | _(empty)_ | Reserved — always empty in current release |

## Examples

**Notify Plex after download:**
```bash
curl -s "http://plex:32400/library/sections/1/refresh?X-Plex-Token=TOKEN" \
  -o /dev/null
```

**Write a log line:**
```bash
/usr/local/bin/log-subtitle.sh {subtitle_path} {language} {provider}
```

**Discord webhook on download:**
```bash
curl -s -X POST https://discord.com/api/webhooks/YOUR_ID/YOUR_TOKEN \
  -H "Content-Type: application/json" \
  -d '{"content":"Subtitle downloaded: {subtitle_path} ({language}) via {provider}"}'
```

> Note: The command is tokenised with `shlex.split` — quote paths that may
> contain spaces, or pass them through a wrapper script.

## Behavior & Limits

- **Timeout:** 60 seconds. Commands exceeding this are killed; Sublarr logs a warning and continues.
- **Non-blocking errors:** A failing command (non-zero exit, crash, or timeout) is logged as a warning. It never blocks or retries the download pipeline.
- **No shell expansion:** The command runs with `shell=False`. Shell features like `&&`, `|`, `$VAR`, or glob patterns are not available. Use a wrapper script for complex logic.
- **Execution context:** The command runs as the same user Sublarr runs as (container: `sublarr` user, default UID 1000). Ensure the command and any target paths are accessible to that user.

## Troubleshooting

**Command does not execute**
- Confirm Post-Processing is toggled **on** in Settings → Automation.
- Check that the `Post-Download Command` field is not empty.

**"invalid shell syntax" in logs**
- Sublarr uses `shlex.split` to tokenise the command. Unmatched quotes or
  unsupported shell syntax causes this error. Test your command with
  `python3 -c "import shlex; print(shlex.split('YOUR COMMAND'))"`.

**Timeout warning in logs**
- Your command exceeds 60 seconds. Move long-running work to a background
  job and have the post-processing command only trigger it.
```

**Verify:** File exists at the target path and renders correctly as Markdown (no syntax errors, table aligns, code blocks close properly).

**Done:** Page covers enable/disable toggle, all 7 variables with correct types from source code, 3 practical examples, behavior/limits section, troubleshooting.

---

### Task A2: Circuit Breaker Dokumentationsseite

**Quellcode-Grundlage (bereits gelesen):**
- `backend/circuit_breaker.py`:
  - States: `CLOSED`, `OPEN`, `HALF_OPEN` (via `CircuitState(StrEnum)`)
  - Default `failure_threshold=5`, `cooldown_seconds=60`
  - `CLOSED → OPEN` when `failure_count >= failure_threshold`
  - `OPEN → HALF_OPEN` when `cooldown_seconds` elapsed (lazy evaluation via `state` property)
  - `HALF_OPEN → CLOSED` on `record_success()`
  - `HALF_OPEN → OPEN` on `record_failure()` (probe failed)
  - `reset()` — manual reset to CLOSED, triggers `persist_fn`
  - `get_status()` — returns dict with `name`, `state`, `failure_count`, `failure_threshold`, `cooldown_seconds`
  - State persists across restarts via `circuit_breaker_state` DB table

**Erstelle:** `D:/Sublarr_Projekt/SublarrWiki/en/user-guide/advanced/circuit-breaker.md`

(Verzeichnis `advanced/` muss ggf. angelegt werden — einfach die Datei in den Pfad schreiben, Git legt das Verzeichnis an.)

Inhalt:

```markdown
---
title: Circuit Breaker
description: How Sublarr protects against failing subtitle providers
published: true
date: 2026-04-03
---

# Circuit Breaker

Sublarr wraps every subtitle provider call in a **circuit breaker**. When a
provider starts failing repeatedly, the circuit breaker opens and prevents
further requests until the provider has had time to recover. This stops
cascade timeouts from blocking your entire download queue.

## State Machine

```
CLOSED ──(5 consecutive failures)──► OPEN
  ▲                                    │
  │                              (60 s cooldown)
  │                                    ▼
  └────(probe succeeds)────── HALF_OPEN
                probe fails ──► OPEN
```

| State | Meaning | Requests allowed |
|---|---|---|
| **CLOSED** | Normal operation, failures are counted | Yes |
| **OPEN** | Provider assumed down, calls are rejected immediately | No |
| **HALF_OPEN** | Cooldown elapsed — one probe request allowed through | One probe |

### Transitions

| From | To | Trigger |
|---|---|---|
| CLOSED | OPEN | 5 consecutive failures |
| OPEN | HALF_OPEN | 60 seconds have elapsed since last failure |
| HALF_OPEN | CLOSED | Probe call succeeded |
| HALF_OPEN | OPEN | Probe call failed |
| Any | CLOSED | Manual reset via API |

## Configuration

Circuit breaker thresholds are global defaults. Future releases will expose
per-provider overrides.

| Parameter | Default | Description |
|---|---|---|
| `failure_threshold` | `5` | Consecutive failures before opening |
| `cooldown_seconds` | `60` | Seconds to wait before allowing a probe |

## Persistence

Circuit breaker state (open/closed, failure count, last failure time) is
persisted in the `circuit_breaker_state` database table. After a restart,
the breaker restores its previous state. If the breaker was OPEN and the
cooldown has already elapsed at restart time, it immediately transitions to
HALF_OPEN so the first real request acts as the probe — no extra wait.

## Monitoring via Prometheus

Each provider's circuit breaker exposes metrics at `GET /api/v1/metrics`:

| Metric | Description |
|---|---|
| `sublarr_circuit_breaker_state` | Current state as a label (`closed`, `open`, `half_open`) |
| `sublarr_circuit_breaker_failure_count` | Current consecutive failure count |

Use these metrics in Grafana or Prometheus alerts to detect providers that
are repeatedly tripping their circuit breakers.

## Manually Resetting a Provider

If a provider's circuit breaker is OPEN and you want to force an immediate
retry without waiting for the cooldown:

1. Go to **Settings → Providers**
2. Find the provider with the "Circuit Open" badge
3. Click **Reset** (or **Re-enable** depending on UI version)

This calls the internal `reset()` method, which immediately transitions the
breaker to CLOSED and persists the new state.

Alternatively, via API:

```bash
curl -X POST http://localhost:5765/api/v1/providers/PROVIDER_NAME/reset \
  -H "X-Api-Key: YOUR_API_KEY"
```

## Why Providers Get Disabled

Providers are auto-disabled (circuit opened) when:
- They return repeated HTTP errors (4xx/5xx)
- They time out repeatedly
- Their response cannot be parsed

A single failure does not open the circuit. Five consecutive failures are
required (default threshold). A single success resets the failure counter.
```

**Verify:** File exists. State machine ASCII diagram renders (no broken characters). Transitions table is accurate against `circuit_breaker.py` source code (verify HALF_OPEN → CLOSED on success, HALF_OPEN → OPEN on failure).

**Done:** Page accurately documents the 4-state-transition model from source, default thresholds (5/60), persistence behavior, and manual reset path.

---

### Task A3: home.md — User Guide Tabelleneinträge ergänzen

**Aktuelle home.md:** Zeile 44 hat bereits "Translation & LLM" in der User Guide-Tabelle. Post-Processing und Circuit Breaker fehlen noch.

Ergänze in der User Guide-Tabelle (`## User Guide`) nach dem bestehenden `[Notifications]`-Eintrag:

```markdown
| [Post-Processing](/user-guide/post-processing) | Shell command after subtitle download |
```

Und nach `[Integrations]` (oder am Ende der Tabelle):

```markdown
| [Circuit Breaker](/user-guide/advanced/circuit-breaker) | Provider resilience and failure isolation |
```

Außerdem Version badge auf Zeile 13 auf `v0.38.1-beta` belassen (bereits korrekt laut aktuellem Stand), oder auf `v0.39.0-beta` aktualisieren sobald Phase 5 fertig ist — entscheide bei Commit.

**Verify:** `grep "post-processing\|circuit-breaker" SublarrWiki/en/home.md` gibt beide Einträge zurück.

**Done:** Beide neuen Seiten sind in der Navigations-Tabelle verlinkt.

---

## Plan B — Wiki: Ollama Chat API & home.md Update

**Wave:** 1
**Files:**
- `D:/Sublarr_Projekt/SublarrWiki/en/user-guide/settings/translation.md` (Abschnitt ergänzen)
- `D:/Sublarr_Projekt/SublarrWiki/en/user-guide/translation-llm.md` (Querverweis ergänzen)

### Task B1: translation.md — Chat API Abschnitt

**Quellcode-Grundlage (bereits gelesen):**
- `backend/translation/ollama.py`:
  - `use_chat_api` config field — Checkbox, default `"false"`, label `"Chat API (V9+)"`, help `"Use /api/chat instead of /api/generate for V9+ models"`
  - `system_prompt` config field — Textarea, help `"System prompt for chat API mode. Use {series_context} as placeholder."`
  - `_build_system_prompt()` — wenn `{series_context}` im Template enthalten ist, wird es substituiert; wenn nicht, wird `series_context` an das Ende angehängt; wenn `series_context=None`, wird `{series_context}` entfernt
  - Bei `use_chat_api=False` → POST `/api/generate` mit `{"model": ..., "prompt": ..., "stream": false}`
  - Bei `use_chat_api=True` → POST `/api/chat` mit `{"model": ..., "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}], "stream": false}`

Ergänze in `SublarrWiki/en/user-guide/settings/translation.md` nach dem bestehenden "Fallback Chains" Abschnitt einen neuen Abschnitt:

```markdown
## Ollama — Chat API (V9+)

Sublarr v0.38.0 added support for the Ollama `/api/chat` endpoint alongside
the existing `/api/generate` endpoint.

### Enabling Chat API

In **Settings → Translation Backends → Ollama**, enable the **Chat API (V9+)** checkbox.

| Setting | Default | Description |
|---|---|---|
| Chat API (V9+) | Off | Use `/api/chat` instead of `/api/generate` |
| System Prompt | _(see below)_ | System message injected as the first chat turn |

### Chat vs. Generate — What Changes

| | `/api/generate` (default) | `/api/chat` (V9+) |
|---|---|---|
| Request format | `{"prompt": "..."}` | `{"messages": [{"role": "system", ...}, {"role": "user", ...}]}` |
| System prompt | Embedded in user prompt | Separate `system` message |
| Series context | Not supported | Injected via `{series_context}` placeholder |
| Supported models | All Ollama models | Models with instruction-following (Qwen2.5, Llama 3+) |

### System Prompt & Series Context

The system prompt is the first message sent to the model in chat mode. The
default system prompt instructs the model to translate anime subtitles into
German using informal language (`du`-form).

You can include `{series_context}` in your system prompt as a placeholder.
Sublarr replaces it with the series name and genre at translation time. This
improves consistency for character names and terminology across an episode.

**Example system prompt with series context:**
```
Du bist ein Anime-Untertitel-Übersetzer EN→DE. {series_context}
Übersetze präzise und natürlich. Keine Erklärungen — nur die Übersetzung.
```

When series context is available (e.g. "Serie: Naruto. Genre: Action."), the
placeholder is substituted. When no context is available, the placeholder is
removed cleanly.

### Which Models Benefit from Chat API?

| Model | Recommendation |
|---|---|
| `qwen2.5:14b-instruct` | Chat API recommended — better instruction following |
| `llama3.2:3b` | Chat API recommended |
| Custom `anime-translator-v8-GGUF` | Generate API — fine-tuned on generate-format prompts |
| Custom `anime-translator-v9-GGUF` | Chat API — trained with chat-format prompts |
| DeepSeek-R1 | Chat API recommended |

> **Rule of thumb:** If your model name ends in `-instruct`, use Chat API.
> If you are using the Sublarr custom model, check the model version:
> V8 and earlier → Generate, V9+ → Chat.
```

**Verify:** File contains the new `## Ollama — Chat API (V9+)` heading. Table alignment is correct. `{series_context}` placeholder is visible in the example (not accidentally substituted by Markdown rendering).

**Done:** `use_chat_api` und `series_context` sind vollständig dokumentiert mit korrekten API-Endpunkten aus dem Quellcode, Tabelle differenziert Chat vs. Generate, Modell-Empfehlungen enthalten.

---

### Task B2: translation-llm.md — Querverweis auf neuen Chat API Abschnitt

`SublarrWiki/en/user-guide/translation-llm.md` enthält bereits eine "Configuring Ollama" Sektion. Ergänze nach dem "Fallback Chains" Block einen Querverweis:

```markdown
## Chat API & Series Context (V9+)

See [Settings — Translation: Chat API](/user-guide/settings/translation#ollama-chat-api-v9)
for the full reference including how to configure system prompts and series
context injection.
```

**Verify:** `grep "Chat API" SublarrWiki/en/user-guide/translation-llm.md` gibt einen Treffer zurück.

**Done:** Beide Wiki-Seiten verlinken auf die Chat API Dokumentation, kein Dead Link.

---

## Plan C — Backend: Route Docstrings

**Wave:** 1
**Files:**
- `D:/Sublarr_Projekt/Sublarr/backend/routes/auth_ui.py`
- `D:/Sublarr_Projekt/Sublarr/backend/routes/media.py`

### Task C1: auth_ui.py — OpenAPI Docstrings

**Referenzformat:** `backend/routes/providers.py` — YAML-basierte OpenAPI Docstrings mit `---` Trennlinie, `get:`/`post:` top-level, `tags`, `summary`, `description`, `security`, `requestBody`, `responses`.

**Zu dokumentieren** (6 Endpoints, Verhalten aus Quellcode bekannt):

**`get_status()`** — `GET /api/v1/auth/status`
- Kein Auth erforderlich
- Returns: `{configured: bool, enabled: bool, authenticated: bool}`
- Kein requestBody

**`setup()`** — `POST /api/v1/auth/setup`
- Nur wenn `!is_ui_auth_configured()`
- Body: `{action: "set_password"|"disable", password?: string}`
- Returns 409 wenn bereits konfiguriert
- Returns 400 wenn Passwort < 12 Zeichen
- Returns `{status: "enabled"|"disabled"}`

**`login()`** — `POST /api/v1/auth/login`
- Rate limited: `10/minute; 30/hour`
- Body: `{password: string}`
- Returns 401 bei falschem Passwort
- Returns `{status: "ok"}`

**`logout()`** — `POST /api/v1/auth/logout`
- Kein Auth erforderlich (löscht Session)
- Returns `{status: "ok"}`

**`change_password()`** — `POST /api/v1/auth/change-password`
- Erfordert aktive Session
- Body: `{current_password: string, new_password: string}`
- Returns 401 wenn nicht authenticated oder current_password falsch
- Returns 400 wenn new_password < 12 Zeichen
- Returns `{status: "ok"}`

**`toggle()`** — `POST /api/v1/auth/toggle`
- Erfordert Session oder API Key
- Body: `{enabled: bool}`
- Returns 401 wenn nicht authenticated
- Returns 400 wenn `enabled` kein boolean
- Returns `{status: "enabled"|"disabled"}`

Füge für jede Funktion einen Docstring im folgenden Format ein (analog zu `providers.py`):

```python
"""Brief description.
---
post:
  tags:
    - Auth
  summary: Short action name
  description: Full description.
  security:
    - sessionAuth: []
  requestBody:
    required: true
    content:
      application/json:
        schema:
          type: object
          required: [field]
          properties:
            field:
              type: string
  responses:
    200:
      description: Success
      content:
        application/json:
          schema:
            type: object
            properties:
              status:
                type: string
    400:
      description: Validation error
    401:
      description: Authentication failed
"""
```

**Verify:** `python -c "import ast; ast.parse(open('backend/routes/auth_ui.py').read()); print('OK')"` aus `D:/Sublarr_Projekt/Sublarr/` heraus. Kein SyntaxError.

**Done:** Alle 6 Endpoints in `auth_ui.py` haben vollständige OpenAPI Docstrings. Responses umfassen Fehler-Codes (400, 401, 409) aus dem Quellcode.

---

### Task C2: media.py — OpenAPI Docstrings

**Zu dokumentieren** (2 Endpoints):

**`stream_media()`** — `GET /api/v1/media/stream?path=<abs_path>`
- Erfordert API Key (`@require_api_key`)
- Returns 503 wenn `settings.streaming_enabled` false
- Returns 400 wenn `path` leer
- Returns 403 wenn `is_safe_path()` fehlschlägt (path traversal)
- Returns 404 wenn Datei nicht gefunden
- HTTP 206 Partial Content bei Range-Header (Range: bytes=start-end)
- HTTP 200 bei fehlendem Range-Header
- Supported formats: `.mp4`, `.mkv`, `.avi`, `.mov`, `.webm`, `.m4v`
- Returns 416 bei ungültigem Range-Header

**`generate_thumbnail()`** — fehlt in media.py (nach erneutem Lesen der Datei: Funktion existiert nicht in `media.py`). Überspringe diese Funktion — dokumentiere nur `stream_media()`.

Docstring für `stream_media()`:

```python
"""Stream a video file with HTTP 206 Range support.
---
get:
  tags:
    - Media
  summary: Stream video file
  description: >
    Serves a local video file with RFC 7233 Range request support (HTTP 206).
    Requires the streaming_enabled setting to be active.
    Path must be within the configured media_path (path traversal protection).
  security:
    - apiKeyAuth: []
  parameters:
    - name: path
      in: query
      required: true
      schema:
        type: string
      description: Absolute path to the video file
  responses:
    200:
      description: Full file (no Range header)
    206:
      description: Partial content (Range header present)
      headers:
        Content-Range:
          schema:
            type: string
          example: "bytes 0-1048575/52428800"
        Accept-Ranges:
          schema:
            type: string
          example: "bytes"
    400:
      description: Missing path parameter
    403:
      description: Path outside media_path (access denied)
    404:
      description: File not found
    416:
      description: Invalid Range header
    503:
      description: Streaming is disabled in settings
"""
```

**Verify:** `python -c "import ast; ast.parse(open('backend/routes/media.py').read()); print('OK')"` aus `D:/Sublarr_Projekt/Sublarr/` heraus.

**Done:** `stream_media()` hat vollständigen OpenAPI Docstring mit allen HTTP-Status-Codes aus dem Quellcode (200, 206, 400, 403, 404, 416, 503).

---

## Commits

Nach Plan A:
```bash
cd D:/Sublarr_Projekt/SublarrWiki
git add en/user-guide/post-processing.md en/user-guide/advanced/circuit-breaker.md en/home.md
git commit -m "docs: add post-processing and circuit-breaker wiki pages"
git push origin main
```

Nach Plan B:
```bash
cd D:/Sublarr_Projekt/SublarrWiki
git add en/user-guide/settings/translation.md en/user-guide/translation-llm.md
git commit -m "docs: document Ollama Chat API (V9+) and series_context"
git push origin main
```

Nach Plan C:
```bash
cd D:/Sublarr_Projekt/Sublarr
git add backend/routes/auth_ui.py backend/routes/media.py
git commit -m "docs: add OpenAPI docstrings to auth_ui and media routes"
```

---

## Gesamtergebnis

| Plan | Output | Status nach Ausführung |
|---|---|---|
| A | 2 neue Wiki-Seiten + home.md update | Beide Seiten in Wiki.js sichtbar nach ≤5 min |
| B | translation.md + translation-llm.md ergänzt | Chat API vollständig dokumentiert |
| C | auth_ui.py + media.py mit Docstrings | OpenAPI-konform, kein SyntaxError |

## Nicht in dieser Phase

- `generate_thumbnail()` existiert nicht in `media.py` — nicht dokumentieren.
- CHANGELOG v0.38.0 `post_processing_enabled` ist korrekt im CHANGELOG (Zeile 201 config.py bestätigt `post_processing_enabled: bool`). Kein Korrekturaufwand identifiziert — bei Ausführung nochmals prüfen ob der CHANGELOG-Eintrag lückenhaft ist und ggf. ergänzen.
- Neue Wiki-Seiten werden in `home.md` verlinkt (Task A3) — keine separaten Navigationsdateien nötig (Wiki.js nutzt Git-Struktur).
