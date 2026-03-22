# Sublarr UI Test Plan — v0.33.0-beta

> **Instanz:** http://192.168.178.194:5765
> **Datum:** 2026-03-22
> **Methode:** Manuell via Playwright-Browser
> **Quellen:** UI_FUNCTIONS.md · UI_GAP_ANALYSIS.md · SETTINGS_GAP_ANALYSIS.md
> **Ergebnisse:** → [FINDINGS.md](FINDINGS.md)

---

## Legende

| Symbol | Bedeutung |
|--------|-----------|
| ✅ | Bestanden |
| ❌ | Fehlgeschlagen |
| ⚠️ | Eingeschränkt / UX-Problem |
| ⏳ | Nicht getestet |
| 🐛 | Bekannter Bug (aus Gap-Analyse) |
| 💅 | UX / Design-Bewertung |

---

## Testziel

Vollständige manuelle Verifikation aller UI-Funktionen auf der deployed Instanz.
Fokus:
1. **Funktionalität** — Reagiert die UI korrekt auf Benutzeraktionen?
2. **Benutzerfreundlichkeit** — Ist die UI intuitiv, konsistent, fehlertolerant?
3. **Bekannte Lücken** — Sind dokumentierte Bugs sichtbar oder behoben?

---

## BEREICH 1 — Navigation & Shell

### 1.1 Sidebar-Navigation

| # | Test | Schritte | Erwartetes Ergebnis | Status |
|---|------|----------|---------------------|--------|
| 1.1.1 | Dashboard-Link | Klick "Dashboard" | URL `/`, Widgets laden | ⏳ |
| 1.1.2 | Library-Link | Klick "Library" | URL `/library`, Serienraster erscheint | ⏳ |
| 1.1.3 | Wanted-Link | Klick "Wanted" | URL `/wanted`, Tabelle erscheint | ⏳ |
| 1.1.4 | Activity-Link | Klick "Activity" | URL `/activity`, Jobliste erscheint | ⏳ |
| 1.1.5 | Queue-Link | Klick "Queue" | URL `/queue`, Queue-Status erscheint | ⏳ |
| 1.1.6 | History-Link | Klick "History" | URL `/history`, Verlaufstabelle erscheint | ⏳ |
| 1.1.7 | Blacklist-Link | Klick "Blacklist" | URL `/blacklist`, Blacklist erscheint | ⏳ |
| 1.1.8 | Settings-Link | Klick "Settings" | URL `/settings`, General-Tab aktiv | ⏳ |
| 1.1.9 | Statistics-Link | Klick "Statistics" | URL `/statistics`, Charts laden | ⏳ |
| 1.1.10 | Tasks-Link | Klick "Tasks" | URL `/tasks`, Taskliste erscheint | ⏳ |
| 1.1.11 | Logs-Link | Klick "Logs" | URL `/logs`, Log-Output erscheint | ⏳ |
| 1.1.12 | Plugins-Link | Klick "Plugins" | URL `/plugins`, Marketplace erscheint | ⏳ |
| 1.1.13 | Aktiver Link Highlight | Aktuelle Seite prüfen | Sidebar-Eintrag hervorgehoben (aktiv-Zustand) | ⏳ |
| 1.1.14 | Sidebar kollabieren | Hamburger/Chevron klicken | Sidebar → Icons only | ⏳ |
| 1.1.15 | Sidebar expandieren | Erneut klicken | Sidebar → Labels sichtbar | ⏳ |

### 1.2 Theme & Sprache

| # | Test | Schritte | Erwartetes Ergebnis | Status |
|---|------|----------|---------------------|--------|
| 1.2.1 | Dark Mode | ThemeToggle klicken | Gesamte UI → dunkles Theme | ⏳ |
| 1.2.2 | Light Mode | ThemeToggle erneut | UI → helles Theme | ⏳ |
| 1.2.3 | Theme persistent | Seite neu laden | Theme bleibt (localStorage) | ⏳ |
| 1.2.4 | Sprache DE | LanguageSwitcher → DE | Labels auf Deutsch | ⏳ |
| 1.2.5 | Sprache EN | LanguageSwitcher → EN | Labels auf Englisch | ⏳ |
| 1.2.6 | Sprache persistent | Seite neu laden | Sprache bleibt erhalten | ⏳ |

### 1.3 Keyboard Shortcuts

| # | Test | Schritte | Erwartetes Ergebnis | Status |
|---|------|----------|---------------------|--------|
| 1.3.1 | Global Search öffnen | `Ctrl+K` | GlobalSearchModal erscheint | ⏳ |
| 1.3.2 | Global Search schließen | `Escape` | Modal verschwindet | ⏳ |
| 1.3.3 | Shortcuts-Hilfe | `?` drücken | KeyboardShortcutsModal erscheint | ⏳ |
| 1.3.4 | Shortcuts-Hilfe schließen | `Escape` / X | Modal schließt | ⏳ |

### 1.4 Global Search Funktion

| # | Test | Schritte | Erwartetes Ergebnis | Status |
|---|------|----------|---------------------|--------|
| 1.4.1 | Suche nach Serie | Ctrl+K → Serientitel tippen | Ergebnisliste erscheint | ⏳ |
| 1.4.2 | Ergebnis anklicken | Ergebnis klicken | Navigiert zur Serie/Episode | ⏳ |
| 1.4.3 | Leere Suche | Ctrl+K ohne Text | Leer-Zustand korrekt angezeigt | ⏳ |

### 1.5 404-Seite

