# Sublarr Roadmap — Bazarr-Ersatz mit LLM-Uebersetzung

> Ziel: Sublarr wird zum eigenstaendigen Subtitle-Manager der Bazarr vollstaendig ersetzt.

## Status-Uebersicht

| Milestone | Status | Branch | Beschreibung |
|---|---|---|---|
| 1 | ✅ Erledigt | `feature/provider-system` | Provider-System (OpenSubtitles, Jimaku, AnimeTosho) |
| 2 | ✅ Erledigt | `feature/provider-system` | Eigenstaendiges Wanted-System |
| 3 | ✅ Erledigt | `feature/provider-system` | Such- und Download-Workflow |
| 4 | ✅ Erledigt | `feature/provider-system` | Provider-UI + Management |
| 5 | ✅ Erledigt | `feature/provider-system` | Upgrade-System + Automatisierung |
| 6 | ⬜ Geplant | — | Erweiterte Provider + Polish |

---

## Milestone 1: Provider-Fundament ✅

**Ziel:** Eigenes Provider-System, kein Bazarr mehr noetig fuer Subtitle-Download.

**Erledigt:**
- [x] Provider Base Class + Subtitle Model (`providers/base.py`)
- [x] ProviderManager mit Priority/Fallback-Logik (`providers/__init__.py`)
- [x] RetryingSession mit Rate-Limit-Handling (`providers/http_session.py`)
- [x] OpenSubtitles.com Provider — REST API v2 (`providers/opensubtitles.py`)
- [x] Jimaku Provider — Anime-spezifisch, AniList, ZIP/RAR (`providers/jimaku.py`)
- [x] AnimeTosho Provider — Fansub ASS, XZ, Feed API (`providers/animetosho.py`)
- [x] Provider-Config in Settings (API Keys, Priorities, Enable/Disable)
- [x] Provider-Cache + Download-History DB-Tabellen
- [x] translator.py: Cases B1/C3 nutzen Provider statt Bazarr
- [x] server.py: /providers, /providers/test, /providers/search Endpoints
- [x] Dockerfile: unrar-free, rarfile Dependency

**Neue Dateien:** 6 | **Geaenderte Dateien:** 6 | **+1977 Zeilen**

---

## Milestone 2: Wanted-System (eigenstaendig) ✅

**Ziel:** Sublarr erkennt selbst fehlende Untertitel, braucht keine Bazarr-Wanted-Liste.

**Erledigt:**
- [x] DB-Tabelle `wanted_items` (type, sonarr/radarr IDs, file_path, status, search_count)
- [x] Library-Scanner: Sonarr/Radarr Episoden durchgehen, fehlende Target-Subs erkennen
- [x] Filesystem-Scanner: Vorhandene `.{lang}.ass/.srt` Dateien indexieren
- [x] `/api/v1/wanted/refresh` Endpoint — Rescan fuer fehlende Subs
- [x] `/api/v1/wanted` mit Pagination + Filter (item_type, status, series_id)
- [x] `/api/v1/wanted/summary` — Aggregierte Wanted-Statistiken
- [x] Wanted-Page im Frontend auf eigene API umstellt (kein Bazarr-Call mehr)
- [x] Auto-Rescan Scheduler (konfigurierbar, Default: alle 6 Stunden)
- [x] Per-Item Status-Updates (wanted, searching, found, failed, ignored)

**Neue Dateien:** 1 (`wanted_scanner.py`) | **Geaenderte Dateien:** 5 | **+700 Zeilen**

---

## Milestone 3: Such- und Download-Workflow ✅

**Ziel:** Komplette Pipeline: Fehlend erkennen → Provider durchsuchen → Downloaden → Uebersetzen

**Erledigt:**
- [x] Sonarr/Radarr Metadata-Enrichment (`get_episode_metadata`, `get_movie_metadata`)
- [x] Such-Modul `wanted_search.py` (Query-Builder, Search, Process, Batch)
- [x] `/api/v1/wanted/<id>/search` — Manuelle Provider-Suche pro Item
- [x] `/api/v1/wanted/<id>/process` — Download + Translate (async)
- [x] `/api/v1/wanted/batch-search` — Batch-Verarbeitung aller Wanted-Items
- [x] `/api/v1/wanted/batch-search/status` — Batch-Progress abfragen
- [x] Download-Logik: Target-ASS direkt suchen, Fallback via translate_file()
- [x] Rate-Limit-Protection: Sequenziell, 0.5s zwischen Items
- [x] Frontend: "Search All" Button + Batch-Progress-Banner
- [x] Frontend: Per-Row Search (Lupe) + Process (Play) Buttons
- [x] Frontend: Expandable Search Results mit Score-Badges + Provider-Info
- [x] WebSocket-Events: wanted_item_processed, wanted_batch_progress, wanted_batch_completed

**Neue Dateien:** 1 (`wanted_search.py`) | **Geaenderte Dateien:** 8 | **+560 Zeilen**

**Ergebnis:** End-to-End Flow ohne Bazarr.

---

## Milestone 4: Provider-UI + Management ✅

**Ziel:** Provider im Frontend konfigurieren, testen, priorisieren.

