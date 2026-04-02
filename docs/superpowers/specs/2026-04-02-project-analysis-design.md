# Sublarr — Projektanalyse & Verbesserungsplan

**Datum:** 2026-04-02  
**Version beim Analysezeitpunkt:** v0.37.3-beta  
**Analysemethode:** 4 parallele Sub-Agenten (Code-Qualität, Sicherheit, Features/Roadmap, Test-Coverage)

---

## Überblick

Sublarr ist funktional stark und liefert kontinuierlich Features. Die Analyse identifiziert drei strukturelle Schwächen:

1. **Test-Coverage: 10% statt 80%-Ziel** — 26 Route-Dateien mit 5.589 LOC komplett ungetestet
2. **Überdimensionierte Dateien** — 8 Backend-Dateien >1000 Zeilen, 5 Frontend-Dateien >1200 Zeilen
3. **5 offene Provider-Security-Lücken (P1–P5)** — behebbar in <15h Gesamtaufwand

Alle Bereiche sind beherrschbar. Dieser Spec organisiert die Arbeit in 6 unabhängige Phasen.

---

## Phase 1 — Security Quickfixes (P1–P5)

**Ziel:** Die 5 offenen Provider-Security-Lücken schließen, bevor v1.0 angestrebt wird.  
**Aufwand:** ~12–18h  
**Risiko bei Nichtbehebung:** SSRF via kompromittiertem Provider, Datei-Schreiben außerhalb des Media-Pfads, LLM-Manipulation

### P1 — Domain-Allowlist für Provider-Downloads
- **Problem:** Alle 30+ Provider rufen `self.session.get(download_url)` auf, ohne den Domainnamen zu prüfen. Ein kompromittierter Provider kann Sublarr auf beliebige URLs umleiten.
- **Lösung:** `validate_download_url(url, provider_name)` in `security_utils.py`; pro Provider eine erlaubte Domain-Whitelist. Alle Provider-Download-Calls validieren.
- **Dateien:** `backend/security_utils.py`, `backend/providers/__init__.py`, jede `*.py` in `backend/providers/` die `.session.get(result.download_url)` aufruft
- **Aufwand:** 3–4h

### P2 — Filename-Sanitization aus Provider-Responses
- **Problem:** `actual_filename = data.get("file_name", "")` in `providers/__init__.py` wird ohne Sanitization für Extension-Extraktion genutzt.
- **Lösung:** `werkzeug.secure_filename()` auf alle Provider-Dateinamen anwenden bevor sie weiterverarbeitet werden.
- **Dateien:** `backend/providers/__init__.py` (~Zeile 484)
- **Aufwand:** 1–2h

### P3 — Prompt-Injection-Guard für Ollama
- **Problem:** Subtitle-Text und Glossar-Einträge fließen direkt via f-String in Ollama-Prompts. Eingebettete LLM-Kommandos können die Übersetzungsanweisung überschreiben.
- **Lösung:** Newlines und Sonderzeichen in Subtitle-Lines escapen; Glossar-Einträge auf Länge und Zeichensatz validieren (max. 100 Zeichen, kein `\n`).
- **Dateien:** `backend/translation/llm_utils.py` (Zeilen 143–153)
- **Aufwand:** 2–3h

### P4 — Magic-Byte-Validierung nach Download
- **Problem:** Heruntergeladener Inhalt wird als valides Subtitle akzeptiert ohne zu prüfen ob er dem deklarierten Format entspricht.
- **Lösung:** Format-Validierer pro Subtitle-Typ (SRT, ASS, VTT); Reject wenn Content nicht zum Format passt; Prüfung auf bekannte böse Signaturen (PE-Header etc.).
- **Dateien:** `backend/providers/__init__.py` (nach Download, vor Speichern)
- **Aufwand:** 1–2h

### P5 — Streaming-Size-Cap
- **Problem:** `dl_resp.content` lädt die gesamte Antwort in Memory — kein Limit. OOM bei großen Dateien möglich.
- **Lösung:** Streaming-Download mit `iter_content()`, Abbruch bei >50 MB; `Content-Length`-Pre-flight-Check.
- **Dateien:** Alle Provider-Dateien mit `.session.get(url)` gefolgt von `.content`
- **Aufwand:** 1–2h

