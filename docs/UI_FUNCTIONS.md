# Sublarr — UI Functions Inventory

Vollständige Liste aller UI-Funktionen, Buttons, Eingabefelder und Anzeigeelemente.

---

## Navigation

### Sidebar (Desktop)
- **Dashboard** Link → `/`
- **Library** Link → `/library`
- **Wanted** Link → `/wanted`
- **Activity** Link → `/activity`
- **Queue** Link → `/queue`
- **History** Link → `/history`
- **Blacklist** Link → `/blacklist`
- **Settings** Link → `/settings`
- **Statistics** Link → `/statistics`
- **Tasks** Link → `/tasks`
- **Logs** Link → `/logs`
- **Plugins** Link → `/plugins`
- **GlobalSearch** Button (Cmd+K / Ctrl+K) → öffnet GlobalSearchModal
- **ThemeToggle** Button → Dark/Light Mode umschalten

### Bottom Navigation (Mobile)
- Dieselben Links wie Sidebar, icons-only

---

## Login (`/login`)

| Element | Typ | Funktion |
|---------|-----|----------|
| Passwort-Eingabe | Password-Input | Passwort eingeben |
| Passwort anzeigen | Toggle (Eye/EyeOff) | Passwort sichtbar/unsichtbar |
| Log In | Button (Primary) | Anmeldung absenden |
| Fehlermeldung | Anzeige | Falsches Passwort anzeigen |

---

## Onboarding-Wizard (`/onboarding`)

| Element | Typ | Funktion |
|---------|-----|----------|
| Fortschrittsbalken | Anzeige | Aktueller Schritt von Gesamt |
| Schritt-Indikator | Anzeige | Icon + Titel + Beschreibung |
| Schritt X von Y | Anzeige | Fortschrittstext |
| Zurück | Button | Vorherigen Schritt |
| Weiter / Fertig | Button (Primary) | Nächsten Schritt / Abschluss |

### Schritt 1 — Modus
- **Sonarr/Radarr-Modus** Radio → integrierter Modus
- **Standalone-Modus** Radio → eigenständiger Ordner-Modus

### Schritt 2 — Sonarr/Radarr
- **Sonarr URL** Text-Input
- **Sonarr API Key** Text-Input
- **Radarr URL** Text-Input
- **Radarr API Key** Text-Input
- **Verbindung testen** Button

### Schritt 3 — Standalone-Ordner
- **Ordner hinzufügen** Button
- **Ordnerpfad** Text-Input (pro Eintrag)
- **Eintrag entfernen** Button (pro Eintrag)

### Schritt 4 — Pfad-Mapping
- **Mapping hinzufügen** Button
- **Lokaler Pfad** Text-Input (pro Mapping)
- **Remote-Pfad** Text-Input (pro Mapping)
- **Mapping entfernen** Button (pro Mapping)

### Schritt 5 — Sprachen
- **Quellsprache** Dropdown
- **Zielsprache** Dropdown
- **Hörgeschädigt-Präferenz** Dropdown
- **Forced-Untertitel-Präferenz** Dropdown

### Schritt 6 — Provider
- **Provider aktivieren/deaktivieren** Toggle (pro Provider)
- **API Key** Input (pro Provider, wenn nötig)

### Schritt 7 — Automation
- **Automation aktivieren** Toggle
- **Suchintervall (Stunden)** Zahl-Input
- **Upgrade aktivieren** Toggle

### Schritt 8 — Ollama / Translation
- **Ollama URL** Text-Input
- **Ollama-Modell** Dropdown / Text-Input
- **Verbindung testen** Button

### Schritt 9 — Media Server
- **Server hinzufügen** Button
- **Server-Typ** Dropdown (pro Eintrag)
- **Konfigurations-Felder** (dynamisch je Typ)
- **Passwort anzeigen** Toggle
- **Verbindung testen** Button (pro Eintrag)
- **Server entfernen** Button (pro Eintrag)

### Schritt 10 — Abschluss / Scan
- **Bibliothek scannen** Button (Primary)

---

## Dashboard (`/`)

| Element | Typ | Funktion |
|---------|-----|----------|
| Widget-Layout | Anzeige | Konfigurierbare Widget-Kacheln |
| Widgets anpassen | Button (Settings-Icon) | WidgetSettingsModal öffnen |
| AutomationBanner | Anzeige | Status der Automation |
| HeroStats | Anzeige | Schlüsselkennzahlen (Gesamtserien, Gesamtfilme, fehlende Untertitel, etc.) |

