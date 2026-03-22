# Sublarr — UI Gap Analysis

Vergleich: Was die UI haben sollte vs. was tatsächlich vorhanden ist.

**Methode:** Backend-Routen, Config-Felder (config.py) und bestehende UI-Komponenten vollständig verglichen.

---

## Teil A — Fehlende UI für vorhandene Backend-Features

Diese Features **existieren im Backend**, haben aber **keine UI-Anbindung**.

### A1 — Bibliothek & Serien

| Feature | Backend-Route | Status UI |
|---------|--------------|-----------|
| Re-scan Series | POST (noch nicht implementiert) | Button vorhanden, gibt nur Toast "coming soon" |
| Movie Detail Page | vorhandene Library-Daten | Filme in Library-Grid anklickbar? Kein Detailseite wie SeriesDetail |
| Multiple Sonarr-Instanzen | `sonarr_instances_json` in Config | UI zeigt nur eine Sonarr-Instanz |
| Multiple Radarr-Instanzen | `radarr_instances_json` in Config | UI zeigt nur eine Radarr-Instanz |
| NFO exportieren | POST `/subtitles/export-nfo` | Keine Schaltfläche in der UI |
| Bazarr-Import | POST `/import/bazarr` | Keine UI vorhanden |
| Kompatibilitäts-Check | POST `/compat-check`, `/compat-check/single` | Keine UI vorhanden |

### A2 — Sprachprofile

| Feature | Backend-Route | Status UI |
|---------|--------------|-----------|
| Sprachprofile erstellen | POST `/language-profiles` | Nur als Dropdown-Filter in Library vorhanden — keine Verwaltungsseite |
| Sprachprofile bearbeiten | PUT `/language-profiles/<id>` | Keine UI |
| Sprachprofile löschen | DELETE `/language-profiles/<id>` | Keine UI |

> **Sprachprofile sind ein zentrales Feature** (sie steuern welche Sprachen für welche Serien gesucht werden), aber es gibt keine dedizierte Seite dafür.

### A3 — Glossar

| Feature | Backend-Route | Status UI |
|---------|--------------|-----------|
| Glossar-Eintrag hinzufügen | POST `/glossary` | GlossaryPanel zeigt Einträge, aber kein "Hinzufügen" |
| Glossar-Eintrag bearbeiten | PUT `/glossary/<id>` | Keine UI |
| Glossar-Eintrag löschen | DELETE `/glossary/<id>` | Keine UI |
| Glossar exportieren | GET `/glossary/export` | Keine UI |

### A4 — Webhooks & Hooks

| Feature | Backend-Route | Status UI |
|---------|--------------|-----------|
| Eingehende Webhooks konfigurieren | GET/POST/PUT/DELETE `/webhooks` | Keine UI (nur ausgehend?) |
| Hook-Manager (Automatisierungs-Hooks) | GET/POST/PUT/DELETE `/hooks` | Keine dedizierte UI |
| Hook testen | POST `/hooks/<id>/test` | Keine UI |
| Hook-Logs anzeigen | GET `/hooks/logs` | Keine UI |
| Hook-Logs leeren | DELETE `/hooks/logs` | Keine UI |

### A5 — Benachrichtigungen

| Feature | Backend-Route | Status UI |
|---------|--------------|-----------|
| Benachrichtigungsverlauf | GET `/notifications/history` | Keine UI |
| Benachrichtigung erneut senden | POST `/history/<id>/resend` | Keine UI |
| Event-Katalog (welche Events existieren) | GET `/events/catalog` | Keine UI |
| Variablen pro Event-Typ | GET `/variables/<event_type>` | Keine UI (für Template-Editor wichtig) |

### A6 — Übersetzung

| Feature | Backend-Route | Status UI |
|---------|--------------|-----------|
| Ollama-Modell herunterladen | POST `/backends/ollama/pull` | Keine UI — Modell muss manuell auf dem Server installiert werden |
| Übersetzungs-Backend-Stats | GET `/backends/stats` | Keine UI |
| Translation-Memory-Stats | GET `/translation-memory/stats` | Keine UI |
| Translation-Memory-Cache leeren | DELETE `/translation-memory/cache` | Keine UI |
| Whisper-Transkription starten | POST `/transcribe` | Keine UI |
| Wanted — Batch-Übersetzen | POST `/wanted/batch-translate` | Keine UI |

### A7 — Subtitle-Tools (im Editor)

| Feature | Backend-Route | Status UI |
|---------|--------------|-----------|
| Zeilen aufteilen | POST `/split-lines` | Keine UI |
| Timing normalisieren | POST `/timing-normalize` | Keine UI |
| Subtitle-Format konvertieren | POST `/convert` | Keine UI |
| OP/ED erkennen (Opening/Ending-Fenster) | POST `/detect-opening-ending` | Keine UI |