### F-05 — Webhook-Exemption absichern (Low-Effort)
- **Problem:** Webhook-Pfade sind pauschal vom Auth-Middleware ausgenommen. Neue Handler ohne HMAC-Check wären offen.
- **Lösung:** Log-Warning in `auth.py` wenn Webhook-Request ohne `X-Signature`-Header eingeht. Optional: Hard-Enforce.
- **Dateien:** `backend/auth.py`
- **Aufwand:** 0.5h

---

## Phase 2 — Deprecated Code & Quick Wins

**Ziel:** Technische Schulden mit geringem Aufwand abbauen  
**Aufwand:** ~3–4h

### datetime.utcnow() ersetzen
- **9 Vorkommen:** `whisper/queue.py` (6×), `routes/system/logs.py` (3×), `nfo_export.py` (1×)
- **Fix:** `from datetime import UTC` + `datetime.now(UTC)` statt `datetime.utcnow()`
- **Aufwand:** 30 Minuten

### whisper_subgen Provider entfernen
- **Datei:** `backend/providers/whisper_subgen.py`
- **Status:** Alle 6 öffentlichen Methoden emittieren `DeprecationWarning`. Bereits durch das Whisper-Backend-System ersetzt.
- **Aufwand:** 30 Minuten (Datei löschen + Registry-Eintrag entfernen)

### ROADMAP.md aktualisieren
- **Problem:** ROADMAP.md behauptet noch "v0.28.0-beta" als aktuelle Version. Wir sind bei v0.37.3-beta.
- **Lösung:** Vergangene Versionen v0.29–v0.37 dokumentieren, Planung ab v0.38 fortschreiben.
- **Aufwand:** 1–2h

---

## Phase 3 — Test-Coverage: Kritische Bereiche

**Ziel:** Backend-Coverage von 10% auf ~35–40% bringen; destruktive und sicherheitskritische Operationen abdecken  
**Aufwand:** ~20–30h

### Priorität 1 — Destruktive Operationen (Datenverlustrisiko)
- **`routes/cleanup.py`** (1.016 LOC): Scan, Duplikat-Erkennung, Orphan-Löschung — **komplett ungetestet**
  - Schätzung: 40–60 neue Tests
- **`bazarr_migrator.py`** (430 LOC): Datenmigration ohne Tests = stille Datenmigrationsfehler
  - Schätzung: 20–30 neue Tests

### Priorität 2 — Sicherheitskritische Routen
- **`routes/api_keys.py`** (803 LOC): Token-CRUD, Permissions — komplett ungetestet
  - Schätzung: 50–80 neue Tests
- **`routes/auth_ui.py`**: Nur partiell getestet; Login-Flow, Session-Handling

### Priorität 3 — Core-Features
- **`routes/profiles.py`** (883 LOC): Betrifft alle Sprachzuordnungen — komplett ungetestet
  - Schätzung: 35–50 neue Tests
- **`routes/notifications_mgmt.py`** (732 LOC): Komplett ungetestet
  - Schätzung: 40–50 neue Tests
- **`whisper/queue.py`** + **`routes/whisper.py`** (773 LOC zusammen): Komplett ungetestet
  - Schätzung: 45–60 neue Tests

### CI-Stabilisierung: Ausgeschlossene Test-Suites
Die 6 von CI ausgeschlossenen Suiten (~500 Tests) sollten stabilisiert werden:
- `test_provider_pipeline.py` — Circuit-Breaker-Tests, flaky durch externes Mocking
- `test_translator_pipeline.py` — Multi-Backend-Orchestration
- `test_translation_backends.py` — Backend-Stats-Recording
- `test_video_sync.py` — ffsubsync/alass-Integration
- `test_wanted_search_reliability.py` — Provider-Fehlerbehandlung

**Vorgehen:** Jeden ausgeschlossenen Test einzeln analysieren; entweder Infrastruktur stabilisieren oder Test-Isolation verbessern.