| # | Test | Schritte | Erwartetes Ergebnis | Status |
|---|------|----------|---------------------|--------|
| 1.5.1 | Ungültige URL | `/nicht-vorhanden` | NotFound-Seite erscheint | ⏳ |
| 1.5.2 | Back-Button | "Back" klicken | Navigiert zurück | ⏳ |

### 1.6 Mobile Navigation 💅

| # | Test | Schritte | Erwartetes Ergebnis | Status |
|---|------|----------|---------------------|--------|
| 1.6.1 | Mobile Viewport | Auf 375px Breite | Bottom-Nav erscheint, Sidebar ausgeblendet | ⏳ |
| 1.6.2 | Bottom-Nav Links | Alle Icons antippen | Navigation funktioniert | ⏳ |
| 1.6.3 | Layout-Integrität | Alle Hauptseiten | Kein Overflow / horizontales Scrollen | ⏳ |

---

## BEREICH 2 — Dashboard (`/`)

### 2.1 Widget-Anzeige

| # | Test | Schritte | Erwartetes Ergebnis | Status |
|---|------|----------|---------------------|--------|
| 2.1.1 | StatCardsWidget | Dashboard aufrufen | Kennzahlen (Serien, Filme, Fehlend, ...) laden | ⏳ |
| 2.1.2 | WantedSummaryWidget | Sichtbar | Wanted-Status-Übersicht korrekt | ⏳ |
| 2.1.3 | RecentActivityWidget | Sichtbar | Letzte Jobs aufgelistet | ⏳ |
| 2.1.4 | AutomationWidget | Sichtbar | Automations-Zeitplan + Status | ⏳ |
| 2.1.5 | ProviderHealthWidget | Sichtbar | Provider-Status-Badges (grün/rot/gelb) | ⏳ |
| 2.1.6 | ServiceStatusWidget | Sichtbar | Sonarr/Radarr/Ollama-Status korrekt | ⏳ |
| 2.1.7 | DiskSpaceWidget | Sichtbar | Festplattennutzung numerisch + visuell | ⏳ |
| 2.1.8 | QualityWidget | Sichtbar | Durchschnittlicher Qualitätsscore | ⏳ |
| 2.1.9 | TranslationStatsWidget | Sichtbar | Übersetzungsstatistiken laden | ⏳ |
| 2.1.10 | QuickActionsWidget | Sichtbar | Schnellzugriffs-Buttons klickbar | ⏳ |

### 2.2 Widget-Verwaltung

| # | Test | Schritte | Erwartetes Ergebnis | Status |
|---|------|----------|---------------------|--------|
| 2.2.1 | Widget-Modal öffnen | Settings-Icon klicken | WidgetSettingsModal erscheint | ⏳ |
| 2.2.2 | Widget ausblenden | Toggle deaktivieren | Widget verschwindet vom Dashboard | ⏳ |
| 2.2.3 | Widget einblenden | Toggle aktivieren | Widget erscheint wieder | ⏳ |
| 2.2.4 | Modal schließen | X klicken | Modal schließt | ⏳ |

### 2.3 UX Dashboard 💅

| # | Test | Schritte | Erwartetes Ergebnis | Status |
|---|------|----------|---------------------|--------|
| 2.3.1 | Ladezeit | Dashboard erstmals öffnen | Skeleton/Loader sichtbar, dann Daten | ⏳ |
| 2.3.2 | Refreshing | Seite neu laden | Keine Layout-Shifts, konsistentes Layout | ⏳ |
| 2.3.3 | Leere Bibliothek | Alle Widgets bei 0 Serien | Keine Fehler, sinnvolle Leer-Zustände | ⏳ |

---

## BEREICH 3 — Bibliothek (`/library`)

### 3.1 Grundfunktionen

| # | Test | Schritte | Erwartetes Ergebnis | Status |
|---|------|----------|---------------------|--------|
| 3.1.1 | Serien-Tab | Library öffnen | Standard-Tab "Series" aktiv, Grid lädt | ⏳ |
| 3.1.2 | Movies-Tab | "Movies" klicken | Film-Grid erscheint | ⏳ |
| 3.1.3 | Rasteransicht | Raster-Icon klicken | LibraryCards angezeigt | ⏳ |
| 3.1.4 | Tabellenansicht | Tabellen-Icon klicken | VirtualLibraryTable erscheint | ⏳ |

### 3.2 Filter & Suche

| # | Test | Schritte | Erwartetes Ergebnis | Status |
|---|------|----------|---------------------|--------|
| 3.2.1 | Textsuche | Begriff in Suchfeld tippen | Liste filtert sofort | ⏳ |
| 3.2.2 | Suche leeren | Suchfeld leeren | Volle Liste wieder sichtbar | ⏳ |
| 3.2.3 | Filter "Alle" | Chip "Alle" klicken | Kein Filter aktiv | ⏳ |
| 3.2.4 | Filter "Fehlend" | Chip "Fehlend" | Nur Serien mit fehlenden Untertiteln | ⏳ |
| 3.2.5 | Filter "Niedriger Score" | Chip anklicken | Nur niedrig-scorende Serien | ⏳ |
| 3.2.6 | Filter "Anime" | Chip anklicken | Nur Anime-Serien | ⏳ |
| 3.2.7 | Filter "Vollständig" | Chip anklicken | Nur vollständige Serien | ⏳ |
| 3.2.8 | Profil-Filter | Dropdown → Profil wählen | Nur Serien mit diesem Profil | ⏳ |

### 3.3 Pagination