### A8 — System & Wartung

| Feature | Backend-Route | Status UI |
|---------|--------------|-----------|
| Einstellungen exportieren | GET `/config/export` | Keine UI |
| Einstellungen importieren | POST `/config/import` | Keine UI |
| Vollständiges Backup erstellen | POST `/backup/full` | System-Einstellungen haben DB-Backup, aber kein "Full Backup" |
| Backup-Liste anzeigen | GET `/backup/full/list` | Keine UI |
| Backup herunterladen | GET `/backup/full/download/<filename>` | Keine UI |
| Backup wiederherstellen | POST `/backup/full/restore` | Keine UI |
| Datenbank-Vacuum | POST `/database/vacuum` | Keine UI |
| ffprobe-Cache-Stats | GET `/cache/ffprobe/stats` | Keine UI |
| ffprobe-Cache leeren | POST `/cache/ffprobe/cleanup` | Keine UI |
| Update-Check | GET `/update` | Keine UI |
| Wanted-Liste aufräumen | POST `/wanted/cleanup` | Keine UI |
| Wanted-Liste refreshen | POST `/wanted/refresh` | Keine Schaltfläche sichtbar |

### A9 — Remux-Feature

Das Backend hat ein vollständiges Remux-System (`backend/routes/remux.py`), aber **keinerlei UI**:

| Feature | Status |
|---------|--------|
| Remux starten (MKV-Tracks neu schreiben) | Keine UI |

> Zugehörige Einstellungsfelder (`remux_trash_dir`, `remux_backup_retention_days`, `remux_use_reflink`, `remux_arr_pause_enabled`) → siehe [SETTINGS_GAP_ANALYSIS.md](SETTINGS_GAP_ANALYSIS.md) Abschnitt 12.

### A10 — Fehlende Einstellungsfelder

> Alle fehlenden und fehlerhaften Config-Felder sind vollständig dokumentiert in **[SETTINGS_GAP_ANALYSIS.md](SETTINGS_GAP_ANALYSIS.md)**.
>
> Kurzfassung: ~70 Config-Felder ohne korrekte UI-Anbindung, davon 14 mit falschem Key-Namen (werden still ignoriert). Kritischste Kategorie: `AutomationSettings.tsx` — alle gespeicherten Werte landen nicht im Backend.

---

## Teil B — Konzeptionell fehlende Features

Features die ein vollständiger Subtitle-Manager **haben sollte**, aber weder Backend noch UI aktuell bieten.

### B1 — Kernfunktionen

| Feature | Priorität | Begründung |
|---------|-----------|------------|
| **Movie Detail Page** | Hoch | Filme in der Library haben kein Detailpage wie Serien — Untertitel für Filme können kaum verwaltet werden |
| **Sprachprofil-Verwaltungsseite** | Hoch | Profile sind zentral für die Automation aber haben keine eigene Seite |
| **Saison-Batch-Aktionen** | Mittel | "Alle fehlenden in Staffel X suchen" — aktuell nur auf Serien-Ebene |

> Passwort / API-Key ändern → Einstellungsfrage, dokumentiert in [SETTINGS_GAP_ANALYSIS.md](SETTINGS_GAP_ANALYSIS.md) Abschnitt 9.

### B2 — Subtitle-Editor Erweiterungen

| Feature | Priorität | Begründung |
|---------|-----------|------------|
| **Zeilen-Split/Merge im Editor** | Mittel | Backend hat `/split-lines`, aber keine UI — häufige Bearbeitungsoperation |
| **Timing-Normalisierung im Editor** | Mittel | Backend hat `/timing-normalize`, aber keine UI |
| **Format-Konverter** | Mittel | Backend hat `/convert`, aber keine UI — nützlich für ASS↔SRT |
| **Suchen & Ersetzen im Editor** | Mittel | Standard-Editor-Feature das fehlt |
| **Undo/Redo im Editor** | Mittel | Undo existiert für Processing (`/tools/process/undo`) aber nicht allgemein im Editor |

### B3 — Übersetzungs-Workflow

| Feature | Priorität | Begründung |
|---------|-----------|------------|
| **Translation-Memory UI** | Mittel | Cache-Statistiken und -Verwaltung — wichtig für Qualität und Speicher |
| **Prompt-Template-Editor** | Mittel | `prompt_template` in Config ist leer = auto-generiert, aber kein UI zum Anpassen |
| **Übersetzungs-Backend-Vergleich** | Niedrig | Zwei Backends parallel laufen lassen und Ergebnis vergleichen |
| **Batch-Übersetzen aus Wanted** | Mittel | Backend hat `/wanted/batch-translate` — alle Wanted-Items übersetzen |