### Frontend — Fehlende Page-Tests
19 Pages ohne Tests; Priorität für sicherheitskritische und Core-Pages:
- `Login.tsx` — Authentifizierungs-UI
- `Onboarding.tsx` — First-Run-Flow
- `Library.tsx`, `Wanted.tsx`, `Dashboard.tsx` — Core-UX

---

## Phase 4 — Feature-Vollständigkeit (Bazarr-Parität)

**Ziel:** Die wichtigsten fehlenden Bazarr-Features implementieren  
**Aufwand:** ~15–20h

### Phase 4A — Language Profile Filter (Hohe Priorität)
Kritisch für Power-User; Bazarr-Standard-Feature:
- `must_contain` — Subtitle muss bestimmten Release-String enthalten
- `must_not_contain` — Ausschluss-Filter
- `cutoff_language` — Sprach-Cutoff nach dem nicht mehr gesucht wird
- `audio_exclude` — Sprachen mit passendem Audio-Track ausnehmen
- **Dateien:** `backend/db/models/`, neues Alembic-Migration, `backend/routes/profiles.py`, Frontend `LanguageProfiles.tsx`
- **Aufwand:** ~6h

### Phase 4B — Video-Codec-Scoring (Mittlere Priorität)
- `video_codec: 2` Gewicht in den Scoring-Tabellen für `x264`/`x265`/`AV1`-Matching
- **Dateien:** `backend/db/models/quality.py`, Scoring-Logic
- **Aufwand:** ~1h

### Phase 4C — Circuit-Breaker-Persistenz (Mittlere Priorität)
- CB-State aktuell im Memory — geht bei Restart verloren
- In DB persistieren damit Provider nicht nach jedem Neustart neu "warmgelaufen" werden
- **Aufwand:** ~3h

### Phase 4D — Download-Upgrade-Tracking (Niedrige Priorität)
- `upgraded_from_id`-Spalte um Download-Qualitäts-Upgrades zu tracken
- Post-Download-Shell-Hook für externe Post-Processing-Skripte
- **Aufwand:** ~4h

### Standalone Auto-Mode
- Auto-Aktivierung wenn keine Sonarr/Radarr-Instanzen konfiguriert
- `is_standalone_mode()`-Helper in `config.py`
- "Scan Library"-Button in ConnectionsSettings
- **Aufwand:** ~3h

### V9 LLM-Integration
- Ollama Chat-API (`/api/chat` statt `/api/generate`) für Gemma-3-Chat-Template
- `use_chat_api`-Config-Flag, `_call_ollama_chat()`-Methode
- `series_context`-Parameter für bessere Kontextualisierung
- Backwards-kompatibel (`use_chat_api=False` default)
- **Dateien:** `backend/translation/ollama.py`, `backend/translation/base.py`
- **Aufwand:** ~5h

---

## Phase 5 — Architektur-Refactoring (Dateigröße)

**Ziel:** Die größten Dateiverletzungen beheben  
**Aufwand:** ~20–30h

### Backend

| Datei | Aktion |
|-------|--------|
| `providers/__init__.py` (1.642 LOC) | Download-Orchestration → `services/provider_download.py`; Format-Validierung → `providers/format_validator.py` |
| `routes/cleanup.py` (1.016 LOC) | Business-Logik → `services/cleanup_scanner.py`; Route-Handler-Shell bleibt |
| `routes/standalone.py` (967 LOC) | Business-Logik → `services/standalone_manager.py` |
| `services/wanted_scanner.py` (1.190 LOC) | In 2–3 fokussierte Module aufteilen |
| `config.py` (1.101 LOC) | Validierungslogik → `config_validators.py` extrahieren |
| `db/repositories/__init__.py` (718 LOC) | Per-Domain aufteilen |

### Frontend