| # | Test | Schritte | Erwartetes Ergebnis | Status |
|---|------|----------|---------------------|--------|
| 3.3.1 | Weiter | "Weiter"-Button | Nächste Seite, Seitenzahl erhöht | ⏳ |
| 3.3.2 | Zurück | "Zurück"-Button | Vorherige Seite | ⏳ |
| 3.3.3 | Direktsprung | Seitenzahl klicken | Direkt zu gewählter Seite | ⏳ |
| 3.3.4 | X–Y von Z | Anzeige prüfen | Korrekte Bereichsangabe | ⏳ |

### 3.4 Bulk-Aktionen (Tabellenansicht)

| # | Test | Schritte | Erwartetes Ergebnis | Status |
|---|------|----------|---------------------|--------|
| 3.4.1 | Mehrfachauswahl | Checkboxen aktivieren | Auswahl-Leiste erscheint | ⏳ |
| 3.4.2 | "Alle Fehlenden suchen" | Button klicken | Suchauftrag gestartet, Toast erscheint | ⏳ |
| 3.4.3 | Auswahl aufheben | Button klicken | Alle Checkboxen deaktiviert | ⏳ |

### 3.5 Bulk-Sync

| # | Test | Schritte | Erwartetes Ergebnis | Status |
|---|------|----------|---------------------|--------|
| 3.5.1 | Bulk-Sync öffnen | Toggle-Button | Bulk-Sync-Panel erscheint | ⏳ |
| 3.5.2 | Bereich wählen | Dropdown "Gesamte Bibliothek" | Option wählbar | ⏳ |
| 3.5.3 | Engine wählen | Engine-Override Dropdown | Optionen: Default/alass/ffsubsync | ⏳ |
| 3.5.4 | Sync starten | Button "Bulk-Sync starten" | Fortschrittsbalken erscheint, WebSocket-Updates | ⏳ |

### 3.6 UX Bibliothek 💅

| # | Test | Schritte | Erwartetes Ergebnis | Status |
|---|------|----------|---------------------|--------|
| 3.6.1 | Poster-Qualität | LibraryCards | Bilder laden ohne Bruch, korrekte Größe | ⏳ |
| 3.6.2 | Leer-Zustand | Bei 0 Serien | Sinnvoller Hinweis (kein leeres Grid) | ⏳ |
| 3.6.3 | Film-Detail-Link 🐛 | Film anklicken | Detail-Seite öffnet (GAP: MovieDetailPage fehlt laut Gap-Analyse) | ⏳ |

---

## BEREICH 4 — Seriendetail (`/library/series/:id`)

### 4.1 Header & Hero

| # | Test | Schritte | Erwartetes Ergebnis | Status |
|---|------|----------|---------------------|--------|
| 4.1.1 | Breadcrumb | Seriendetail öffnen | "Library > [Serientitel]" sichtbar, klickbar | ⏳ |
| 4.1.2 | Poster / Cover | Sichtbar | Bild geladen, korrekte Darstellung | ⏳ |
| 4.1.3 | Metadaten | Sichtbar | Jahr, Episodenanzahl, Status, Sprachen | ⏳ |
| 4.1.4 | Re-scan-Button 🐛 | Klick | Toast "coming soon" oder funktioniert (GAP: nicht implementiert) | ⏳ |

### 4.2 SeriesSettingsPanel

| # | Test | Schritte | Erwartetes Ergebnis | Status |
|---|------|----------|---------------------|--------|
| 4.2.1 | Panel öffnen | Settings-Icon klicken | Panel erscheint | ⏳ |
| 4.2.2 | Sprachprofil setzen | Dropdown wählen | Gespeichert, Toast erscheint | ⏳ |
| 4.2.3 | Format setzen | Dropdown wählen | ASS/SRT/VTT wählbar | ⏳ |
| 4.2.4 | HI-Toggle | Umschalten | Gespeichert | ⏳ |
| 4.2.5 | Forced-Toggle | Umschalten | Gespeichert | ⏳ |
| 4.2.6 | Fansub-Override | Button klicken | FansubOverrideModal öffnet | ⏳ |
| 4.2.7 | Embedded extrahieren | Button klicken | Extraktions-Banner erscheint, Fortschritt sichtbar | ⏳ |
| 4.2.8 | Health-Check | Button klicken | HealthCheckPanel öffnet | ⏳ |
| 4.2.9 | Cleanup | Button klicken | SubtitleCleanupModal öffnet | ⏳ |

### 4.3 GlossaryPanel

| # | Test | Schritte | Erwartetes Ergebnis | Status |
|---|------|----------|---------------------|--------|
| 4.3.1 | Panel öffnen | Glossar-Icon klicken | Panel erscheint | ⏳ |
| 4.3.2 | Einträge anzeigen | Sichtbar | Fansub-Begriffe + Definitionen gelistet | ⏳ |
| 4.3.3 | Suche im Glossar | Text eingeben | Liste filtert | ⏳ |
| 4.3.4 | Eintrag hinzufügen 🐛 | UI prüfen | GAP: Kein "Hinzufügen"-Button (bekannte Lücke) | ⏳ |

### 4.4 Staffel-Navigation

| # | Test | Schritte | Erwartetes Ergebnis | Status |
|---|------|----------|---------------------|--------|
| 4.4.1 | Staffel-Tabs | Tabs S1, S2, ... | Alle Staffeln wechselbar | ⏳ |
| 4.4.2 | Staffel-Zusammenfassung | Pro Tab | Episodenanzahl + Fehlend + Score | ⏳ |

### 4.5 Episodenliste