### Widgets (individuell ein-/ausblendbar)
| Widget | Anzeige |
|--------|---------|
| StatCardsWidget | Kernzahlen (Serien, Filme, fehlend, ...) |
| WantedSummaryWidget | Wanted-Status-Übersicht |
| RecentActivityWidget | Letzte abgeschlossene Jobs |
| AutomationWidget | Automations-Zeitplan und -Status |
| ProviderHealthWidget | Verfügbarkeit der Subtitle-Provider |
| ServiceStatusWidget | Sonarr/Radarr/Ollama Verbindungsstatus |
| DiskSpaceWidget | Festplattennutzung |
| QualityWidget | Durchschnittliche Untertitelqualität |
| TranslationStatsWidget | Übersetzungsstatistiken |
| NeedsAttentionCard | Serien/Episoden mit Problemen |
| QuickActionsWidget | Schnellzugriff auf häufige Aktionen |

### WidgetSettingsModal
- **Widget ein-/ausblenden** Toggle (pro Widget)
- **Schließen** Button (X)

---

## Bibliothek (`/library`)

### Steuerelemente
| Element | Typ | Funktion |
|---------|-----|----------|
| Suche | Text-Input (mit Such-Icon) | Serien/Filme filtern |
| Series / Movies | Tabs | Zwischen Serien und Filmen wechseln |
| Profil-Filter | Dropdown | Nach Sprachprofil filtern |
| Filter-Preset-Menü | Dropdown | Gespeicherte Filter laden/speichern |
| Tabellenansicht | Toggle-Button (Tabelle-Icon) | Tabellenansicht aktivieren |
| Rasteransicht | Toggle-Button (Raster-Icon) | Rasteransicht aktivieren |
| Bulk-Sync | Toggle-Button | Bulk-Sync-Panel ein-/ausblenden |

### Filter-Chips (nur Serien)
- **Alle** Chip
- **Fehlend** Chip
- **Niedriger Score** Chip
- **Anime** Chip
- **Vollständig** Chip

### Bulk-Sync-Panel
| Element | Typ | Funktion |
|---------|-----|----------|
| Bereich | Dropdown | "Gesamte Bibliothek" / "Einzelne Serie" |
| Serien-Auswahl | Dropdown | Serie auswählen (bei Einzelserie) |
| Engine-Override | Dropdown | Default / alass / ffsubsync |
| Bulk-Sync starten | Button (Primary) | Sync-Prozess starten |
| Fortschrittsbalken | Anzeige | Aktueller Fortschritt |
| Statistiken | Anzeige | Aktuell/Gesamt, Synchronisiert, Fehlgeschlagen, % |
| Aktuelle Datei | Anzeige | Pfad der aktuell verarbeiteten Datei |

### Mehrfachauswahl (Tabellenansicht)
| Element | Typ | Funktion |
|---------|-----|----------|
| Checkboxen | Checkbox (pro Zeile) | Serien einzeln auswählen |
| "X Serien ausgewählt" | Infoleiste | Auswahlstatus |
| Alle Fehlenden suchen | Button | Für alle ausgewählten Serien suchen |
| Auswahl aufheben | Button | Selektion zurücksetzen |

### Rasteransicht
- **LibraryCard** (pro Serie/Film): Poster, Titel, fehlende Untertitel-Badge → Klick → Detail-Seite

### Tabellenansicht (VirtualLibraryTable)
| Spalte | Inhalt |
|--------|--------|
| Checkbox | Mehrfachauswahl |
| Titel | Serienname + Jahr |
| Fehlend | Anzahl fehlender Untertitel |
| Episoden | Gesamte Episodenanzahl |
| Profil | Zugeordnetes Sprachprofil |