| Datei | Aktion |
|-------|--------|
| `api/client.ts` (2.151 LOC) | Mock-Daten → separates `api/mocks.ts`; Endpoints domain-weise aufteilen |
| `lib/types.ts` (1.301 LOC) | Domain-weise aufteilen: `types/library.ts`, `types/translation.ts`, etc. |
| `pages/Settings/AdvancedTab.tsx` (1.306 LOC) | Sub-Komponenten extrahieren |
| `pages/Wanted.tsx` (1.260 LOC) | Toolbar, RowActions, FilterPanel als eigene Komponenten |
| `pages/Settings/LegacySettings.tsx` (1.248 LOC) | Tab-basiertes Routing (`/settings/providers`, etc.) |

### Error-Handler-Deduplizierung
- 50+ identische `except Exception as e: logger.error(...)` Patterns
- `@handle_api_error`-Decorator in `backend/error_utils.py`
- Schrittweise einführen

---

## Phase 6 — Timestamp-Migration (Breaking Change)

**Ziel:** Alle Timestamp-Spalten von `TEXT` → `DateTime(timezone=True)` migrieren  
**Aufwand:** ~5–6h  
**Risiko:** Breaking Change — Alembic-Migration reformatiert alle gespeicherten Zeitstempel

### Was sich ändert
- Gespeicherte Werte: `"2024-01-15T10:30:00+00:00"` (String) → Python `datetime`-Objekte
- Alle `Mapped[str]` Timestamp-Spalten werden `Mapped[datetime]`
- Code der `.isoformat()` auf Timestamps aufruft muss angepasst werden

### Vorgehen
1. Alle betroffenen Modelle identifizieren
2. Alembic-Migration mit `USING`-Cast-Klausel (PostgreSQL) + SQLite-kompatiblem Pfad
3. `scripts/check_datetime_migration.py` für Vor/Nach-Verifikation nutzen
4. Ankündigung an Nutzer vor Release (Docker-Deployments migrieren automatisch)

---

## Reihenfolge & Abhängigkeiten

```
Phase 1 (Security)      ← keine Abhängigkeiten, sofort starten
Phase 2 (Quick Wins)    ← keine Abhängigkeiten, sofort starten
Phase 3 (Tests)         ← parallel zu Phase 1+2 möglich; Phase 5 erleichtert Phase 3
Phase 4 (Features)      ← unabhängig, nach Phase 1 priorisieren
Phase 5 (Refactoring)   ← nach Phase 3 (Tests schützen Refactoring)
Phase 6 (Timestamps)    ← letzte Phase; koordinierte Ankündigung nötig
```

---

## Erfolgskriterien pro Phase

| Phase | Definition of Done |
|-------|-------------------|
| 1 — Security | P1–P5 implementiert + Tests; Security-Reviewer bestätigt; kein `shell=True` neu eingeführt |
| 2 — Quick Wins | Keine `datetime.utcnow()` mehr; `whisper_subgen.py` gelöscht; ROADMAP.md aktuell |
| 3 — Tests | Backend-Coverage ≥40%; `cleanup.py` + `api_keys.py` + `profiles.py` vollständig getestet; mind. 3 CI-ausgeschlossene Suites stabilisiert |
| 4 — Features | Language-Profile-Filter funktional + getestet; Standalone Auto-Mode aktiv; V9-Integration optional aktivierbar |
| 5 — Refactoring | Keine Backend-Datei >800 LOC; keine Frontend-Datei >1000 LOC (Ausnahmen dokumentiert); `@handle_api_error` eingeführt |
| 6 — Timestamps | Migration auf allen unterstützten DB-Backends getestet; `check_datetime_migration.py` bestätigt 0 Fehler; Breaking-Change-Ankündigung im CHANGELOG |

---

## Offene Fragen

1. **Phase-Reihenfolge:** Security (Phase 1) + Quick Wins (Phase 2) klar als erstes — aber Phase 3 (Tests) vs. Phase 4 (Features) danach: Präferenz?
2. **Timestamp-Migration (Phase 6):** Für v0.38 oder auf v0.40 verschieben für mehr Testzeit?
3. **`LegacySettings.tsx`-Refactoring:** Tab-basiertes Routing würde URLs ändern (`/settings` → `/settings/providers`) — akzeptabel?
4. **CI-Suites:** Sollen ausgeschlossene Test-Suites in Phase 3 stabilisiert oder dauerhaft als "opt-in only" belassen werden?