| # | Test | Schritte | Erwartetes Ergebnis | Status |
|---|------|----------|---------------------|--------|
| 4.5.1 | Episodenliste | Staffel öffnen | Alle Episoden gelistet mit Status-Badges | ⏳ |
| 4.5.2 | Status-Badges | Sichtbar | Sprachen + Qualitäts-Scores angezeigt | ⏳ |
| 4.5.3 | Aktionsmenü öffnen | Dropdown-Button klicken | Alle Aktionen gelistet | ⏳ |

### 4.6 Episoden-Aktionen

| # | Test | Schritte | Erwartetes Ergebnis | Status |
|---|------|----------|---------------------|--------|
| 4.6.1 | Suchen | Aktion "Suchen" | Suchauftrag startet, Toast erscheint | ⏳ |
| 4.6.2 | Interaktive Suche | Aktion klicken | InteractiveSearchModal öffnet | ⏳ |
| 4.6.3 | Bearbeiten | Aktion klicken | SubtitleEditorModal öffnet | ⏳ |
| 4.6.4 | Vorschau | Aktion klicken | Untertitel-Vorschau erscheint | ⏳ |
| 4.6.5 | Vergleich | Aktion klicken | SubtitleComparison öffnet | ⏳ |
| 4.6.6 | Synchronisieren | Aktion klicken | SyncControls erscheinen | ⏳ |
| 4.6.7 | Übersetzen | Aktion klicken | Übersetzungsjob startet | ⏳ |
| 4.6.8 | Track extrahieren | Aktion klicken | Extraktion startet | ⏳ |
| 4.6.9 | Löschen | Aktion klicken | Bestätigungs-Dialog erscheint | ⏳ |
| 4.6.10 | Lösch-Dialog bestätigen | "Löschen" klicken | Datei gelöscht, Toast erscheint | ⏳ |
| 4.6.11 | Lösch-Dialog abbrechen | "Abbrechen" klicken | Dialog schließt, nichts gelöscht | ⏳ |
| 4.6.12 | Blacklist | Aktion klicken | Eintrag zur Blacklist, Toast | ⏳ |

### 4.7 SubtitleEditorModal 💅

| # | Test | Schritte | Erwartetes Ergebnis | Status |
|---|------|----------|---------------------|--------|
| 4.7.1 | Editor öffnet | Bearbeiten-Aktion | Modal öffnet mit Inhalt | ⏳ |
| 4.7.2 | Tabs im Editor | Tabs sichtbar | Text/Diff/Waveform/... tabs wechselbar | ⏳ |
| 4.7.3 | Zeile bearbeiten | Text ändern | Änderung möglich | ⏳ |
| 4.7.4 | Speichern | Speichern-Button | Gespeichert, Toast erscheint | ⏳ |
| 4.7.5 | Schließen | X / Abbrechen | Modal schließt ohne Fehler | ⏳ |

### 4.8 InteractiveSearchModal

| # | Test | Schritte | Erwartetes Ergebnis | Status |
|---|------|----------|---------------------|--------|
| 4.8.1 | Modal öffnet | Interaktive Suche | Modal mit Suchergebnissen | ⏳ |
| 4.8.2 | Ergebnis herunterladen | Download-Button | Download startet, Toast erscheint | ⏳ |
| 4.8.3 | Ergebnis blacklisten | Blacklist-Button | Geblockt, aus Liste entfernt | ⏳ |
| 4.8.4 | Modal schließen | X | Modal schließt | ⏳ |

---

## BEREICH 5 — Wanted (`/wanted`)

### 5.1 Zusammenfassungs-Kacheln

| # | Test | Schritte | Erwartetes Ergebnis | Status |
|---|------|----------|---------------------|--------|
| 5.1.1 | Wanted-Kachel | Sichtbar | Anzahl ausstehender Elemente | ⏳ |
| 5.1.2 | Extracted-Kachel | Sichtbar | Anzahl extrahierter Elemente | ⏳ |
| 5.1.3 | Failed-Kachel | Sichtbar | Anzahl fehlgeschlagener Versuche | ⏳ |
| 5.1.4 | Ignored-Kachel | Sichtbar | Anzahl ignorierter Elemente | ⏳ |

### 5.2 Filter

| # | Test | Schritte | Erwartetes Ergebnis | Status |
|---|------|----------|---------------------|--------|
| 5.2.1 | Status-Filter | "Failed" wählen | Nur fehlgeschlagene Items | ⏳ |
| 5.2.2 | Typ-Filter | "Movie" wählen | Nur Film-Items | ⏳ |
| 5.2.3 | Textsuche | Titel tippen | Liste filtert | ⏳ |
| 5.2.4 | Sortierung | Sortierfeld ändern | Liste neu geordnet | ⏳ |
| 5.2.5 | Sortierrichtung | Toggle | Auf-/Absteigend wechselt | ⏳ |

### 5.3 Tabellen-Aktionen

| # | Test | Schritte | Erwartetes Ergebnis | Status |
|---|------|----------|---------------------|--------|
| 5.3.1 | Suchen (Zeile) | Such-Button | Suchauftrag startet | ⏳ |
| 5.3.2 | Interaktive Suche | Button | Modal öffnet | ⏳ |
| 5.3.3 | Blacklisten | Button | Element geblockt | ⏳ |
| 5.3.4 | Batch-Auswahl | Checkboxen | Batch-Aktionsleiste erscheint | ⏳ |
| 5.3.5 | Batch-Suche | "Alle suchen" | Batch-Job startet | ⏳ |

---

## BEREICH 6 — Activity (`/activity`)