### Pagination
- **Zurück** Button
- **Weiter** Button
- **Seitenzahlen** (Smart Pagination mit „...")
- **X–Y von Z** Anzeige

---

## Seriendetail (`/library/series/:id`)

### Header
| Element | Typ | Funktion |
|---------|-----|----------|
| Breadcrumb | Navigation | Library > Serientitel |

### SeriesHero
| Element | Typ | Funktion |
|---------|-----|----------|
| Serientitel | Anzeige | Titel der Serie |
| Cover-Art | Bild | Serienbild |
| Metadaten | Anzeige | Jahr, Episodenanzahl, Status, etc. |
| Re-scan Series | Button | Bibliothek re-scannen ⚠️ **coming soon** |
| Einstellungen öffnen | Button | SeriesSettingsPanel ein-/ausblenden |
| Glossar öffnen | Button | GlossaryPanel ein-/ausblenden |

### SeriesSettingsPanel
| Element | Typ | Funktion |
|---------|-----|----------|
| Sprachprofil | Dropdown | Sprachprofil für Serie setzen |
| Untertitelformat | Dropdown | Bevorzugtes Format (ASS, SRT, ...) |
| Hörgeschädigt | Toggle | HI-Untertitel bevorzugen |
| Forced | Toggle | Forced-Untertitel bevorzugen |
| Fansub-Override | Button | FansubOverrideModal öffnen |
| Eingebettete extrahieren | Button | Embedded Tracks extrahieren |
| Health-Check | Button | HealthCheckPanel öffnen |
| Cleanup | Button | SubtitleCleanupModal öffnen |

### GlossaryPanel
| Element | Typ | Funktion |
|---------|-----|----------|
| Suche | Text-Input | Glossar-Einträge filtern |
| Eintrags-Liste | Anzeige | Fansub-Begriffe und Definitionen |

### Staffel-Navigation
| Element | Typ | Funktion |
|---------|-----|----------|
| Staffel-Tabs | Tabs (S1, S2, ...) | Zwischen Staffeln wechseln |
| Staffel-Zusammenfassung | Anzeige | Episodenanzahl, Fehlend, Niedriger Score |

### Episodenliste (pro Episode)
| Element | Typ | Funktion |
|---------|-----|----------|
| Episodennummer & Titel | Anzeige | EP-Nr. + Titel |
| Untertitel-Status-Badges | Badges | Verfügbare Sprachen + Qualitäts-Score |
| Aktionsmenü | Dropdown-Button | Alle Episodenaktionen |
| Suchbereich | Expandierbarer Bereich | Suchergebnisse anzeigen |
| Verlaufsbereich | Expandierbarer Bereich | Download-Verlauf anzeigen |
| Tracks-Bereich | Expandierbarer Bereich | Eingebettete Tracks anzeigen |

### Episoden-Aktionsmenü (pro Episode)
| Aktion | Funktion |
|--------|----------|
| Suchen | Automatische Untertitelsuche starten |
| Interaktive Suche | InteractiveSearchModal öffnen |
| Bearbeiten | SubtitleEditorModal öffnen |
| Vorschau | Untertitel-Vorschau anzeigen |
| Vergleich | SubtitleComparison öffnen |
| Synchronisieren | SyncControls öffnen |
| Übersetzen / Neu-übersetzen | Übersetzungsjob starten |
| Als Sidecar extrahieren | Eingebetteten Track extrahieren |
| Löschen | Untertitel-Datei löschen (mit Bestätigung) |
| Zur Blacklist hinzufügen | Untertitel blockieren |

### Lösch-Dialog
| Element | Typ | Funktion |
|---------|-----|----------|
| Dateipfad | Anzeige | Zu löschende Datei |
| Zur Blacklist hinzufügen | Checkbox | Gleichzeitig blockieren |
| Abbrechen | Button | Dialog schließen |
| Löschen | Button (Danger) | Datei löschen |

### Extraktions-Fortschrittsbanner
| Element | Typ | Funktion |
|---------|-----|----------|
| Spinner + Text | Anzeige | "Extracting Tracks — X / Y Episodes" |
| Aktuelle Datei | Anzeige | Pfad der aktuellen Episode |
| Fortschrittsbalken | Anzeige | Prozentualer Fortschritt |

---

## Wanted (`/wanted`)

### Zusammenfassungs-Kacheln
| Kachel | Anzeige |
|--------|---------|
| Wanted | Anzahl ausstehender Elemente |
| Extracted | Anzahl extrahierter Elemente |
| Failed | Anzahl fehlgeschlagener Versuche |
| Ignored | Anzahl ignorierter Elemente |

### Filterleiste
| Element | Typ | Funktion |
|---------|-----|----------|
| Status | Dropdown | Wanted / Ignored / Failed / Found |
| Typ | Dropdown | Episode / Movie |
| Untertiteltyp | Dropdown | Full / Forced |
| Titel | Text-Input | Freitextsuche |
| Sortierfeld | Dropdown | Added at / Title / Last search at / Score / Search count |
| Sortierrichtung | Toggle | Auf-/Absteigend |

### Tabelle (VirtualWantedTable)
| Spalte | Inhalt |
|--------|--------|
| Checkbox | Mehrfachauswahl |
| Titel/Episode | Serienname + EP-Info |
| Status | Status-Badge |
| Sprache | Zielsprache |
| Format | Untertitelformat |
| Score | Qualitäts-Score |
| Letzte Suche | Datum/Zeit |
| Aktionen | Aktionsbuttons |

### Zeilen-Aktionsbuttons (pro Element)
| Aktion | Funktion |
|--------|----------|
| Suchen | Automatische Suche starten |
| Interaktive Suche | Manuellen Suche-Dialog öffnen |
| Verarbeiten/Herunterladen | Bestes Suchergebnis herunterladen |
| Blacklisten | Element blockieren |
| Neu-übersetzen | Übersetzungsjob erneut starten |
| Eingebettet extrahieren | Eingebetteten Track extrahieren |

### Erweiterte Zeile — Suchergebnisse
| Spalte | Inhalt |
|--------|--------|
| Provider | Quellanbieter |
| Typ | Target / Source |
| Format | ASS / SRT / ... |
| Score | Qualitätsbewertung |
| Release | Release-Name |
| Sprache | Sprache |
| Blacklist | Ban-Button (pro Ergebnis) |

### Batch-Aktionsleiste (bei Auswahl)
| Element | Typ | Funktion |
|---------|-----|----------|
| "X Elemente ausgewählt" | Anzeige | Auswahlstatus |
| Alle suchen | Button | Batch-Suche starten |
| Alle herunterladen | Button | Batch-Download starten |
| Auswahl aufheben | Button | Selektion zurücksetzen |

---

## Activity / Jobs (`/activity`)

### Filter-Tabs
- **Alle** Tab
- **Abgeschlossen** Tab
- **Fehlgeschlagen** Tab
- **Läuft** Tab
- **In Warteschlange** Tab

### Tabelle
| Spalte | Inhalt |
|--------|--------|
| Inhalt | Serientitel + EP-Info |
| Status | Status-Badge |
| Sprache | Zielsprache |
| Zeit | Abschluss-Zeitstempel |
| Fehler | Fehlermeldung (bei Failed) |
| Aktionen | Aktionsbuttons |

### Erweiterte Zeile (Details)
| Element | Anzeige |
|---------|---------|
| Vollständiger Pfad | Quelldatei |
| Ausgabepfad | Untertiteldatei |
| Übersetzungsqualität | Qualitätsbalken |
| Quelle | Provider-Name |
| Backend | Übersetzungs-Backend |
| Übersetzte Zeilen | Anzahl |
| Format | Untertitelformat |
| Force-Flag | Ja/Nein |
| Erstellt am | Zeitstempel |
| Abgeschlossen am | Zeitstempel |
| Fehlerdetails | Fehlermeldung (bei Failed) |

### Zeilenaktionen
| Aktion | Funktion |
|--------|----------|
| Erneut versuchen | Fehlgeschlagenen Job neu starten (nur bei Failed) |

### Pagination
- **Zurück** Button
- **Weiter** Button
- **Seiteninformation** Anzeige

---

## Queue (`/queue`)

### Batch-Verarbeitungs-Status
| Element | Typ | Funktion |
|---------|-----|----------|
| Fortschrittsbalken | Anzeige | Fortschritt der Batch-Verarbeitung |
| Statistiken | Anzeige | Total, Verarbeitet, Erfolgreich, Fehlgeschlagen, Übersprungen |
| Aktuelle Datei | Anzeige | Aktuell verarbeiteter Pfad |

### Wanted-Batch-Such-Status
| Element | Typ | Funktion |
|---------|-----|----------|
| Fortschrittsbalken | Anzeige | Suchfortschritt |
| Statistiken | Anzeige | Total, Verarbeitet, Gefunden, Fehlgeschlagen, Übersprungen |
| Aktuelles Element | Anzeige | Aktuell gesuchtes Element |

### Batch-Probe-Status
| Element | Typ | Funktion |
|---------|-----|----------|
| Fortschrittsbalken | Anzeige | Probe-Fortschritt |
| Statistiken | Anzeige | Total, Gefunden, Extrahiert, Fehlgeschlagen |
| Aktuelles Element | Anzeige | Aktuell verarbeitetes Element |

### Scanner-Status
| Element | Typ | Funktion |
|---------|-----|----------|
| Fortschrittsbalken | Anzeige | Scanner-Fortschritt |
| Phasenindikator | Anzeige | Aktuelle Scan-Phase |
| Statistiken | Anzeige | Fortschritt, Hinzugefügt, Aktualisiert |

### Aktive Jobs
| Element | Typ | Funktion |
|---------|-----|----------|
| Job-Liste | Anzeige | Laufende Jobs mit Status-Badge |
| Leer-Zustand | Anzeige | "Keine aktiven Jobs" |

### Jobs in Warteschlange
| Element | Typ | Funktion |
|---------|-----|----------|
| Queue-Liste | Anzeige | Wartende Jobs |
| Leer-Zustand | Anzeige | "Keine Jobs in Warteschlange" |

---

## Verlauf (`/history`)

### Zusammenfassungs-Kachel
- **Gesamt-Downloads** Anzeige

### Filterleiste
| Element | Typ | Funktion |
|---------|-----|----------|
| Provider | Dropdown | AnimeTosho / Jimaku / OpenSubtitles / SubDL / ... |
| Format | Dropdown | ASS / SRT / ... |
| Sprache | Text-Input | Sprachsuche |
| Dateipfad | Text-Input | Pfadsuche |

### Tabelle
| Spalte | Inhalt |
|--------|--------|
| Checkbox | Mehrfachauswahl |
| Titel/Episode | Serienname + EP-Info |
| Provider | Quellanbieter |
| Sprache | Untertitelsprache |
| Format | Dateiformat |
| Score | Qualitäts-Score |
| Download-Zeit | Datum/Zeit |
| Aktionen | Aktionsbuttons |

### Zeilenaktionen
| Aktion | Funktion |
|--------|----------|
| Vorschau | Untertitel in Viewer öffnen (Eye-Icon) |
| Diff | Vergleich mit aktueller Datei (GitCompare-Icon) |
| Blacklisten | Eintrag blockieren (Ban-Icon) |

### Batch-Aktionsleiste (bei Auswahl)
- Wie in Wanted (Alle auswählen, BatchActionBar)

### Pagination
- **Zurück** / **Weiter** Buttons + Seitenanzeige

---

## Blacklist (`/blacklist`)

### Header
| Element | Typ | Funktion |
|---------|-----|----------|
| Gesamtanzahl | Anzeige | "X blockierte Untertitel" |
| Alle löschen | Button (Danger) | Bestätigungs-Dialog + alle Einträge entfernen |

### Zusammenfassungs-Kachel
- **Gesamt blockiert** Anzeige

### Tabelle
| Spalte | Inhalt |
|--------|--------|
| Provider | Quellanbieter |
| Untertitel-ID | Interne ID |
| Sprache | Sprache |
| Titel/Pfad | Serientitel oder Dateipfad |
| Grund | Blockierungsgrund |
| Hinzugefügt | Datum |
| Aktionen | Entfernen-Button |

### Zeilenaktionen
| Aktion | Funktion |
|--------|----------|
| Entfernen | Blacklist-Eintrag löschen (Trash-Icon) |

### Bestätigungs-Dialog ("Alle löschen")
| Element | Typ | Funktion |
|---------|-----|----------|
| Bestätigungstext | Anzeige | "Alle Blacklist-Einträge löschen?" |
| Abbrechen | Button | Dialog schließen |
| Bestätigen | Button (Danger) | Alle Einträge löschen |

### Pagination
- **Zurück** / **Weiter** Buttons + Seitenanzeige

---

## Einstellungen (`/settings`)

### Übersicht
| Element | Typ | Funktion |
|---------|-----|----------|
| Einstellungssuche | Text-Input | Einstellungen durchsuchen |
| Kategorie-Kacheln | Links | Zu Kategorie-Seiten navigieren |

### Allgemein (`/settings/general`)
| Element | Typ | Funktion |
|---------|-----|----------|
| Quellsprache | Text-Input | Standardquellsprache |
| Zielsprache | Text-Input | Standardzielsprache |
| Hörgeschädigt-Präferenz | Dropdown | HI-Untertitel Einstellung |
| Forced-Präferenz | Dropdown | Forced-Untertitel Einstellung |
| Log-Level | Dropdown | DEBUG / INFO / WARNING / ERROR |
| Erweiterte Optionen | Bereich | Weitere Felder |

### Verbindungen (`/settings/connections`)
| Element | Typ | Funktion |
|---------|-----|----------|
| Sonarr URL | Text-Input | Sonarr-Instanz URL |
| Sonarr API Key | Text-Input | Sonarr API-Schlüssel |
| Sonarr testen | Button | Verbindung testen |
| Radarr URL | Text-Input | Radarr-Instanz URL |
| Radarr API Key | Text-Input | Radarr API-Schlüssel |
| Radarr testen | Button | Verbindung testen |
| Pfad-Mapping hinzufügen | Button | Neues Mapping anlegen |
| Lokaler Pfad | Text-Input (pro Mapping) | Lokaler Pfad |
| Remote-Pfad | Text-Input (pro Mapping) | Remote-Pfad |
| Mapping entfernen | Button (pro Mapping) | Mapping löschen |

### Untertitel (`/settings/subtitles`)
| Element | Typ | Funktion |
|---------|-----|----------|
| Bevorzugtes Format | Dropdown | ASS / SRT / VTT / ... |
| Extraktions-Einstellungen | Bereich | Optionen für eingebettete Extraktion |
| Qualitätsschwellenwert | Zahl-Input | Mindest-Score für "niedrig" |
| Health-Check-Konfiguration | Bereich | Health-Check-Parameter |

### Provider (`/settings/providers`)
| Element | Typ | Funktion |
|---------|-----|----------|
| Provider-Kacheln | Drag & Drop | Provider-Priorität festlegen |
| Enable/Disable Toggle | Toggle (pro Provider) | Provider aktivieren/deaktivieren |
| Cache leeren | Button (pro Provider) | Provider-Cache löschen |
| Alle Caches leeren | Button | Alle Provider-Caches löschen |
| Marketplace durchsuchen | Bereich | Plugins installieren/deinstallieren |
| Anti-Captcha Backend | Dropdown | Disabled / Anti-Captcha.com / CapMonster |
| Anti-Captcha API Key | Password-Input | API-Schlüssel |

### Automation (`/settings/automation`)
| Element | Typ | Funktion |
|---------|-----|----------|
| Automation aktiviert | Toggle | Globale Automation ein/aus |
| Suchintervall | Zahl-Input | Stunden zwischen automatischen Suchen |
| Upgrade aktiviert | Toggle | Bestehende Untertitel upgraden |
| Ruhezeiten | Bereich | Zeitraum ohne Automation |
| Benachrichtigungs-Templates | Text-Inputs | Eigene Benachrichtigungstexte |

### Übersetzung (`/settings/translation`)
| Element | Typ | Funktion |
|---------|-----|----------|
| Ollama URL | Text-Input | Ollama-Instanz URL |
| Ollama-Modell | Dropdown / Text-Input | Modell auswählen |
| Verbindung testen | Button | Ollama-Verbindung testen |
| Whisper-Konfiguration | Bereich | STT-Einstellungen |
| Übersetzungs-Backend | Dropdown | Backend-Auswahl |

### Benachrichtigungen (`/settings/notifications`)
| Element | Typ | Funktion |
|---------|-----|----------|
| E-Mail-Setup | Bereich | SMTP-Konfiguration |
| Webhook-Setup | Bereich | Webhook-URL und Header |
| Template-Editor | Text-Area | Benachrichtigungsvorlage |
| Vorschau | Button | Template-Vorschau anzeigen |
| Ruhezeiten | Bereich | Zeitraum ohne Benachrichtigungen |

### System (`/settings/system`)
| Element | Typ | Funktion |
|---------|-----|----------|
| Datenbankinfo | Anzeige | DB-Größe, Pfad, Version |
| Backup erstellen | Button | Datenbank sichern |
| Backup wiederherstellen | Button + File-Input | Backup laden |
| Health-Check | Bereich | Systemgesundheits-Panel |
| Service-Status | Anzeige | Sonarr/Radarr/Ollama Status |
| Logs herunterladen | Button | Log-Datei herunterladen |

---

## Statistiken (`/statistics`)

### Steuerelemente
| Element | Typ | Funktion |
|---------|-----|----------|
| Zeitraum | Filter (7d / 30d / 90d / 365d) | Zeitraum auswählen |
| Exportieren | Dropdown (JSON / CSV) | Daten exportieren |

### Charts
| Chart | Anzeige |
|-------|---------|
| TranslationChart | Übersetzungsstatistiken |
| ProviderChart | Provider-Nutzungsverteilung |
| FormatChart | Untertitelformat-Verteilung |
| DownloadChart | Downloads über Zeit |
| QualityTrendChart | Qualitätsverlauf |
| ProviderSuccessChart | Provider-Erfolgsquote |

### Serien-Qualitätstabelle
| Spalte | Inhalt |
|--------|--------|
| Serie | Serienname |
| Formate | Verwendete Formate |
| Qualität | Score-Balken (grün/gelb/rot) |
| Downloads | Gesamtanzahl |
| Letzter Download | Datum |
| Sortieren nach | Avg. Qualität / Downloads |

---

## Tasks (`/tasks`)

### Task-Kacheln (pro Task)
| Element | Typ | Funktion |
|---------|-----|----------|
| Status-Indikator | Animierter Punkt | Grün = läuft |
| Task-Name | Anzeige | Display-Name des Tasks |
| Status-Badge | Badge | Running / Idle / Disabled |
| Abbrechen | Button | Laufenden Task stoppen (wenn abbrechbar) |
| Jetzt ausführen | Button | Task manuell starten |
| Letzter Lauf | Anzeige | Datum/Zeit |
| Nächster Lauf | Anzeige | Datum/Zeit |
| Intervall | Anzeige | "Alle X Stunden" |
| Fortschrittsbalken | Anzeige | Fortschritt (wenn vorhanden) |

---

## Logs (`/logs`)

### Steuerelemente
| Element | Typ | Funktion |
|---------|-----|----------|
| Level-Filter | Tabs (ALL / DEBUG / INFO / WARNING / ERROR) | Log-Level filtern |
| Suche | Text-Input | Log-Einträge durchsuchen |
| Herunterladen | Button | Log-Datei herunterladen |
| Auto-Scroll | Toggle | Automatisch ans Ende scrollen |

### Log-Viewer
| Element | Typ | Funktion |
|---------|-----|----------|
| Log-Zeilen | Virtuelles Scroll-List | Log-Einträge mit Zeitstempel |
| Farbkodierung | Anzeige | ERROR=rot, WARNING=gelb, INFO=normal, DEBUG=gedimmt |

---

## Plugins (`/plugins`)

### Marketplace-Steuerelemente
| Element | Typ | Funktion |
|---------|-----|----------|
| Suche | Text-Input | Plugin-Suche |
| Kategorie | Filter | Alle / Provider / Translation / Tools |

### Plugin-Kacheln
| Element | Typ | Funktion |
|---------|-----|----------|
| Name | Anzeige | Plugin-Name + Package-Icon |
| Version | Anzeige | Versionsnummer |
| Bewertung | Anzeige | Sterne (wenn vorhanden) |
| Autor | Anzeige | Autorenname |
| Downloads | Anzeige | Download-Anzahl |
| Beschreibung | Anzeige | Plugin-Beschreibung |
| Installieren / Deinstallieren | Button | Plugin installieren/entfernen |
| GitHub öffnen | Link (ExternalLink-Icon) | GitHub-Repository öffnen |

---

## Globale / Geteilte Elemente

### GlobalSearchModal (Cmd+K)
| Element | Typ | Funktion |
|---------|-----|----------|
| Sucheingabe | Text-Input | Serien/Episoden/Einstellungen suchen |
| Suchergebnisse | Liste | Treffer anklicken → Navigation |

### Keyboard-Shortcuts-Modal
| Element | Typ | Funktion |
|---------|-----|----------|
| Shortcut-Liste | Anzeige | Alle verfügbaren Tastenkürzel |
| Schließen | Button | Modal schließen |

### Toast-Benachrichtigungen
| Typ | Funktion |
|-----|---------|
| Success (grün) | Erfolgreiche Aktionen |
| Error (rot) | Fehlgeschlagene Aktionen |
| Info (blau) | Informationen / Hinweise |
| Warning (gelb) | Warnungen |

### SubtitleEditorModal
| Element | Typ | Funktion |
|---------|-----|----------|
| Dateipfad | Anzeige | Pfad der Untertiteldatei |
| Vorschau-Modus | Tab | Read-only Vorschau |
| Bearbeiten-Modus | Tab | Bearbeitbarer Editor (CodeMirror) |
| Waveform-Tab | Tab | Audio-Waveform anzeigen |
| Rechtschreib-Tab | Tab | SpellCheckPanel |
| Speichern | Button (Primary) | Änderungen speichern |
| Schließen | Button | Modal schließen |

### SyncControls / SyncModal
| Element | Typ | Funktion |
|---------|-----|----------|
| Sync-Methode Tabs | Tabs | Offset / Geschwindigkeit / Framerate / Chapter / ffsubsync / alass |
| Offset-Eingabe | Zahl-Input | Zeitversatz in ms |
| Geschwindigkeit | Zahl-Input | Wiedergabegeschwindigkeit |
| Framerate | Dropdown | Framerate anpassen |
| Kapitel-Auswahl | Dropdown | Kapitel-basiertes Sync |
| Vorschau | Button | Sync-Vorschau anzeigen |
| Anwenden | Button (Primary) | Sync durchführen |
| Zurücksetzen | Button | Einstellungen zurücksetzen |

### InteractiveSearchModal
| Element | Typ | Funktion |
|---------|-----|----------|
| Sucheingabe | Text-Input | Manuelle Suchanfrage |
| Suchergebnisse | Tabelle | Ergebnisliste mit Provider, Format, Score |
| Herunterladen | Button (pro Ergebnis) | Ergebnis herunterladen |
| Blacklisten | Button (pro Ergebnis) | Ergebnis blockieren |
| Schließen | Button | Modal schließen |

### SubtitleComparison (Vergleich)
| Element | Typ | Funktion |
|---------|-----|----------|
| Datei-Auswahl Links | Dropdown | Erste Datei für Vergleich |
| Datei-Auswahl Rechts | Dropdown | Zweite Datei für Vergleich |
| Side-by-Side-Ansicht | Anzeige | Beide Untertitel nebeneinander |
| Diff-Hervorhebung | Anzeige | Unterschiede farblich markiert |
| Schließen | Button | Zurück |

### PlayerModal (Web-Player)
| Element | Typ | Funktion |
|---------|-----|----------|
| Video-Player | Anzeige | HTML5-Videowiedergabe |
| Untertitel-Track-Auswahl | Dropdown | Untertitelspur auswählen |
| Wiedergabe-Steuerung | Buttons | Play/Pause, Seek, Lautstärke |
| Schließen | Button | Modal schließen |

### HealthCheckPanel
| Element | Typ | Funktion |
|---------|-----|----------|
| Health-Status | Anzeige | Gesamtbewertung der Untertitelqualität |
| Probleme-Liste | Anzeige | Einzelne gefundene Probleme |
| Schließen | Button | Panel schließen |

### FansubOverrideModal
| Element | Typ | Funktion |
|---------|-----|----------|
| Fansub-Gruppen | Liste | Bevorzugte Gruppen |
| Gruppe hinzufügen | Button | Neue Gruppe eintragen |
| Gruppe entfernen | Button (pro Eintrag) | Gruppe entfernen |
| Speichern | Button (Primary) | Einstellungen speichern |
| Schließen | Button | Modal schließen |

### SubtitleCleanupModal
| Element | Typ | Funktion |
|---------|-----|----------|
| Sidecar-Dateien-Liste | Anzeige | Gefundene Duplikate/Altdateien |
| Auswahl | Checkboxen | Zu löschende Dateien markieren |
| Löschen | Button (Danger) | Ausgewählte Dateien löschen |
| Schließen | Button | Modal schließen |

### BatchActionBar
| Element | Typ | Funktion |
|---------|-----|----------|
| "X Elemente ausgewählt" | Anzeige | Auswahlstatus |
| Kontextabhängige Aktionen | Buttons | Je nach Seite unterschiedlich |
| Auswahl aufheben | Button | Selektion leeren |

---

## Ausstehend / Platzhalter ⚠️

| Funktion | Ort | Status |
|---------|-----|--------|
| Re-scan Series | SeriesDetail → SeriesHero | `toast('coming soon')` — nicht implementiert |

---

*Stand: 2026-03-21 — generiert aus vollständiger Frontend-Code-Analyse*