### B4 — Monitoring & Observability

| Feature | Priorität | Begründung |
|---------|-----------|------------|
| **Update-Check / Changelog in der UI** | Mittel | Backend hat `/update` Route — Update-Check sollte im Dashboard oder System sichtbar sein |
| **Provider-Rate-Limit-Status** | Mittel | Verbleibende Quota pro Provider sehen (wichtig bei OpenSubtitles etc.) |
| **Circuit-Breaker-Status** | Niedrig | Welche Provider aktuell im OPEN-Zustand sind |
| **Translation-Backend-Stats-Seite** | Niedrig | Erfolgsquote, Latenz, Token-Verbrauch pro Backend |
| **ffprobe-Cache-Statistiken** | Niedrig | Wie viele Einträge im Cache, Größe, Hit-Rate |

### B5 — Benachrichtigungen & Automatisierung

| Feature | Priorität | Begründung |
|---------|-----------|------------|
| **Benachrichtigungsverlauf** | Mittel | Welche Benachrichtigungen wann gesendet wurden — Backend hat `/notifications/history` |
| **Hook-Verwaltung UI** | Mittel | Backend hat vollständiges Hook-CRUD — Automatisierungs-Hooks (z.B. nach Download Script ausführen) |

> `jellyfin_play_translate_enabled` und `auto_sync_after_download` sind Einstellungsfelder → [SETTINGS_GAP_ANALYSIS.md](SETTINGS_GAP_ANALYSIS.md) Abschnitt 5.

### B6 — Import & Migration

| Feature | Priorität | Begründung |
|---------|-----------|------------|
| **Bazarr-Import-Wizard** | Niedrig | Backend hat `/import/bazarr` — Migration von Bazarr wäre ein Selling-Point |
| **Einstellungen Export/Import** | Mittel | Konfiguration sichern und auf andere Instanzen übertragen |
| **Backup-Management UI** | Hoch | Vollständige Backup-Liste, Download, Restore — Backend komplett vorhanden, UI fehlt |

### B7 — Erweiterte Bibliotheks-Features

| Feature | Priorität | Begründung |
|---------|-----------|------------|
| **AniDB-Mapping-Verwaltung** | Niedrig | AniDB-Cache einsehen und manuell überschreiben |
| **NFO-Export-Button** | Niedrig | Backend hat `/subtitles/export-nfo` — für Kodi/Jellyfin-User nützlich |
| **Remux-UI** | Niedrig | MKV-Tracks neu schreiben — mächtiges Feature komplett ohne UI |
| **Whisper-Transkriptions-UI** | Niedrig | Audio → Untertitel direkt aus der Episode-Ansicht |
| **OP/ED-Erkennung UI** | Niedrig | Opening/Ending automatisch erkennen und aus Untertiteln ausschließen |

---

## Zusammenfassung

### Kritische Lücken (sofort angehen)

1. **Movie Detail Page** — Filme haben keine Verwaltungsansicht
2. **Sprachprofil-Verwaltungsseite** — zentrales Feature ohne UI
3. **Backup-Management** — Backend komplett vorhanden, UI fehlt komplett
4. **Re-scan Series** — Button vorhanden, Logik fehlt
5. **AutomationSettings komplett kaputt** — alle Config-Keys falsch → siehe [SETTINGS_GAP_ANALYSIS.md](SETTINGS_GAP_ANALYSIS.md)

### Mittelfristig

6. **Glossar-Verwaltung** (Add/Edit/Delete in GlossaryPanel)
7. **Settings Export/Import**
8. **Benachrichtigungsverlauf**
9. **Fehlende & fehlerhafte Einstellungsfelder** → vollständig in [SETTINGS_GAP_ANALYSIS.md](SETTINGS_GAP_ANALYSIS.md)
10. **Hook-Manager**
11. **Translation-Memory UI**
12. **Batch-Übersetzen (Wanted)**
13. **Saison-Batch-Aktionen**

### Langfristig / Nice-to-have

14. **Remux-UI**
15. **Whisper-Transkriptions-UI**
16. **Bazarr-Import-Wizard**
17. **Update-Check im Dashboard**
18. **OP/ED-Erkennung**
19. **Subtitle-Format-Konverter**
20. **Provider-Rate-Limit-Status**

---

*Stand: 2026-03-21 — Analyse basiert auf vollständigem Vergleich von backend/routes/, backend/config.py und frontend/src/*