| # | Test | Schritte | Erwartetes Ergebnis | Status |
|---|------|----------|---------------------|--------|
| 6.1 | Tab "Alle" | Standard | Alle Jobs sichtbar | ⏳ |
| 6.2 | Tab "Abgeschlossen" | Klick | Nur erfolgreiche Jobs | ⏳ |
| 6.3 | Tab "Fehlgeschlagen" | Klick | Nur fehlgeschlagene Jobs | ⏳ |
| 6.4 | Tab "Läuft" | Klick | Nur aktive Jobs | ⏳ |
| 6.5 | Erweiterte Zeile | Zeile anklicken | Detailinfos ausklappen | ⏳ |
| 6.6 | Erneut versuchen | Bei Failed: Button | Job neu gestartet | ⏳ |
| 6.7 | Pagination | Mehrere Seiten | Weiter/Zurück funktioniert | ⏳ |

---

## BEREICH 7 — Queue (`/queue`)

| # | Test | Schritte | Erwartetes Ergebnis | Status |
|---|------|----------|---------------------|--------|
| 7.1 | Queue-Seite | Aufrufen | Alle Status-Bereiche sichtbar | ⏳ |
| 7.2 | Aktive Jobs | Sichtbar | Jobs gelistet oder Leer-Zustand | ⏳ |
| 7.3 | Warteschlange | Sichtbar | Queue oder Leer-Zustand | ⏳ |
| 7.4 | Scanner-Status | Sichtbar | Fortschrittsbalken + Phasenindikator | ⏳ |

---

## BEREICH 8 — History (`/history`)

| # | Test | Schritte | Erwartetes Ergebnis | Status |
|---|------|----------|---------------------|--------|
| 8.1 | Gesamt-Downloads | Kachel | Zahl korrekt | ⏳ |
| 8.2 | Provider-Filter | Dropdown | Filtert nach Provider | ⏳ |
| 8.3 | Format-Filter | Dropdown | Filtert nach ASS/SRT/... | ⏳ |
| 8.4 | Pfad-Suche | Textfeld | Suche nach Dateipfad | ⏳ |
| 8.5 | Tabelle | Sichtbar | Spalten: Titel, Provider, Sprache, Format, Score, Datum | ⏳ |
| 8.6 | Pagination | Mehrere Seiten | Funktioniert | ⏳ |

---

## BEREICH 9 — Blacklist (`/blacklist`)

| # | Test | Schritte | Erwartetes Ergebnis | Status |
|---|------|----------|---------------------|--------|
| 9.1 | Liste | Aufrufen | Geblockte Items gelistet | ⏳ |
| 9.2 | Eintrag entfernen | Unblock-Button | Item entfernt, Toast erscheint | ⏳ |
| 9.3 | Leer-Zustand | Bei leerer Blacklist | Sinnvoller Hinweis | ⏳ |

---

## BEREICH 10 — Einstellungen (`/settings`) 🐛

> **Kritisch:** SETTINGS_GAP_ANALYSIS dokumentiert 14 falsche Config-Keys und ~70 fehlende Felder.
> Dieser Bereich prüft ob die Fixes aus dem UI-Verbesserungsplan (66 Schritte, Stand 2026-03-21) greifen.

### 10.1 General Settings

| # | Test | Schritte | Bekannter Bug | Status |
|---|------|----------|---------------|--------|
| 10.1.1 | Port-Feld | Speichern | ✅ Key `port` korrekt | ⏳ |
| 10.1.2 | Log-Level | Speichern | ✅ Key `log_level` korrekt | ⏳ |
| 10.1.3 | Workers-Feld 🐛 | Speichern | ⚠️ Key `workers` falsch → `scan_metadata_max_workers` | ⏳ |
| 10.1.4 | Log to File 🐛 | Toggle | ⚠️ Key `log_to_file` (bool) falsch → Backend erwartet Pfad `log_file` | ⏳ |
| 10.1.5 | Media Path | Speichern | ✅ Key `media_path` korrekt | ⏳ |
| 10.1.6 | Feldname prüfen | Netzwerk-Tab | Gesendeter Key vs. erwartetem Key im Backend | ⏳ |

### 10.2 Automation Settings 🐛 (KRITISCH)

> **Achtung:** Laut SETTINGS_GAP_ANALYSIS hat diese Seite 8 falsche Keys — alle Saves landen nicht im Backend.

| # | Test | Bekannter Bug | Ist der Fix drin? | Status |
|---|------|---------------|-------------------|--------|
| 10.2.1 | Suchintervall 🐛 | `wanted_search_frequency` → korrekt: `wanted_search_interval_hours` | | ⏳ |
| 10.2.2 | Scan on Start 🐛 | `scan_on_start` → korrekt: `wanted_search_on_startup` | | ⏳ |
| 10.2.3 | Auto-Upgrade 🐛 | `auto_upgrade_enabled` → korrekt: `upgrade_enabled` | | ⏳ |
| 10.2.4 | Upgrade-Schwellenwert 🐛 | `auto_upgrade_threshold` → korrekt: `upgrade_min_score_delta` | | ⏳ |
| 10.2.5 | Upgrade-Intervall 🐛 | `upgrade_check_frequency` → korrekt: `upgrade_scan_interval_hours` | | ⏳ |
| 10.2.6 | Auto-Übersetzen 🐛 | `auto_translate` → korrekt: `wanted_auto_translate` | | ⏳ |
| 10.2.7 | Auto-Suche bei Download 🐛 | `auto_search_on_download` → korrekt: `webhook_auto_search` | | ⏳ |
| 10.2.8 | Auto-Sync 🐛 | `auto_sync` → korrekt: `auto_sync_after_download` | | ⏳ |
| 10.2.9 | Auto-Cleanup 🐛 | `auto_cleanup` → korrekt: `auto_cleanup_after_extract` | | ⏳ |
| 10.2.10 | Speichern → Netzwerk | DevTools Network Tab | Gesendete Keys mit Backend vergleichen | ⏳ |