**Erledigt:**
- [x] Settings-Page: Provider-Tab mit Enable/Disable Toggles
- [x] Credential-Formulare pro Provider (API-Keys, Login)
- [x] Provider-Test-Button (nutzt `/api/v1/providers/test/{name}`)
- [x] Priority-Arrows fuer Provider-Reihenfolge
- [x] Provider-Status-Anzeige (Health, Enabled, letzte Suche)
- [x] Provider-Cache-Statistiken + Clear Cache Button (pro Provider und global)

**Geaenderte Dateien:** 3 (Settings.tsx, server.py, config.py)

---

## Milestone 5: Upgrade-System + Automatisierung ✅

**Ziel:** SRT→ASS Upgrade, automatische Verarbeitung neuer Downloads.

**Erledigt:**
- [x] Upgrade-Logik: Score-Vergleich mit konfigurierbarem Min-Delta (`upgrade_min_score_delta`)
- [x] Zeitfenster-Schutz: Kuerzlich gedownloadete Subs brauchen 2x Score-Delta (`upgrade_window_days`)
- [x] SRT→ASS Upgrade-Path: ASS wird automatisch bevorzugt (`upgrade_prefer_ass`)
- [x] Webhook-Enhancement: Sonarr/Radarr Download → Auto-Scan → Auto-Search → Auto-Translate
- [x] Webhook Delay konfigurierbar (`webhook_delay_minutes`, Default: 5 Min)
- [x] Scheduler: Periodisch Wanted-Items durchsuchen (`wanted_search_interval_hours`)
- [x] Re-Translation Trigger bei Model/Prompt-Aenderung (Config-Hash-Tracking)
- [x] Notification-System: WebSocket Events fuer alle Aktionen (webhook, upgrade, search, retranslation)
- [x] GlobalWebSocketListener + Toast-Benachrichtigungen im Frontend
- [x] Upgrade-History DB-Tabelle + Translation-Config-History

**Neue Dateien:** 1 (`upgrade_scorer.py`) | **Geaenderte Dateien:** 6 | **+800 Zeilen**

---

## Milestone 6: Erweiterte Provider + Polish

**Ziel:** Mehr Provider, Language-Profiles, Bazarr komplett entfernen.

**Tasks:**
- [ ] SubDL Provider hinzufuegen (Subscene-Nachfolger, REST API)
- [ ] Language-Profile System:
  - DB-Tabelle `language_profiles` (Name, Source-Languages, Target-Languages)
  - DB-Tabelle `series_profiles` / `movie_profiles` (Zuweisung pro Serie/Film)
  - Multi-Target-Language Support in Translation-Pipeline
  - Profile-Editor in Settings UI
- [ ] `bazarr_client.py` endgueltig entfernen
- [ ] `SUBLARR_BAZARR_*` Config-Variablen deprecaten/entfernen
- [ ] `.env.example` aktualisieren
- [ ] Docker-Image optimieren (Dependencies pruefen)
- [ ] README.md mit Setup-Anleitung

---

## Geschaetzter Aufwand

| Milestone | Aufwand | Bazarr-Code gespart |
|---|---|---|
| 1 Provider-Fundament | ✅ ~1.5 Wochen | ~70% |
| 2 Wanted-System | ✅ ~1 Woche | ~40% |
| 3 Such-/Download-Flow | ✅ ~1 Woche | ~50% |
| 4 Provider-UI | ✅ ~3-4 Tage | ~20% |
| 5 Upgrade + Automation | ✅ ~3-4 Tage | ~30% |
| 6 Erweiterung + Polish | ~1 Woche | ~20% |
| **Gesamt** | **~5-6 Wochen** | |

Ohne Bazarr-Code-Uebernahme waere der Aufwand ~12-16 Wochen.

---

## Technische Grundlagen

### Warum kein subliminal als Dependency?

Sublarr nutzt ein eigenes leichtgewichtiges Provider-System statt subliminal direkt:
- subliminal bringt ~15 transitive Dependencies (stevedore, dogpile.cache, enzyme, etc.)
- Bazarrs subliminal_patch ist eine schwer wartbare Fork mit Metaclass-Magic
- Sublarrs Provider-System: ~1200 Zeilen, 1 neue Dependency (rarfile), saubere Architektur
- Konzepte (Interface, Scoring, Archive-Handling) wurden uebernommen, Code wurde vereinfacht

### Provider-Erweiterung

Neuen Provider hinzufuegen:
1. `backend/providers/myprovider.py` erstellen
2. `SubtitleProvider` erben, `name`/`languages` setzen
3. `search()` und `download()` implementieren
4. `@register_provider` Decorator
5. Config-Felder in `config.py` hinzufuegen
6. Import in `ProviderManager._init_providers()` hinzufuegen

### Bazarr-Komponenten als Referenz

| Bazarr-Quelle | Sublarr-Nutzung |
|---|---|
| `subliminal_patch/providers/jimaku.py` | Architektur-Vorlage fuer `providers/jimaku.py` |
| `subliminal_patch/providers/animetosho.py` | Feed-API Pattern fuer `providers/animetosho.py` |
| `subliminal_patch/providers/mixins.py` | ZIP/RAR/XZ Extraction Logic |
| `subliminal_patch/score.py` | Scoring-Weights (Episode/Movie) |
| `subliminal_patch/http.py` | RetryingSession Pattern |
| `bazarr/subtitles/wanted/` | Wanted-Detection Algorithmus (Milestone 2) |
| `bazarr/subtitles/upgrade.py` | Upgrade-Logik Konzept (Milestone 5) |