### 10.3 Provider Settings

| # | Test | Schritte | Erwartetes Ergebnis | Status |
|---|------|----------|---------------------|--------|
| 10.3.1 | Provider-Liste | Sichtbar | Alle Provider-Kacheln sichtbar | ⏳ |
| 10.3.2 | Provider aktivieren | Toggle | Gespeichert, Toast erscheint | ⏳ |
| 10.3.3 | API-Key eingeben | Textfeld + Speichern | Gespeichert | ⏳ |
| 10.3.4 | Drag & Drop Priorität | Provider ziehen | Reihenfolge ändert sich | ⏳ |
| 10.3.5 | Plugin-Marketplace | Tab | Marketplace-Liste erscheint | ⏳ |

### 10.4 Connections Settings

| # | Test | Schritte | Erwartetes Ergebnis | Status |
|---|------|----------|---------------------|--------|
| 10.4.1 | Sonarr URL eingeben | Textfeld | Gespeichert | ⏳ |
| 10.4.2 | Sonarr testen | Test-Button | Verbindung OK oder Fehlermeldung | ⏳ |
| 10.4.3 | Radarr URL eingeben | Textfeld | Gespeichert | ⏳ |
| 10.4.4 | Pfad-Mappings | Hinzufügen/Entfernen | Funktioniert | ⏳ |
| 10.4.5 | Media Servers Tab | Tab | Media-Server-Liste | ⏳ |
| 10.4.6 | Server hinzufügen | Button | Formular erscheint | ⏳ |
| 10.4.7 | Server testen | Test-Button | Verbindung OK oder Fehlermeldung | ⏳ |

### 10.5 Translation Settings

| # | Test | Schritte | Erwartetes Ergebnis | Status |
|---|------|----------|---------------------|--------|
| 10.5.1 | Ollama URL | Textfeld + Speichern | Gespeichert | ⏳ |
| 10.5.2 | Ollama testen | Test-Button | Verbindung OK oder Fehlermeldung | ⏳ |
| 10.5.3 | Modell-Dropdown | Wählen | Modell gespeichert | ⏳ |
| 10.5.4 | Prompt-Template | Bearbeiten | Template speicherbar | ⏳ |
| 10.5.5 | Glossar-Toggle | Aktivieren | Gespeichert | ⏳ |
| 10.5.6 | Whisper-Tab | Tab klicken | Whisper-Einstellungen sichtbar | ⏳ |

### 10.6 Subtitle Settings

| # | Test | Schritte | Erwartetes Ergebnis | Status |
|---|------|----------|---------------------|--------|
| 10.6.1 | Quellsprache | Dropdown | Gespeichert | ⏳ |
| 10.6.2 | Zielsprache | Dropdown | Gespeichert | ⏳ |
| 10.6.3 | HI-Präferenz | Dropdown | Gespeichert | ⏳ |
| 10.6.4 | Forced-Präferenz | Dropdown | Gespeichert | ⏳ |
| 10.6.5 | Scoring-Einstellungen | ScoringTab | Bewertungsfelder konfigurierbar | ⏳ |

### 10.7 Notification Settings

| # | Test | Schritte | Erwartetes Ergebnis | Status |
|---|------|----------|---------------------|--------|
| 10.7.1 | Apprise-URL eingeben | Textfeld | Gespeichert | ⏳ |
| 10.7.2 | Notify on Download | Toggle | Gespeichert | ⏳ |
| 10.7.3 | Notify on Upgrade | Toggle | Gespeichert | ⏳ |
| 10.7.4 | Templates-Tab | Tab klicken | Template-Editor sichtbar | ⏳ |
| 10.7.5 | Template bearbeiten | Text ändern + Speichern | Gespeichert | ⏳ |
| 10.7.6 | Notification History Tab 🐛 | Tab prüfen | GAP: fehlt laut Gap-Analyse | ⏳ |

### 10.8 System Settings

| # | Test | Schritte | Erwartetes Ergebnis | Status |
|---|------|----------|---------------------|--------|
| 10.8.1 | DB-Backup | Button klicken | Backup erstellt, Download-Link | ⏳ |
| 10.8.2 | Cache leeren | Button klicken | Bestätigung + Toast | ⏳ |
| 10.8.3 | Backup-Liste 🐛 | UI prüfen | GAP: Backup-List fehlt laut Gap-Analyse | ⏳ |
| 10.8.4 | Datenbank-Vacuum 🐛 | UI prüfen | GAP: Vacuum-Button fehlt laut Gap-Analyse | ⏳ |
| 10.8.5 | Config Export/Import | Buttons | Buttons vorhanden und funktional | ⏳ |

### 10.9 Security Tab

| # | Test | Schritte | Erwartetes Ergebnis | Status |
|---|------|----------|---------------------|--------|
| 10.9.1 | Passwort ändern | Neues PW eingeben + Speichern | Geändert, Toast erscheint | ⏳ |
| 10.9.2 | API-Keys Tab | Tab klicken | API-Key-Liste sichtbar | ⏳ |
| 10.9.3 | API-Key erstellen | Button + Name | Key erstellt, sichtbar | ⏳ |
| 10.9.4 | API-Key löschen | Delete-Button | Key entfernt | ⏳ |

### 10.10 Advanced Settings

| # | Test | Schritte | Erwartetes Ergebnis | Status |
|---|------|----------|---------------------|--------|
| 10.10.1 | Standalone-Ordner | Liste sichtbar | Ordner konfigurierbar | ⏳ |
| 10.10.2 | Ordner hinzufügen | Button | Eingabefeld erscheint | ⏳ |
| 10.10.3 | Migration-Tab | Tab | Alembic-Info sichtbar | ⏳ |
| 10.10.4 | Cache-Tab | Tab | Cache-Infos sichtbar | ⏳ |
| 10.10.5 | AniDB-Tab | Tab prüfen | AniDB-Einstellungen (GAP: möglicherweise fehlt) | ⏳ |
| 10.10.6 | Remux-Tab | Tab prüfen | Remux-Einstellungen (GAP: fehlt laut Gap-Analyse) | ⏳ |

---

## BEREICH 11 — Statistics (`/statistics`)

| # | Test | Schritte | Erwartetes Ergebnis | Status |
|---|------|----------|---------------------|--------|
| 11.1 | Seite laden | Aufrufen | Charts erscheinen ohne Fehler | ⏳ |
| 11.2 | Download-Chart | Sichtbar | Zeitreihe der Downloads | ⏳ |
| 11.3 | Provider-Chart | Sichtbar | Anteil pro Provider | ⏳ |
| 11.4 | Format-Chart | Sichtbar | Verteilung ASS/SRT/... | ⏳ |
| 11.5 | Leer-Zustand | 0 Downloads | Sinnvoller Hinweis | ⏳ |

---

## BEREICH 12 — Tasks (`/tasks`)

| # | Test | Schritte | Erwartetes Ergebnis | Status |
|---|------|----------|---------------------|--------|
| 12.1 | Seite laden | Aufrufen | Task-Liste erscheint | ⏳ |
| 12.2 | Laufende Tasks | Sichtbar | Status-Badges korrekt | ⏳ |
| 12.3 | Task abbrechen | Abbrechen-Button | Task gestoppt, Status aktualisiert | ⏳ |
| 12.4 | Task-Details | Zeile ausklappen | Detailinfos sichtbar | ⏳ |

---

## BEREICH 13 — Logs (`/logs`)

| # | Test | Schritte | Erwartetes Ergebnis | Status |
|---|------|----------|---------------------|--------|
| 13.1 | Seite laden | Aufrufen | Log-Ausgabe erscheint | ⏳ |
| 13.2 | Level-Filter | Dropdown | Filtert nach DEBUG/INFO/WARN/ERROR | ⏳ |
| 13.3 | Suche in Logs | Textfeld | Logs nach Begriff filtern | ⏳ |
| 13.4 | Live-Updates | Warten | Neue Log-Einträge erscheinen (WebSocket) | ⏳ |
| 13.5 | Logs herunterladen | Button (falls vorhanden) | Log-Datei wird heruntergeladen | ⏳ |

---

## BEREICH 14 — Plugins (`/plugins`)

| # | Test | Schritte | Erwartetes Ergebnis | Status |
|---|------|----------|---------------------|--------|
| 14.1 | Marketplace laden | Aufrufen | Plugin-Liste erscheint | ⏳ |
| 14.2 | Plugin installieren | Install-Button | Installiert, Status wechselt | ⏳ |
| 14.3 | Plugin deinstallieren | Uninstall-Button | Entfernt | ⏳ |
| 14.4 | Installierte Plugins | Tab | Nur installierte sichtbar | ⏳ |

---

## BEREICH 15 — Auth & Onboarding

### 15.1 Login

| # | Test | Schritte | Erwartetes Ergebnis | Status |
|---|------|----------|---------------------|--------|
| 15.1.1 | Login-Seite | `/login` aufrufen | Passwort-Feld + Login-Button | ⏳ |
| 15.1.2 | Falsches Passwort | Falsches PW eingeben | Fehlermeldung erscheint | ⏳ |
| 15.1.3 | Passwort anzeigen | Eye-Icon | Passwort sichtbar/verborgen | ⏳ |
| 15.1.4 | Korrektes Login | Richtiges PW | Weitergeleitet zu Dashboard | ⏳ |
| 15.1.5 | Auth-Redirect | `/library` ohne Login | Redirect zu `/login` | ⏳ |

### 15.2 Onboarding-Wizard

| # | Test | Schritte | Erwartetes Ergebnis | Status |
|---|------|----------|---------------------|--------|
| 15.2.1 | Fortschrittsbalken | Jeden Schritt | Fortschritt korrekt angezeigt | ⏳ |
| 15.2.2 | Modus wählen | Sonarr/Standalone | Richtige Felder für Modus | ⏳ |
| 15.2.3 | Zurück/Weiter | Buttons | Navigation funktioniert | ⏳ |
| 15.2.4 | Verbindung testen | Test-Button | Verbindung OK oder Fehler | ⏳ |
| 15.2.5 | Wizard abschließen | "Fertig" klicken | Bibliothek-Scan startet | ⏳ |

---

## BEREICH 16 — WebSocket & Live-Updates

| # | Test | Schritte | Erwartetes Ergebnis | Status |
|---|------|----------|---------------------|--------|
| 16.1 | WebSocket verbunden | DevTools → Network → WS | Verbindung zu `/socket.io` offen | ⏳ |
| 16.2 | Job-Status live | Suchauftrag starten | Activity/Queue aktualisiert ohne Reload | ⏳ |
| 16.3 | Toast bei Job-Abschluss | Job abwarten | Toast-Benachrichtigung erscheint | ⏳ |
| 16.4 | Extraktion live | Embedded extrahieren | Progress-Banner aktualisiert in Echtzeit | ⏳ |
| 16.5 | Reconnect | Server kurz stoppen/starten | Verbindung wird automatisch neu aufgebaut | ⏳ |

---

## BEREICH 17 — Globale UX & Konsistenz 💅

### 17.1 Toast-Benachrichtigungen

| # | Test | Prüfen | Erwartetes Ergebnis | Status |
|---|------|--------|---------------------|--------|
| 17.1.1 | Erfolg-Toast | Nach Speichern | Grüner Toast mit Meldung | ⏳ |
| 17.1.2 | Fehler-Toast | Bei Fehler | Roter Toast mit Fehlermeldung | ⏳ |
| 17.1.3 | Toast verschwindet | Warten | Toast verschwindet automatisch | ⏳ |

### 17.2 Leer-Zustände

| # | Test | Prüfen | Erwartetes Ergebnis | Status |
|---|------|--------|---------------------|--------|
| 17.2.1 | Library leer | 0 Serien | Sinnvoller Call-to-Action | ⏳ |
| 17.2.2 | Wanted leer | 0 Items | Sinnvoller Hinweis | ⏳ |
| 17.2.3 | History leer | 0 Downloads | Sinnvoller Hinweis | ⏳ |
| 17.2.4 | Blacklist leer | 0 Items | Sinnvoller Hinweis | ⏳ |

### 17.3 Fehlerbehandlung

| # | Test | Prüfen | Erwartetes Ergebnis | Status |
|---|------|--------|---------------------|--------|
| 17.3.1 | API-Fehler | Backend-Fehler provozieren | UI zeigt Fehlermeldung, kein Absturz | ⏳ |
| 17.3.2 | Netzwerk-Fehler | Offline-Modus simulieren | Graceful Degradation / Fehlermeldung | ⏳ |

### 17.4 Responsive Design

| # | Test | Viewport | Erwartetes Ergebnis | Status |
|---|------|----------|---------------------|--------|
| 17.4.1 | Desktop | 1920×1080 | Vollständiges Layout | ⏳ |
| 17.4.2 | Laptop | 1280×800 | Kein Overflow | ⏳ |
| 17.4.3 | Tablet | 768px | Angepasstes Layout | ⏳ |
| 17.4.4 | Mobile | 375px | Bottom-Nav, kompaktes Layout | ⏳ |

### 17.5 Performance 💅

| # | Test | Prüfen | Erwartetes Ergebnis | Status |
|---|------|--------|---------------------|--------|
| 17.5.1 | Ladezeiten | Network-Tab | Hauptseiten < 1s (nach erstem Load) | ⏳ |
| 17.5.2 | Virtual Scroll | Große Listen (100+ Items) | Kein Ruckeln, keine DOM-Explosion | ⏳ |
| 17.5.3 | Modal-Öffnen | Alle Modals | Öffnet sofort, kein Flackern | ⏳ |

---

## BEKANNTE LÜCKEN — Verifikation (aus Gap-Analysen)

> Diese Tests prüfen ob bekannte Gaps aus UI_GAP_ANALYSIS.md bestehen bleiben oder behoben wurden.

| # | Gap (A/B Nr.) | Erwarteter Zustand | Status |
|---|--------------|---------------------|--------|
| G.1 | A1: Re-scan Series | "Coming soon" Toast oder funktional | ⏳ |
| G.2 | A1: Movie Detail Page | Film anklickbar → Detail-Seite | ⏳ |
| G.3 | A2: Sprachprofil-Verwaltungsseite | Seite existiert oder fehlt | ⏳ |
| G.4 | A3: Glossar Add/Edit/Delete | Buttons vorhanden | ⏳ |
| G.5 | A5: Benachrichtigungsverlauf | Tab/Seite vorhanden | ⏳ |
| G.6 | A8: Config Export/Import | Buttons in System-Settings | ⏳ |
| G.7 | A8: Backup-Liste & Restore | UI vorhanden | ⏳ |
| G.8 | A8: DB-Vacuum | Button in System | ⏳ |
| G.9 | A8: Update-Check | Sichtbar in UI | ⏳ |
| G.10 | B6: Einstellungen Export/Import | Vorhanden | ⏳ |

---

## Findings-Dokument

Alle gefundenen Probleme werden in **[FINDINGS.md](FINDINGS.md)** dokumentiert:

```
## FINDING-XXX — [Titel]

**Bereich:** [Settings / Library / Dashboard / ...]
**Schwere:** Kritisch / Hoch / Mittel / Niedrig / UX
**Typ:** Funktionsfehler / Broken-Key / Fehlende Funktion / UX-Problem / Design
**Testfall:** [Ref. aus diesem Plan, z.B. 10.2.1]

### Beschreibung
[Was passiert tatsächlich?]

### Erwartetes Verhalten
[Was sollte passieren?]

### Reproduktion
1. Schritt 1
2. Schritt 2
3. ...

### Beleg
[Screenshot-Datei / Netzwerk-Request / Fehlermeldung]

### Ursache (wenn bekannt)
[Bekannter Bug aus Gap-Analyse / Vermutung]
```

---

*Testplan erstellt: 2026-03-22 | Basis: UI_FUNCTIONS.md (100+ Elemente) + UI_GAP_ANALYSIS.md + SETTINGS_GAP_ANALYSIS.md*
