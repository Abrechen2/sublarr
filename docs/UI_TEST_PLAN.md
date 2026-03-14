# Sublarr — UI Test Plan (Vollständig)

> Stand: 2026-03-14 | Version 0.29.0-beta
> Ziel: Alle UI-Funktionen manuell verifizierbar dokumentiert. Jede Funktion mit konkretem Test-Schritt und erwartetem Ergebnis.

---

## Legende

| Symbol | Bedeutung |
|--------|-----------|
| ✅ | Test bestanden |
| ❌ | Test fehlgeschlagen |
| ⏳ | Noch nicht getestet |
| 🔗 | API-Call wird ausgelöst |
| 🔌 | WebSocket-Event |
| 💾 | Daten werden gespeichert |
| 🗑️ | Daten werden gelöscht |

---

## 1. NAVIGATION & ROUTING

### 1.1 Sidebar-Navigation

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 1.1.1 | Dashboard-Link | Klick auf "Dashboard" in Sidebar | Navigiert zu `/`, URL ändert sich, Dashboard-Widgets laden | ⏳ |
| 1.1.2 | Library-Link | Klick auf "Library" | Navigiert zu `/library`, Serienraster erscheint | ⏳ |
| 1.1.3 | Wanted-Link | Klick auf "Wanted" | Navigiert zu `/wanted`, Tabelle erscheint | ⏳ |
| 1.1.4 | Activity-Link | Klick auf "Activity" | Navigiert zu `/activity`, Jobliste erscheint | ⏳ |
| 1.1.5 | History-Link | Klick auf "History" | Navigiert zu `/history`, Downloadverlauf erscheint | ⏳ |
| 1.1.6 | Blacklist-Link | Klick auf "Blacklist" | Navigiert zu `/blacklist`, Blacklist erscheint | ⏳ |
| 1.1.7 | Settings-Link | Klick auf "Settings" | Navigiert zu `/settings`, General-Tab aktiv | ⏳ |
| 1.1.8 | Statistics-Link | Klick auf "Statistics" | Navigiert zu `/statistics`, Charts laden | ⏳ |
| 1.1.9 | Tasks-Link | Klick auf "Tasks" | Navigiert zu `/tasks`, Taskliste erscheint | ⏳ |
| 1.1.10 | Logs-Link | Klick auf "Logs" | Navigiert zu `/logs`, Log-Output erscheint | ⏳ |
| 1.1.11 | Plugins-Link | Klick auf "Plugins" | Navigiert zu `/plugins`, Marketplace erscheint | ⏳ |
| 1.1.12 | Aktiver Link Highlight | Aktuelle Seite besuchen | Entsprechender Sidebar-Eintrag ist farblich hervorgehoben | ⏳ |
| 1.1.13 | Sidebar kollabieren | Klick auf Hamburger-/Chevron-Icon | Sidebar wird schmaler, nur Icons bleiben sichtbar | ⏳ |
| 1.1.14 | Sidebar expandieren | Klick auf Hamburger-/Chevron-Icon (wenn kollabiert) | Sidebar zeigt wieder Labels | ⏳ |

### 1.2 Theme & Sprache

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 1.2.1 | Dark Mode aktivieren | ThemeToggle-Button klicken | Gesamte UI wechselt zu dunklem Theme | ⏳ |
| 1.2.2 | Light Mode aktivieren | ThemeToggle erneut klicken | UI wechselt zu hellem Theme | ⏳ |
| 1.2.3 | Theme persistent | Theme wechseln, Seite neu laden | Theme bleibt erhalten (localStorage) | ⏳ |
| 1.2.4 | Sprache DE wählen | LanguageSwitcher → "DE" | UI-Labels wechseln auf Deutsch | ⏳ |
| 1.2.5 | Sprache EN wählen | LanguageSwitcher → "EN" | UI-Labels wechseln auf Englisch | ⏳ |
| 1.2.6 | Sprache persistent | Sprache wechseln, Seite neu laden | Sprache bleibt erhalten (localStorage) | ⏳ |

### 1.3 Keyboard Shortcuts

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 1.3.1 | Global Search öffnen | `Ctrl+K` drücken | GlobalSearchModal erscheint | ⏳ |
| 1.3.2 | Global Search schließen | `Escape` drücken | Modal verschwindet | ⏳ |
| 1.3.3 | Shortcuts-Hilfe öffnen | `?` drücken | KeyboardShortcutsModal erscheint | ⏳ |
| 1.3.4 | Shortcuts-Hilfe schließen | `Escape` oder X-Button | Modal schließt | ⏳ |

### 1.4 404 / Fehlerseiten

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 1.4.1 | 404-Seite | `/nicht-vorhanden` aufrufen | NotFound-Seite erscheint mit "Back"-Button | ⏳ |
| 1.4.2 | Back-Button auf 404 | "Back"-Button klicken | Navigiert zurück (Browser-History) | ⏳ |

---

## 2. DASHBOARD (`/`)

### 2.1 Widget-Anzeige

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 2.1.1 | StatCardsWidget laden | Dashboard aufrufen | Stat-Karten (Translated Today, Total, Failed) laden mit Zahlen | ⏳ |
| 2.1.2 | ProviderHealthWidget | Dashboard aufrufen | Provider-Status-Badges sichtbar (grün/rot/gelb) | ⏳ |
| 2.1.3 | ServiceStatusWidget | Dashboard aufrufen | Backend/Translator-Status-Indikatoren sichtbar | ⏳ |
| 2.1.4 | TranslationStatsWidget | Dashboard aufrufen | Tagesstatistik-Chart rendert (kein leeres div) | ⏳ |
| 2.1.5 | RecentActivityWidget | Dashboard aufrufen | Letzte Jobs werden aufgelistet | ⏳ |
| 2.1.6 | WantedSummaryWidget | Dashboard aufrufen | Wanted-Zähler sichtbar | ⏳ |
| 2.1.7 | DiskSpaceWidget | Dashboard aufrufen | Festplattennutzungs-Balken sichtbar | ⏳ |
| 2.1.8 | QualityWidget | Dashboard aufrufen | Qualitäts-Trend-Chart rendert | ⏳ |

### 2.2 Dashboard-Anpassung

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 2.2.1 | "Customize"-Button öffnet Modal | "Customize" klicken | WidgetSettingsModal erscheint mit Checkbox-Liste | ⏳ |
| 2.2.2 | Widget deaktivieren | Checkbox eines Widgets deaktivieren | Widget verschwindet aus dem Grid | ⏳ |
| 2.2.3 | Widget reaktivieren | Deaktiviertes Widget wieder aktivieren | Widget erscheint im Grid | ⏳ |
| 2.2.4 | Konfiguration persistent | Widgets deaktivieren, Seite neu laden | Konfiguration aus localStorage erhalten | ⏳ |
| 2.2.5 | Modal schließen | X-Button oder Escape | Modal schließt, Grid-Zustand bleibt | ⏳ |

---

## 3. LIBRARY (`/library`)

### 3.1 Grid-Ansicht

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 3.1.1 | Serien-Karten laden | Library aufrufen | LibraryGridCards mit Poster, Titel, fehlende Sub-Zähler | ⏳ |
| 3.1.2 | Karte anklicken | Auf Seriencard klicken | Navigation zu `/library/series/:id` | ⏳ |
| 3.1.3 | Fehlende Subs-Badge | Karte betrachten | Oranges Badge mit Anzahl fehlender Subs (wenn vorhanden) | ⏳ |
| 3.1.4 | Profil-Badge anzeigen | Karte betrachten | Zugewiesenes Sprachprofil wird angezeigt | ⏳ |

### 3.2 Ansicht wechseln

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 3.2.1 | Grid → Table wechseln | Table-Icon klicken | Ansicht wechselt zu VirtualLibraryTable | ⏳ |
| 3.2.2 | Table → Grid wechseln | Grid-Icon klicken | Ansicht wechselt zurück zu Karten | ⏳ |
| 3.2.3 | Ansicht persistent | Wechseln, Seite neu laden | Letzte Ansicht wird gespeichert | ⏳ |

### 3.3 Pagination

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 3.3.1 | Nächste Seite | "Weiter"-Pfeil klicken | 🔗 `getLibrary(page+1)` wird aufgerufen, neue Serien erscheinen | ⏳ |
| 3.3.2 | Vorherige Seite | "Zurück"-Pfeil klicken | 🔗 `getLibrary(page-1)` wird aufgerufen | ⏳ |
| 3.3.3 | Seitenzahl direkt wählen | Seitenzahl-Button klicken | 🔗 Entsprechende Seite wird geladen | ⏳ |
| 3.3.4 | Erste Seite bei 0 Ergebnissen | Bei leerer Library | Leerer Zustand mit Hinweistext | ⏳ |

### 3.4 Profil zuweisen (aus Library-View)

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 3.4.1 | "Assign Profile"-Button | Button auf Karte klicken | Dropdown mit verfügbaren Profilen erscheint | ⏳ |
| 3.4.2 | Profil wählen | Profil aus Dropdown wählen | 🔗 `assignProfile(type, arrId, profileId)` → Karte zeigt neues Profil | ⏳ |

### 3.5 Refresh

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 3.5.1 | Refresh-Button | Refresh-Icon klicken | 🔗 `getLibrary()` erneut aufgerufen, Lade-Indikator kurz sichtbar | ⏳ |

### 3.6 Bulk Auto-Sync Panel

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 3.6.1 | "Entire Library" Scope | Scope-Selector auf "Library" lassen | Keine Serienauswahl nötig | ⏳ |
| 3.6.2 | "Single Series" Scope | Scope-Selector auf "Series" stellen | Serien-Dropdown erscheint | ⏳ |
| 3.6.3 | Serien auswählen | Serie aus Dropdown wählen | Auswahl wird gespeichert | ⏳ |
| 3.6.4 | Engine wählen | Engine-Dropdown (alass / ffsubsync) | Auswahl gespeichert | ⏳ |
| 3.6.5 | Bulk Sync starten | "Start Bulk Sync" klicken | 🔗 `autoSyncBulk()` → Fortschrittsbalken erscheint | ⏳ |
| 3.6.6 | Fortschritts-Update | Während Sync laufend | 🔌 `sync_batch_progress` → Balken und "X/Y" Counter aktualisieren | ⏳ |
| 3.6.7 | Sync abgeschlossen | Warten bis fertig | 🔌 `sync_batch_complete` → Toast "Bulk sync complete: X synced, Y failed" | ⏳ |

---

## 4. SERIES DETAIL (`/library/series/:id`)

### 4.1 Kopfbereich

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 4.1.1 | Zurück-Button | "← Back"-Button klicken | Navigation zurück zu `/library` | ⏳ |
| 4.1.2 | Serientitel anzeigen | Seite laden | Titel, Jahr, Status-Badge sichtbar | ⏳ |
| 4.1.3 | Poster/Fanart | Seite laden | Poster oder Platzhalter-Bild sichtbar | ⏳ |
| 4.1.4 | "Search All Episodes" | Button klicken | 🔗 `startWantedBatchSearch(undefined, seriesId)` → Toast "Search started" | ⏳ |
| 4.1.5 | "Refresh Series" | Button klicken | 🔗 `refreshAnidbMapping(seriesId)` → Toast | ⏳ |
| 4.1.6 | "Extract All Tracks" | Button klicken | 🔗 `batchExtractAllTracks(seriesId)` → Fortschritt | ⏳ |

### 4.2 Episode-Liste

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 4.2.1 | Episodenliste laden | Seite laden | Alle Episoden aufgelistet (Nummer, Titel, Status) | ⏳ |
| 4.2.2 | Status-Badges pro Episode | Episoden betrachten | Teal=optimal ASS, Amber=upgradeable SRT, Orange=fehlend | ⏳ |
| 4.2.3 | Episode expandieren | Auf Episode klicken | Detailbereich mit Untertitel-Dateien klappt auf | ⏳ |
| 4.2.4 | Episodenfilter (Staffel) | Staffel-Tab wählen | Nur Episoden dieser Staffel angezeigt | ⏳ |

### 4.3 Episode Action Menu

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 4.3.1 | Aktionsmenü öffnen | ⋮-Button auf Episode klicken | Dropdown mit Aktionen erscheint | ⏳ |
| 4.3.2 | "Search" | Menü → "Search" | 🔗 `episodeSearch(episodeId)` → Toast | ⏳ |
| 4.3.3 | "History" | Menü → "History" | Historien-Panel expandiert | ⏳ |
| 4.3.4 | "Edit" | Menü → "Edit" | SubtitleEditorModal öffnet im Preview-Modus | ⏳ |
| 4.3.5 | "Extract" | Menü → "Extract" | 🔗 `extractEmbeddedSub(itemId)` → Toast | ⏳ |
| 4.3.6 | "Interactive Search" | Menü → "Interactive Search" | InteractiveSearchModal öffnet | ⏳ |
| 4.3.7 | "Add to Blacklist" | Menü → "Add to Blacklist" | Bestätigungs-Dialog, dann 🔗 `addToBlacklist(...)` | ⏳ |
| 4.3.8 | "View Health" | Menü → "View Health" | HealthCheckPanel öffnet | ⏳ |
| 4.3.9 | "Delete" | Menü → "Delete" | Bestätigungs-Dialog, dann 🗑️ Untertitel gelöscht | ⏳ |

### 4.4 Subtitle Editor Modal

#### 4.4.1 Modal allgemein

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 4.4.1.1 | Modal öffnet | "Edit" wählen | Modal erscheint, Lade-Animation, dann Inhalt | ⏳ |
| 4.4.1.2 | Modal schließen (X) | X-Button oben rechts | Modal schließt | ⏳ |
| 4.4.1.3 | Modal schließen (Escape) | Escape-Taste | Modal schließt | ⏳ |
| 4.4.1.4 | Ungespeichert-Warnung | Inhalt ändern, Escape drücken | Dialog "Unsaved changes — discard?" erscheint | ⏳ |
| 4.4.1.5 | Discard bestätigen | "Discard"-Button im Warn-Dialog | Modal schließt ohne Speichern | ⏳ |
| 4.4.1.6 | Discard abbrechen | "Cancel"-Button im Warn-Dialog | Modal bleibt offen mit Änderungen | ⏳ |

#### 4.4.2 Preview-Tab

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 4.4.2.1 | Preview anzeigen | Modal öffnen, Preview-Tab aktiv | Untertitel-Text lesbar dargestellt, Metadaten (Format, Encoding, Cue-Count) | ⏳ |
| 4.4.2.2 | ASS-Formatierung | ASS-Datei öffnen | Style-Tags werden berücksichtigt | ⏳ |
| 4.4.2.3 | SRT-Formatierung | SRT-Datei öffnen | Timing und Text korrekt dargestellt | ⏳ |

#### 4.4.3 Edit-Tab

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 4.4.3.1 | Edit-Tab aktivieren | "Edit"-Tab klicken | CodeMirror-Editor lädt mit Dateiinhalt | ⏳ |
| 4.4.3.2 | Text editieren | Im Editor tippen | Text ändert sich | ⏳ |
| 4.4.3.3 | Syntax-Highlighting ASS | ASS-Datei editieren | ASS-Tags farblich hervorgehoben | ⏳ |
| 4.4.3.4 | Syntax-Highlighting SRT | SRT-Datei editieren | Timestamps farblich hervorgehoben | ⏳ |
| 4.4.3.5 | "Save"-Button | Änderung machen, "Save" klicken | 🔗 `saveSubtitleContent(filePath, content)` → Toast "Saved" | ⏳ |
| 4.4.3.6 | "Discard"-Button | Änderung machen, "Discard" klicken | Inhalt zurückgesetzt auf Original | ⏳ |

#### 4.4.4 Quality Tools (im Edit-Tab)

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 4.4.4.1 | "Auto-Sync" Button | "Auto-Sync" klicken | 🔗 `autoSyncFile(filePath)` → Fortschrittsbalken → Ergebnis | ⏳ |
| 4.4.4.2 | "Overlap Fix" | "Overlap Fix" klicken | 🔗 `overlapFix(filePath)` → Toast "X overlaps fixed" | ⏳ |
| 4.4.4.3 | "Timing Normalize" | Button klicken | 🔗 `timingNormalize(filePath)` → Toast | ⏳ |
| 4.4.4.4 | "Merge Lines" | Button klicken | 🔗 `mergeLines(filePath)` → Toast "X lines merged" | ⏳ |
| 4.4.4.5 | "Split Lines" | Button klicken | 🔗 `splitLines(filePath)` → Toast "X lines split" | ⏳ |
| 4.4.4.6 | "Spell Check" | Button klicken | 🔗 `spellCheck(filePath)` → SpellCheckPanel öffnet sich | ⏳ |
| 4.4.4.7 | "Remove Credits" | Button klicken | 🔗 `removeCredits(filePath)` → Toast | ⏳ |
| 4.4.4.8 | "Detect OP/ED" | Button klicken | 🔗 `detectOpeningEnding(filePath)` → Bereiche markiert | ⏳ |

#### 4.4.5 Spell Check Panel

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 4.4.5.1 | Fehler-Liste laden | Spell Check ausführen | Liste mit falsch geschriebenen Wörtern + Kontext | ⏳ |
| 4.4.5.2 | "Fix" pro Wort | "Fix"-Button neben Wort | Wort wird durch Vorschlag ersetzt, Liste aktualisiert | ⏳ |
| 4.4.5.3 | "Ignore" pro Wort | "Ignore"-Button | Wort verschwindet aus Liste (wird nicht ersetzt) | ⏳ |
| 4.4.5.4 | Panel schließen | X-Button | SpellCheckPanel verschwindet | ⏳ |

#### 4.4.6 Diff-Tab

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 4.4.6.1 | Diff-Tab aktivieren | "Diff"-Tab klicken | Zwei-Paneel-Ansicht (Original links, Bearbeitet rechts) | ⏳ |
| 4.4.6.2 | Diff-Highlighting | Änderung machen, Diff öffnen | Geänderte Zeilen farblich hervorgehoben | ⏳ |
| 4.4.6.3 | Merge-Buttons | Diff-Ansicht betrachten | "Accept/Reject per Chunk"-Buttons sichtbar | ⏳ |

#### 4.4.7 Waveform-Tab

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 4.4.7.1 | Waveform-Tab aktivieren | "Waveform"-Tab klicken | AudioWaveform-Komponente lädt | ⏳ |
| 4.4.7.2 | Waveform anklicken | Auf Waveform klicken | Suche springt zu diesem Zeitpunkt | ⏳ |
| 4.4.7.3 | Subtitle-Cues auf Waveform | Waveform betrachten | Cue-Bereiche farblich überlagert | ⏳ |
| 4.4.7.4 | Zeitachsen-Lineal | Waveform betrachten | Zeitstempel-Markierungen sichtbar | ⏳ |

### 4.5 Interactive Search Modal

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 4.5.1 | Modal öffnen | "Interactive Search" wählen | Modal erscheint mit Lade-Animation | ⏳ |
| 4.5.2 | Ergebnisliste laden | Warten auf Ergebnisse | Provider-Ergebnisse mit Score, Release-Info, Sprache sichtbar | ⏳ |
| 4.5.3 | Qualitäts-Badges | Ergebnisse betrachten | Machine-Translation-%, HI-Flag, Forced-Flag, Trust-Bonus sichtbar | ⏳ |
| 4.5.4 | Ergebnis sortieren | Spalten-Header klicken | Liste umsortiert | ⏳ |
| 4.5.5 | "Download" pro Ergebnis | "Download"-Button | 🔗 `downloadSpecific(itemId, {provider, subtitle_id, language, translate})` → Toast | ⏳ |
| 4.5.6 | Modal schließen | X-Button oder Escape | Modal schließt | ⏳ |
| 4.5.7 | Keine Ergebnisse | Wenn keine Provider-Treffer | Leerer Zustand "No results found" | ⏳ |

### 4.6 Player Modal

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 4.6.1 | Player öffnen | "Play"-Icon auf Episode klicken | PlayerModal öffnet, Video streamt | ⏳ |
| 4.6.2 | Play/Pause | Play/Pause-Button | Video startet / pausiert | ⏳ |
| 4.6.3 | Seek-Bar | Seek-Bar ziehen | Video springt zu Position | ⏳ |
| 4.6.4 | Lautstärke | Lautstärke-Slider | Audio ändert sich | ⏳ |
| 4.6.5 | Vollbild | Vollbild-Button | Video wechselt in Vollbild | ⏳ |
| 4.6.6 | Untertitel-Track wählen | SubtitleTrackSelector Dropdown | Untertitel wechseln zur gewählten Sprache | ⏳ |
| 4.6.7 | Wiedergabegeschwindigkeit | Geschwindigkeits-Dropdown (0.5x, 1x, 1.5x, 2x) | Videogeschwindigkeit ändert sich | ⏳ |
| 4.6.8 | "Seek to Cue" | Auf Untertitel-Cue im Player klicken | Video springt zu diesem Zeitpunkt | ⏳ |
| 4.6.9 | Player schließen | X-Button | Modal schließt, Video stoppt | ⏳ |
| 4.6.10 | Streaming aktiviert prüfen | Settings → streaming_enabled | Streaming-Feature ist konfigurierbar | ⏳ |

### 4.7 Glossar-Panel

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 4.7.1 | Glossar-Panel öffnen | Glossar-Tab/Button auf SeriesDetail | Panel erscheint, Einträge laden | ⏳ |
| 4.7.2 | Einträge anzeigen | Panel betrachten | Source-Term → Target-Term, Confidence, Approved-Status | ⏳ |
| 4.7.3 | Suche/Filter | Suchfeld ausfüllen | 🔗 `getGlossaryEntries(seriesId, ...)` mit filter → gefilterte Liste | ⏳ |
| 4.7.4 | Eintrag bearbeiten | "Edit"-Button auf Eintrag | Formular-Modal öffnet mit bestehenden Werten | ⏳ |
| 4.7.5 | Eintrag speichern | Werte ändern, "Save" | 🔗 `updateGlossaryEntry(id, entry)` → Toast | ⏳ |
| 4.7.6 | Eintrag löschen | "Delete"-Button | Bestätigungs-Dialog, dann 🔗 `deleteGlossaryEntry(id)` | ⏳ |
| 4.7.7 | Begriffe vorschlagen | "Suggest Terms"-Button | 🔗 `suggestGlossaryTerms(seriesId)` → Neue Begriffe erscheinen | ⏳ |
| 4.7.8 | Glossar exportieren | "Export TSV"-Button | 🔗 `exportGlossaryTsv(seriesId)` → TSV-Datei-Download | ⏳ |
| 4.7.9 | Neuen Eintrag erstellen | "Add Entry"-Button | Leeres Formular-Modal öffnet | ⏳ |
| 4.7.10 | Neuen Eintrag speichern | Felder ausfüllen, "Save" | 🔗 `createGlossaryEntry(entry)` → Eintrag in Liste | ⏳ |

### 4.8 Health Check Panel

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 4.8.1 | "Run Health Check" | Button klicken | 🔗 `runHealthCheck(filePath)` → Ergebnis-Liste mit Issues | ⏳ |
| 4.8.2 | Issue-Liste anzeigen | Nach Scan | Issue-Typ, Schweregrad (error/warning/info), Zeilennummer | ⏳ |
| 4.8.3 | "Fix" pro Issue | "Fix"-Button neben Issue | 🔗 `applyHealthFix(fixId)` → Issue aus Liste entfernt, Toast | ⏳ |
| 4.8.4 | Kein Problem gefunden | Perfekte Datei prüfen | "No issues found"-Nachricht | ⏳ |

### 4.9 Sync Controls

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 4.9.1 | Referenz-Video wählen | Datei-Selektor | Video-/Audio-Datei ausgewählt | ⏳ |
| 4.9.2 | Engine wählen | Dropdown (alass / ffsubsync) | Auswahl gespeichert | ⏳ |
| 4.9.3 | Sync Preview | "Preview"-Button | 🔗 `getSyncPreview()` → Tabelle mit vorgeschlagenen Anpassungen | ⏳ |
| 4.9.4 | Sync anwenden | "Apply Sync"-Button | 🔗 `advancedSync(subPath, videoPath, engine)` → Fortschrittsbalken → Toast | ⏳ |

---

## 5. WANTED (`/wanted`)

### 5.1 Summary Cards

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 5.1.1 | Summary-Zahlen laden | Seite aufrufen | Wanted/Extracted/Failed/Ignored Zähler mit Werten | ⏳ |
| 5.1.2 | "Search All" Button | "Search All"-Button klicken | 🔗 `searchAllWanted()` → Toast "Search started" | ⏳ |

### 5.2 Filter Bar

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 5.2.1 | Status-Filter "Wanted" | Status-Dropdown → "Wanted" | 🔗 Nur Wanted-Items angezeigt | ⏳ |
| 5.2.2 | Status-Filter "Ignored" | Status-Dropdown → "Ignored" | Nur ignorierte Items | ⏳ |
| 5.2.3 | Status-Filter "Failed" | Status-Dropdown → "Failed" | Nur fehlgeschlagene Items | ⏳ |
| 5.2.4 | Status-Filter "Extracted" | Status-Dropdown → "Extracted" | Nur extrahierte Items | ⏳ |
| 5.2.5 | Typ-Filter "Episode" | Typ → "Episode" | Nur Episoden angezeigt | ⏳ |
| 5.2.6 | Typ-Filter "Movie" | Typ → "Movie" | Nur Filme angezeigt | ⏳ |
| 5.2.7 | Untertitel-Typ "Full" | Untertitel-Typ → "Full" | Nur Full-Subs angezeigt | ⏳ |
| 5.2.8 | Untertitel-Typ "Forced" | Untertitel-Typ → "Forced" | Nur Forced-Subs angezeigt | ⏳ |
| 5.2.9 | Titel-Suche | Text in Suchfeld eingeben | Gefilterte Ergebnisse erscheinen | ⏳ |
| 5.2.10 | Filter zurücksetzen | "Clear filters"-Button | Alle Filter zurückgesetzt, alle Items gezeigt | ⏳ |
| 5.2.11 | Sortierung "Added" | Sort → "Added" | Items nach Hinzufügedatum sortiert | ⏳ |
| 5.2.12 | Sortierung "Title" | Sort → "Title" | Items alphabetisch sortiert | ⏳ |
| 5.2.13 | Sortierung "Last Search" | Sort → "Last Search" | Nach letztem Suchdatum sortiert | ⏳ |
| 5.2.14 | Sortierung "Score" | Sort → "Current Score" | Nach aktuellem Score sortiert | ⏳ |
| 5.2.15 | Sortierung "Search Count" | Sort → "Search Count" | Nach Suchanzahl sortiert | ⏳ |

### 5.3 Filter Presets

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 5.3.1 | Filter-Preset speichern | Filter setzen, "Save Preset", Name eingeben | 🔗 `createFilterPreset()` → Preset in Liste | ⏳ |
| 5.3.2 | Preset laden | Preset aus Dropdown wählen | Filter werden auf gespeicherte Werte gesetzt | ⏳ |
| 5.3.3 | Preset löschen | "Delete"-Icon bei Preset | 🔗 `deleteFilterPreset(id)` → Aus Liste entfernt | ⏳ |

### 5.4 Item-Auswahl & Batch-Aktionen

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 5.4.1 | Einzelne Checkbox | Checkbox bei Item klicken | Item wird ausgewählt (Checkbox gecheckt) | ⏳ |
| 5.4.2 | BatchActionBar erscheint | Item auswählen | BatchActionBar taucht auf mit "1 item selected" | ⏳ |
| 5.4.3 | Mehrere Items wählen | Mehrere Checkboxen | BatchActionBar zeigt korrekte Anzahl | ⏳ |
| 5.4.4 | "Select All" | Select-All-Checkbox | Alle Items auf aktueller Seite werden ausgewählt | ⏳ |
| 5.4.5 | Auswahl aufheben | Alle Checkboxen deaktivieren | BatchActionBar verschwindet | ⏳ |
| 5.4.6 | "Search Selected" | Items wählen, "Search Selected" | 🔗 `startWantedBatchSearch(selectedItemIds)` → Fortschritt | ⏳ |
| 5.4.7 | "Extract Embedded" | Items wählen, "Extract Embedded" | 🔗 `batchExtractEmbedded(selectedItemIds)` → Fortschrittsbalken | ⏳ |
| 5.4.8 | "Re-translate" | Items wählen, "Re-translate" | 🔗 `batchTranslate(selectedItemIds)` → Toast | ⏳ |
| 5.4.9 | "Mark as Ignored" | Items wählen, "Mark as Ignored" | 🔗 `updateWantedItemStatus()` für alle → Status ändert sich | ⏳ |
| 5.4.10 | "Delete Selected" | Items wählen, "Delete" | Bestätigungs-Dialog, dann 🗑️ Items entfernt | ⏳ |
| 5.4.11 | "Cleanup Sidecars" | Items wählen, "Cleanup" | Modal mit Dry-Run-Toggle, 🔗 `cleanupSidecars()` | ⏳ |
| 5.4.12 | WebSocket Batch-Progress | Batch-Suche laufend | 🔌 `wanted_search_progress` → Counter in BatchActionBar aktualisiert | ⏳ |
| 5.4.13 | WebSocket Batch-Complete | Batch-Suche fertig | 🔌 `wanted_search_completed` → Toast "Search complete: X found" | ⏳ |
| 5.4.14 | WebSocket Extract-Progress | Batch-Extract laufend | 🔌 `batch_extract_progress` → Fortschritt | ⏳ |
| 5.4.15 | WebSocket Extract-Complete | Batch-Extract fertig | 🔌 `batch_extract_complete` → Toast | ⏳ |

### 5.5 Per-Item Aktionsmenü

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 5.5.1 | Aktionsmenü öffnen | ⋮-Button klicken | Dropdown erscheint | ⏳ |
| 5.5.2 | "Search" | Menü → "Search" | 🔗 `searchWantedItem(itemId)` → Toast | ⏳ |
| 5.5.3 | "Process" | Menü → "Process" | 🔗 `processWantedItem(itemId)` → Toast | ⏳ |
| 5.5.4 | "Extract" | Menü → "Extract" | 🔗 `extractEmbeddedSub(itemId)` → Status ändert sich | ⏳ |
| 5.5.5 | "Interactive Search" | Menü → "Interactive Search" | InteractiveSearchModal öffnet | ⏳ |
| 5.5.6 | "Edit" | Menü → "Edit" | SubtitleEditorModal öffnet | ⏳ |
| 5.5.7 | "Delete" | Menü → "Delete" | Bestätigungs-Dialog | ⏳ |
| 5.5.8 | "Mark as Wanted" | Menü → "Mark as..." | Status ändert sich zu "wanted" | ⏳ |
| 5.5.9 | "Mark as Ignored" | Menü → "Mark as Ignored" | Status ändert sich zu "ignored", Item verschwindet bei Filter "Wanted" | ⏳ |
| 5.5.10 | "Add to Blacklist" | Menü → "Add to Blacklist" | 🔗 `addToBlacklist(...)` → Toast | ⏳ |

### 5.6 Status-Badges (Wanted-Tabelle)

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 5.6.1 | "Wanted"-Badge | Item mit status=wanted | Oranges/Gelbes Badge "Wanted" | ⏳ |
| 5.6.2 | "Found"-Badge | Item mit status=found | Grünes Badge "Found" | ⏳ |
| 5.6.3 | "Failed"-Badge | Item mit status=failed | Rotes Badge "Failed" | ⏳ |
| 5.6.4 | "Ignored"-Badge | Item mit status=ignored | Graues Badge "Ignored" | ⏳ |
| 5.6.5 | "Extracted"-Badge | Item mit status=extracted | Teal Badge "Extracted" | ⏳ |
| 5.6.6 | "Full"-Badge | item.subtitle_type=full | Blaues Badge "Full" | ⏳ |
| 5.6.7 | "Forced"-Badge | item.subtitle_type=forced | Blaues Badge "Forced" | ⏳ |

---

## 6. ACTIVITY (`/activity`)

### 6.1 Jobliste

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 6.1.1 | Jobs laden | Seite aufrufen | Tabelle mit Jobs (File, Status, Source, Backend, Quality, Updated) | ⏳ |
| 6.1.2 | Automatisches Refresh | 15 Sekunden warten | Neue Jobs erscheinen automatisch | ⏳ |

### 6.2 Filter & Suche

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 6.2.1 | Status-Filter "Queued" | Auf "Queued"-Button klicken | Nur eingereihte Jobs | ⏳ |
| 6.2.2 | Status-Filter "Running" | "Running"-Button | Nur laufende Jobs | ⏳ |
| 6.2.3 | Status-Filter "Completed" | "Completed"-Button | Nur abgeschlossene Jobs | ⏳ |
| 6.2.4 | Status-Filter "Failed" | "Failed"-Button | Nur fehlgeschlagene Jobs | ⏳ |
| 6.2.5 | Filter zurücksetzen | "All"-Button | Alle Jobs angezeigt | ⏳ |

### 6.3 Expandierbare Zeilen

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 6.3.1 | Zeile expandieren | Auf Jobzeile klicken | Detailbereich expandiert mit weiteren Infos | ⏳ |
| 6.3.2 | Zeile kollabieren | Erneut auf expandierte Zeile klicken | Detailbereich klappt zu | ⏳ |
| 6.3.3 | Vollständiger Dateipfad | Expandierte Zeile betrachten | Absoluter Pfad zur Videodatei | ⏳ |
| 6.3.4 | Output-Pfad | Expandierte Zeile (bei completed) | Pfad zur erstellen Untertiteldatei | ⏳ |
| 6.3.5 | Quality Score Bar | Expandierte Zeile | Farbbalken (grün≥75%, gelb≥50%, rot<50%) | ⏳ |
| 6.3.6 | Fehlermeldung | Expandierte failed-Zeile | Vollständige Fehlermeldung sichtbar | ⏳ |

### 6.4 Aktionen

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 6.4.1 | "Retry"-Button bei Failed | "Retry" auf fehlgeschlagenem Job | 🔗 `retryJob(jobId)` → Job status → "queued" | ⏳ |
| 6.4.2 | Refresh-Button | "Refresh"-Icon klicken | 🔗 `getJobs()` erneut → frische Daten | ⏳ |

### 6.5 Pagination

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 6.5.1 | Nächste Seite | Pfeil-Button | Nächste Job-Seite | ⏳ |
| 6.5.2 | Vorherige Seite | Zurück-Pfeil | Vorherige Job-Seite | ⏳ |
| 6.5.3 | Items pro Seite | PerPage-Dropdown (10/25/50) | Entsprechende Anzahl Jobs | ⏳ |

---

## 7. HISTORY (`/history`)

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 7.1 | History laden | Seite aufrufen | Tabelle mit Download-Einträgen (Datei, Provider, Sprache, Zeitpunkt) | ⏳ |
| 7.2 | Provider-Filter | Provider-Dropdown wählen | Nur Einträge von diesem Provider | ⏳ |
| 7.3 | Sprach-Filter | Sprach-Dropdown wählen | Nur Einträge für diese Sprache | ⏳ |
| 7.4 | Provider-Stats anzeigen | Stats-Karte | Erfolgsrate pro Provider in % | ⏳ |
| 7.5 | Sprach-Stats anzeigen | Stats-Karte | Downloads pro Sprache | ⏳ |
| 7.6 | Pagination | Seiten-Buttons | Korrekte Einträge der jeweiligen Seite | ⏳ |

---

## 8. BLACKLIST (`/blacklist`)

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 8.1 | Blacklist laden | Seite aufrufen | Tabelle mit Blacklist-Einträgen (Provider, Subtitle-ID, Sprache, Grund) | ⏳ |
| 8.2 | Eintrag entfernen | "Remove"-Button neben Eintrag | 🔗 `removeFromBlacklist(id)` → Eintrag entfernt, Toast | ⏳ |
| 8.3 | "Clear All"-Button | "Clear All" klicken | Bestätigungs-Dialog erscheint | ⏳ |
| 8.4 | "Clear All" bestätigen | "Confirm" in Dialog | 🔗 `clearBlacklist()` → Tabelle leer, Toast | ⏳ |
| 8.5 | "Clear All" abbrechen | "Cancel" in Dialog | Dialog schließt, Blacklist unverändert | ⏳ |
| 8.6 | Pagination | Seiten-Buttons | Korrekte Einträge | ⏳ |
| 8.7 | Leere Blacklist | Wenn keine Einträge | "No blacklisted entries"-Nachricht | ⏳ |

---

## 9. SETTINGS (`/settings`)

### 9.1 Tab-Navigation

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 9.1.1 | General-Tab | Tab klicken | General-Einstellungen sichtbar | ⏳ |
| 9.1.2 | Providers-Tab | Tab klicken | Provider-Kacheln sichtbar | ⏳ |
| 9.1.3 | Translation-Tab | Tab klicken | Translation-Einstellungen sichtbar | ⏳ |
| 9.1.4 | Whisper-Tab | Tab klicken | Whisper-Einstellungen sichtbar | ⏳ |
| 9.1.5 | Media Servers-Tab | Tab klicken | Media-Server-Liste sichtbar | ⏳ |
| 9.1.6 | Automation-Tab | Tab klicken | Hooks/Webhooks-Konfiguration sichtbar | ⏳ |
| 9.1.7 | Notifications-Tab | Tab klicken | Notification-Template-Liste sichtbar | ⏳ |
| 9.1.8 | Integrations-Tab | Tab klicken | Export/Import-Buttons sichtbar | ⏳ |
| 9.1.9 | API Keys-Tab | Tab klicken | API-Key-Liste sichtbar | ⏳ |
| 9.1.10 | Security-Tab | Tab klicken | Login/Auth-Einstellungen sichtbar | ⏳ |
| 9.1.11 | Advanced-Tab | Tab klicken | Scoring/Cleanup-Einstellungen sichtbar | ⏳ |

### 9.2 General Tab

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 9.2.1 | App Name ändern | Textfeld → Wert ändern → Save | 🔗 `updateConfig({app_name: "..."})` → Toast "Saved" | ⏳ |
| 9.2.2 | Default Language | Dropdown → Sprache wählen → Save | 🔗 Gespeichert | ⏳ |
| 9.2.3 | Log Level | Dropdown → Level wählen → Save | 🔗 Gespeichert | ⏳ |
| 9.2.4 | Log Retention | Zahlfeld → Wert → Save | 🔗 Gespeichert | ⏳ |
| 9.2.5 | "Check Updates" Toggle | Toggle umschalten → Save | 🔗 Gespeichert | ⏳ |
| 9.2.6 | "Auto-Extract" Toggle | Toggle umschalten → Save | 🔗 Gespeichert | ⏳ |
| 9.2.7 | "Auto-Translate" Toggle | Toggle umschalten → Save | 🔗 Gespeichert | ⏳ |
| 9.2.8 | Validierung required Feld | Pflichtfeld leeren → Save versuchen | Fehler-Highlight, kein API-Call | ⏳ |

### 9.3 Providers Tab

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 9.3.1 | Provider-Kacheln laden | Tab aufrufen | Alle Provider als Kacheln dargestellt | ⏳ |
| 9.3.2 | Provider aktivieren | Enable-Toggle auf Kachel | Provider wird aktiv, Kachel-Styling ändert sich | ⏳ |
| 9.3.3 | Provider deaktivieren | Enable-Toggle deaktivieren | Provider inaktiv | ⏳ |
| 9.3.4 | "Test"-Button auf Kachel | "Test"-Button | 🔗 `testProvider(name)` → Health-Badge (grün/rot) | ⏳ |
| 9.3.5 | ProviderEditModal öffnen | "Edit"-Button auf Kachel | Modal mit Provider-Konfigurationsfeldern | ⏳ |
| 9.3.6 | API-Key eingeben | API-Key-Feld ausfüllen | Eingabe maskiert (Passwort-Typ), `***configured***` für gespeicherte Keys | ⏳ |
| 9.3.7 | Provider testen (in Modal) | "Test"-Button in Modal | 🔗 `testProvider(name, config)` → Grüner/Roter Status | ⏳ |
| 9.3.8 | Modal schließen | X-Button | Modal schließt | ⏳ |
| 9.3.9 | "Delete"-Button (Custom) | "Delete" auf benutzerdefin. Provider | Bestätigungs-Dialog, dann Provider entfernt | ⏳ |

### 9.4 Translation Tab

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 9.4.1 | Engine wählen | Engine-Dropdown (ollama/openai/claude) | Kontext-Felder wechseln je nach Engine | ⏳ |
| 9.4.2 | Modellname eingeben | Text-Feld | Gespeichert | ⏳ |
| 9.4.3 | API-Key (wenn nicht Ollama) | Passwort-Feld | Maskiert, `***configured***` wenn gespeichert | ⏳ |
| 9.4.4 | Temperature | Slider ziehen | Wert ändert sich, gespeichert | ⏳ |
| 9.4.5 | Custom Prompt | Textarea ausfüllen | Freier Text, gespeichert | ⏳ |
| 9.4.6 | Prompt Preset wählen | Dropdown | Textarea füllt sich mit Preset-Inhalt | ⏳ |
| 9.4.7 | Save | "Save"-Button | 🔗 `updateConfig(translationValues)` → Toast | ⏳ |

### 9.5 Media Servers Tab

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 9.5.1 | Instanz-Liste laden | Tab aufrufen | Alle konfigurierten Server aufgelistet | ⏳ |
| 9.5.2 | Server-Typ wählen | Jellyfin/Emby/Plex/Kodi Selector | Formular-Felder passen sich an | ⏳ |
| 9.5.3 | "Add Server" | "Add Server"-Button | Leeres Formular erscheint | ⏳ |
| 9.5.4 | Server-URL eingeben | URL-Feld | Gespeichert | ⏳ |
| 9.5.5 | API-Key eingeben | API-Key-Feld | Maskiert | ⏳ |
| 9.5.6 | "Test Server" | "Test"-Button | 🔗 `testMediaServer(...)` → Status angezeigt | ⏳ |
| 9.5.7 | Server bearbeiten | "Edit"-Button | Formular mit bestehenden Werten | ⏳ |
| 9.5.8 | Server löschen | "Delete"-Button | Bestätigungs-Dialog → Server entfernt | ⏳ |

### 9.6 Automation Tab (Hooks & Webhooks)

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 9.6.1 | Hooks-Liste laden | Tab aufrufen | Interne Hooks aufgelistet | ⏳ |
| 9.6.2 | Hook aktivieren | Toggle | Hook aktiv | ⏳ |
| 9.6.3 | Webhook-URL eingeben | URL-Feld | Gespeichert | ⏳ |
| 9.6.4 | "Test Webhook" | "Test"-Button | 🔗 `testWebhook(url)` → Toast Erfolg/Fehler | ⏳ |
| 9.6.5 | Quiet Hours aktivieren | Enable-Checkbox | Zeitfelder erscheinen | ⏳ |
| 9.6.6 | Start-Zeit setzen | Zeit-Picker | Gespeichert | ⏳ |
| 9.6.7 | End-Zeit setzen | Zeit-Picker | Gespeichert | ⏳ |

### 9.7 Notifications Tab

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 9.7.1 | Template-Liste laden | Tab aufrufen | Templates pro Event-Typ aufgelistet | ⏳ |
| 9.7.2 | Template bearbeiten | "Edit"-Button | Editor-Modal mit Textarea | ⏳ |
| 9.7.3 | Variablen im Template | `{{series}}`, `{{episode}}` eintragen | Platzhalter als Text im Feld | ⏳ |
| 9.7.4 | Template-Vorschau | "Preview"-Button | 🔗 `previewNotificationTemplate()` → Beispieltext | ⏳ |
| 9.7.5 | Template speichern | "Save"-Button | 🔗 `updateNotificationTemplate()` → Toast | ⏳ |
| 9.7.6 | Template löschen | "Delete"-Button | Bestätigungs-Dialog → 🗑️ | ⏳ |
| 9.7.7 | Template duplizieren | "Duplicate"-Button | Kopie erstellt, Modal öffnet | ⏳ |

### 9.8 Integrations Tab

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 9.8.1 | "Export Config" | Button klicken | 🔗 `exportConfig()` → JSON-Datei-Download | ⏳ |
| 9.8.2 | "Import Config" | Datei auswählen | 🔗 `importConfig(config)` → Toast | ⏳ |
| 9.8.3 | "Export API Keys" | Button klicken | 🔗 CSV-Download | ⏳ |
| 9.8.4 | "Import API Keys" | Datei auswählen | 🔗 Keys werden importiert | ⏳ |
| 9.8.5 | "Export Statistics" | Button klicken | JSON/CSV-Download | ⏳ |
| 9.8.6 | Bazarr Migration Preview | Migration-Button | 🔗 `importBazarrConfig()` → Vorschau | ⏳ |
| 9.8.7 | Bazarr Migration bestätigen | "Confirm Import" | 🔗 `confirmBazarrImport()` → Toast | ⏳ |

### 9.9 API Keys Tab

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 9.9.1 | Key-Liste laden | Tab aufrufen | Keys mit Name, Erstellt, Zuletzt genutzt | ⏳ |
| 9.9.2 | "Generate Key" | Button klicken | Formular erscheint (Name, Scopes) | ⏳ |
| 9.9.3 | Key-Name eingeben | Name-Feld ausfüllen | Gespeichert | ⏳ |
| 9.9.4 | Scopes wählen | Scope-Checkboxen | Ausgewählt | ⏳ |
| 9.9.5 | Key erstellen | "Create"-Button | 🔗 `createApiKey(...)` → Key einmalig im Klartext angezeigt | ⏳ |
| 9.9.6 | Key kopieren | "Copy"-Icon | Key in Zwischenablage | ⏳ |
| 9.9.7 | Key testen | "Test"-Button | 🔗 `testApiKey(key)` → Erfolg/Fehler | ⏳ |
| 9.9.8 | Key widerrufen | "Revoke"-Button | Bestätigungs-Dialog → 🗑️ | ⏳ |

### 9.10 Security Tab

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 9.10.1 | Login-Formular anzeigen | Tab aufrufen (wenn Auth aktiv) | E-Mail + Passwort-Felder + Change-Button | ⏳ |
| 9.10.2 | Passwort ändern | Neues PW eingeben, "Change" klicken | 🔗 Passwort aktualisiert, Toast | ⏳ |
| 9.10.3 | "Logout"-Button | Logout-Button klicken | Session gecleart, Redirect zu `/login` | ⏳ |

### 9.11 Advanced Tab

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 9.11.1 | "Edit Weights"-Button | Scoring-Bereich → "Edit Weights" | Modal mit Schiebereglern pro Provider | ⏳ |
| 9.11.2 | Gewichtung anpassen | Slider ziehen | Wert ändert sich | ⏳ |
| 9.11.3 | Gewichtung speichern | "Save"-Button | 🔗 `updateScoringWeights(...)` → Toast | ⏳ |
| 9.11.4 | "Reset to Defaults" | Button klicken | 🔗 `resetScoringWeights()` → Standardwerte | ⏳ |
| 9.11.5 | Cleanup-Regeln definieren | Regelfelder ausfüllen | Regeln werden gespeichert | ⏳ |
| 9.11.6 | Cleanup ausführen | "Run Cleanup"-Button | 🔗 Cleanup-Vorgang → Toast | ⏳ |
| 9.11.7 | DB Backup | "Backup"-Button | Datenbankdatei-Download | ⏳ |
| 9.11.8 | DB Restore | Datei hochladen | Bestätigung + Restore | ⏳ |
| 9.11.9 | DB Optimize | "Optimize"-Button | 🔗 Vacuum/Analyze → Toast | ⏳ |

---

## 10. STATISTICS (`/statistics`)

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 10.1 | Download-Chart laden | Seite aufrufen | Linienchart mit Tagesstatistik (kein leeres div) | ⏳ |
| 10.2 | Format-Chart laden | Seite aufrufen | Kuchenchart ASS vs SRT | ⏳ |
| 10.3 | Provider-Chart laden | Seite aufrufen | Balken-Chart pro Provider | ⏳ |
| 10.4 | Qualitäts-Trend-Chart | Seite aufrufen | Linienchart Qualitätstrend | ⏳ |
| 10.5 | Translation-Chart laden | Seite aufrufen | Übersetzungsstatistiken | ⏳ |
| 10.6 | Provider-Erfolgsrate | Chart betrachten | Win-Rate in % pro Provider | ⏳ |
| 10.7 | Statistiken exportieren | "Export"-Button | 🔗 `exportStatistics()` → JSON/CSV Download | ⏳ |
| 10.8 | Charts interaktiv | Hover auf Chart-Punkt | Tooltip mit exakten Werten erscheint | ⏳ |

---

## 11. TASKS (`/tasks`)

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 11.1 | Task-Liste laden | Seite aufrufen | Alle Background-Tasks mit Status (laufend/geplant/abgeschlossen) | ⏳ |
| 11.2 | Task-Status anzeigen | Liste betrachten | Status-Badge pro Task | ⏳ |
| 11.3 | Task abbrechen | "Cancel"-Button | 🔗 `cancelTask(taskId)` → Status ändert sich | ⏳ |
| 11.4 | Scheduler-Status | Liste betrachten | Nächster geplanter Lauf sichtbar (z.B. "Wanted Scan in 3h 42m") | ⏳ |
| 11.5 | Task manuell starten | "Run Now"-Button (falls vorhanden) | 🔗 Task wird eingereihrt | ⏳ |

---

## 12. LOGS (`/logs`)

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 12.1 | Log-Output laden | Seite aufrufen | Log-Zeilen werden angezeigt (neueste zuerst) | ⏳ |
| 12.2 | Level-Filter DEBUG | DEBUG wählen | Alle Log-Levels sichtbar | ⏳ |
| 12.3 | Level-Filter INFO | INFO wählen | Nur INFO, WARNING, ERROR | ⏳ |
| 12.4 | Level-Filter WARNING | WARNING wählen | Nur WARNING, ERROR | ⏳ |
| 12.5 | Level-Filter ERROR | ERROR wählen | Nur Fehler | ⏳ |
| 12.6 | Log-Zeilen-Limit | Standardausgabe | Letzte N Zeilen angezeigt | ⏳ |
| 12.7 | "Download"-Button | Button klicken | Log-Datei wird heruntergeladen | ⏳ |
| 12.8 | "Clear"-Button | Button klicken | Bestätigungs-Dialog → Logs gecleart | ⏳ |
| 12.9 | Farbcodierung | Logs betrachten | DEBUG=grau, INFO=weiß, WARNING=gelb, ERROR=rot | ⏳ |

---

## 13. PLUGINS (`/plugins`)

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 13.1 | Marketplace laden | Seite aufrufen | Plugin-Kacheln mit Name, Beschreibung, Version | ⏳ |
| 13.2 | Plugin installieren | "Install"-Button | 🔗 `installMarketplacePlugin()` → Fortschritt → Toast | ⏳ |
| 13.3 | Installiertes Plugin anzeigen | Nach Installation | Plugin in "Installed"-Liste | ⏳ |
| 13.4 | Plugin deinstallieren | "Uninstall"-Button | Bestätigungs-Dialog → 🔗 `uninstallMarketplacePlugin()` | ⏳ |
| 13.5 | Plugin-Details | Plugin-Kachel erweitern | Beschreibung, Autor, Version, Changelog | ⏳ |

---

## 14. AUTH (`/login`, `/setup`, `/onboarding`)

### 14.1 Login

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 14.1.1 | Login-Formular | `/login` aufrufen (wenn Auth aktiv) | E-Mail + Passwort-Felder sichtbar | ⏳ |
| 14.1.2 | Valide Credentials | Korrekte E-Mail/PW → "Login" | 🔗 `login(email, password)` → Redirect zu `/` | ⏳ |
| 14.1.3 | Falsche Credentials | Falsches PW → "Login" | Fehlermeldung "Invalid credentials" | ⏳ |
| 14.1.4 | Leeres Formular | Ohne Eingabe → "Login" | Validierungsfehler, kein API-Call | ⏳ |
| 14.1.5 | AuthGuard redirect | Geschützte Route ohne Login aufrufen | Redirect zu `/login` | ⏳ |
| 14.1.6 | Eingeloggt bleiben | Nach Login, Seite neu laden | Session bleibt, kein Redirect zu `/login` | ⏳ |

### 14.2 Setup / Onboarding

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 14.2.1 | Setup-Seite | `/setup` aufrufen (erste Einrichtung) | Einrichtungsformular erscheint | ⏳ |
| 14.2.2 | Onboarding-Wizard | `/onboarding` bei erstem Start | Mehrstufiger Wizard | ⏳ |
| 14.2.3 | Wizard-Schritt vor | "Weiter"-Button | Nächster Schritt | ⏳ |
| 14.2.4 | Wizard-Schritt zurück | "Zurück"-Button | Vorheriger Schritt | ⏳ |
| 14.2.5 | Wizard abschließen | Letzter Schritt → "Fertig" | Redirect zu `/` | ⏳ |

---

## 15. GLOBALE KOMPONENTEN

### 15.1 Global Search Modal

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 15.1.1 | Modal öffnen | Ctrl+K oder Search-Icon | Suchfeld im Vordergrund | ⏳ |
| 15.1.2 | Suche tippen | Text eingeben | Ergebnisse erscheinen (Serien, Episoden) | ⏳ |
| 15.1.3 | Ergebnis anklicken | Ergebnis auswählen | Navigation zur entsprechenden Seite | ⏳ |
| 15.1.4 | Pfeil-Navigation | Pfeil-Hoch/Runter | Auswahl bewegt sich | ⏳ |
| 15.1.5 | Enter auswählen | Enter auf Ergebnis | Navigation | ⏳ |
| 15.1.6 | Leere Suche | Nichts eingeben | Letzten Suchen oder Vorschläge | ⏳ |
| 15.1.7 | Keine Ergebnisse | Nicht-existentes suchen | "No results"-Nachricht | ⏳ |

### 15.2 Quick Actions FAB

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 15.2.1 | FAB-Button | Floating Action Button klicken | Quick-Actions-Menü öffnet | ⏳ |
| 15.2.2 | Quick Action ausführen | Action wählen | Entsprechende Aktion | ⏳ |
| 15.2.3 | Menü schließen | Außerhalb klicken oder Escape | Menü schließt | ⏳ |

### 15.3 Toast-Benachrichtigungen

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 15.3.1 | Erfolgs-Toast | Erfolgreiche Aktion | Grüner Toast oben rechts | ⏳ |
| 15.3.2 | Fehler-Toast | Fehlgeschlagene Aktion | Roter Toast | ⏳ |
| 15.3.3 | Info-Toast | Informations-Event | Blauer/Grauer Toast | ⏳ |
| 15.3.4 | Warning-Toast | Warnungs-Event | Gelber Toast | ⏳ |
| 15.3.5 | Toast auto-dismiss | Warten (ca. 5 Sek.) | Toast verschwindet automatisch | ⏳ |
| 15.3.6 | Toast manuell schließen | X-Button auf Toast | Toast verschwindet sofort | ⏳ |
| 15.3.7 | Mehrere Toasts | Mehrere Aktionen | Toasts stapeln sich | ⏳ |

### 15.4 InfoTooltip

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 15.4.1 | Tooltip erscheint | Auf ?-Icon hovern | Beschreibungstext im Tooltip | ⏳ |
| 15.4.2 | Tooltip verschwindet | Maus wegbewegen | Tooltip verschwindet | ⏳ |

### 15.5 Error Boundary

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 15.5.1 | Fehler abfangen | Simulierten JS-Fehler auslösen | ErrorBoundary zeigt Fehlermeldung statt weißem Screen | ⏳ |
| 15.5.2 | "Retry"-Button | Button in ErrorBoundary | Komponente wird neu gerendert | ⏳ |

---

## 16. ACCESSIBILITY (Barrierefreiheit)

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 16.1 | Tab-Navigation | Tab-Taste durch gesamte UI | Fokus bewegt sich logisch durch alle interaktiven Elemente | ⏳ |
| 16.2 | Modal-Fokus | Modal öffnen | Fokus springt in Modal, verlässt diesen nicht (Fokus-Trap) | ⏳ |
| 16.3 | Modal Escape schließt | Escape in jedem Modal | Modal schließt | ⏳ |
| 16.4 | Aria-Labels Icons | Screen-Reader mit Icon-Button | aria-label wird vorgelesen | ⏳ |
| 16.5 | Dialog-Role | Modal öffnen, DOM prüfen | `role="dialog"` + `aria-modal="true"` auf innerem Card-div | ⏳ |
| 16.6 | Skip-to-Content | Tab auf Seite | "Skip to main content"-Link erscheint | ⏳ |
| 16.7 | Farbe nicht einziger Indikator | Statusbadges | Zusätzlich Icon oder Text, nicht nur Farbe | ⏳ |

---

## 17. RESPONSIVE DESIGN

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 17.1 | Mobile Sidebar | Viewport auf <768px | Hamburger-Menü erscheint, Sidebar versteckt | ⏳ |
| 17.2 | Mobile Sidebar öffnen | Hamburger klicken | Sidebar als Overlay | ⏳ |
| 17.3 | Mobile Tabellen | Tabellen auf Mobile | Horizontal scrollbar oder Stacking | ⏳ |
| 17.4 | Mobile Grid | Library-Grid auf Mobile | 1-Spalten-Layout | ⏳ |
| 17.5 | Mobile Modals | Modal auf Mobile | Volle Viewport-Breite | ⏳ |
| 17.6 | Tablet-Layout | Viewport ~768px–1024px | 2-Spalten-Grid, Sidebar schmal | ⏳ |

---

## 18. PERFORMANCE & LADEZUSTÄNDE

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 18.1 | Lade-Skeleton | Seite erstmals laden | Skeleton-Animationen statt leerem Inhalt | ⏳ |
| 18.2 | Lazy Loading | Code-Splitting | Editor/Player laden erst bei Bedarf (DevTools → Network) | ⏳ |
| 18.3 | Pagination Keep-Previous | Seitennavigation | Vorige Seite bleibt sichtbar während neue lädt | ⏳ |
| 18.4 | API-Fehler anzeigen | Backend unavailable | Fehlermeldung statt endlosem Spinner | ⏳ |
| 18.5 | Offline/Network-Fehler | Netzwerk trennen | Fehlermeldung "Could not connect to backend" | ⏳ |

---

## 19. WEBSOCKET / REAL-TIME

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 19.1 | Verbindungsstatus | WebSocket-Verbindung betrachten | Verbindungsindikator (grün=verbunden) | ⏳ |
| 19.2 | Reconnect | WS-Verbindung trennen (DevTools) | Automatische Reconnect-Versuche | ⏳ |
| 19.3 | `wanted_search_completed` | Suche ausführen | Toast erscheint ohne Seite neu zu laden | ⏳ |
| 19.4 | `upgrade_completed` | SRT→ASS Upgrade ausführen | Toast "Upgrade complete: ..." | ⏳ |
| 19.5 | `config_updated` | Config extern ändern | `config_updated`-Event → Cache invalidiert | ⏳ |
| 19.6 | `webhook_received` | Sonarr/Radarr Webhook senden | Toast "Webhook received: Serientitel" | ⏳ |
| 19.7 | `retranslation_completed` | Re-translation Batch beenden | Toast mit Statistiken | ⏳ |
| 19.8 | `wanted_scan_progress` | Wanted-Scan läuft | Fortschrittsanzeige in Tasks-Seite / Widget | ⏳ |

---

## ANHANG: TESTUMGEBUNG EINRICHTEN

```bash
# Entwicklungsserver starten
npm run dev
# → Backend: http://localhost:5765
# → Frontend: http://localhost:5173

# Mit Test-Daten (falls vorhanden)
cd backend && python seed_test_data.py

# Browser-DevTools für WebSocket-Events
# → Application → WebSocket → socket.io
```

### Empfohlene Test-Reihenfolge

1. Auth (14) — sicherstellen, dass Login funktioniert
2. Navigation (1) — sicherstellen, dass alle Seiten erreichbar
3. Settings (9) — Providers/Translation konfigurieren
4. Library (3) → Series Detail (4) — Hauptworkflow
5. Wanted (5) — Such-/Extraktions-Workflow
6. Activity (6) / History (7) — Ergebnisse verifizieren
7. Globale Komponenten (15) — Toast, Toasts, Search
8. Accessibility (16) — Tab-Navigation, Aria
9. Responsive (17) — Mobile-Ansicht

---

---

## 20. KEYBOARD SHORTCUTS (Erweitert)

### 20.1 Navigation-Shortcuts (g-Key Combos)

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 20.1.1 | `g d` → Dashboard | `g` dann `d` drücken | Navigation zu `/` | ⏳ |
| 20.1.2 | `g l` → Library | `g` dann `l` drücken | Navigation zu `/library` | ⏳ |
| 20.1.3 | `g w` → Wanted | `g` dann `w` drücken | Navigation zu `/wanted` | ⏳ |
| 20.1.4 | `g s` → Settings | `g` dann `s` drücken | Navigation zu `/settings` | ⏳ |
| 20.1.5 | `g a` → Activity | `g` dann `a` drücken | Navigation zu `/activity` | ⏳ |
| 20.1.6 | `g h` → History | `g` dann `h` drücken | Navigation zu `/history` | ⏳ |
| 20.1.7 | Shortcut in Textfeld | Im Editor tippen, dann `g d` versuchen | Kein Versehentliches Navigieren | ⏳ |

### 20.2 Editor-Shortcuts (SubtitleEditor)

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 20.2.1 | `Ctrl+S` Speichern | Im Editor `Ctrl+S` drücken | 🔗 `saveSubtitleContent()` → Toast "Saved" | ⏳ |
| 20.2.2 | `Ctrl+Z` Rückgängig | Änderung machen, `Ctrl+Z` | Letzte Änderung rückgängig | ⏳ |
| 20.2.3 | `Ctrl+Shift+Z` Wiederholen | Nach Rückgängig: `Ctrl+Shift+Z` | Rückgängig-Aktion wiederholt | ⏳ |
| 20.2.4 | `Ctrl+H` Suchen & Ersetzen | Im Editor `Ctrl+H` | CodeMirror Find-&-Replace-Panel öffnet | ⏳ |

---

## 21. SUBTITLE EDITOR (Erweiterte Tests)

### 21.1 Validierung & Konflikt-Erkennung

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 21.1.1 | Debounced Validation | Schnell tippen (mehrere Zeichen) | Validierung läuft erst ~500ms nach letzter Eingabe | ⏳ |
| 21.1.2 | Mtime-Konflikt (409) | Datei extern ändern, dann in UI speichern | 409-Fehler → "File was modified externally. Reload?" Dialog | ⏳ |
| 21.1.3 | "Reload before saving" | Konflikt-Dialog → "Reload" klicken | Datei wird neu geladen, Änderungen gehen verloren | ⏳ |
| 21.1.4 | "Force save" bei Konflikt | Konflikt-Dialog → "Save Anyway" | Trotzdem gespeichert, Toast | ⏳ |
| 21.1.5 | `beforeunload` Warning | Änderung machen, Tab schließen versuchen | Browser-Warnung "Ungespeicherte Änderungen" | ⏳ |
| 21.1.6 | Last-Modified Tracking | Mehrfach speichern | Timestamp aktualisiert sich nach jedem Save | ⏳ |

### 21.2 ASS/SRT Edge Cases

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 21.2.1 | Ungültige Timestamps | `0:99:99.999 --> 0:00:00.000` eingeben | Validation-Fehler hervorgehoben | ⏳ |
| 21.2.2 | Zeilenumbruch in ASS-Cue | `\N` in ASS-Cue | Korrekt als Zeilenumbruch dargestellt | ⏳ |
| 21.2.3 | Sonderzeichen in Pfad | Datei mit `ä`, `ö`, `[`, `)` im Pfad | Datei wird korrekt geladen und gespeichert | ⏳ |

---

## 22. SERIES DETAIL (Erweiterte Tests)

### 22.1 Audio Track Picker

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 22.1.1 | Audio-Tracks anzeigen | Audio-Track-Panel auf SeriesDetail | Alle extrahierten Audio-Tracks mit Codec, Sprache, Stream-Index | ⏳ |
| 22.1.2 | Primären Track wählen | Track aus Dropdown wählen | Gewählter Track als Sync-Referenz gesetzt | ⏳ |
| 22.1.3 | Mehrsprachige Tracks | Serie mit DE+EN-Audio | Beide Tracks aufgelistet, korrekte ISO-639-1 Anzeige | ⏳ |

### 22.2 Fansub Preferences Panel

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 22.2.1 | Panel öffnen | Fansub-Prefs-Tab | Eingabefelder für Preferred/Excluded Groups | ⏳ |
| 22.2.2 | Bevorzugte Gruppen | Kommagetrennte Liste eingeben | Gespeichert | ⏳ |
| 22.2.3 | Ausgeschlossene Gruppen | Kommagetrennte Liste eingeben | Gespeichert | ⏳ |
| 22.2.4 | Bonus-Punkte Slider | Slider auf 20 (Standard) | Wert korrekt angezeigt | ⏳ |
| 22.2.5 | Slider anpassen | Slider ziehen (0–100) | Wert ändert sich | ⏳ |
| 22.2.6 | Einstellungen speichern | "Save"-Button | 🔗 Prefs gespeichert, Toast | ⏳ |
| 22.2.7 | Einstellungen zurücksetzen | "Reset"-Button | Standardwerte wiederhergestellt | ⏳ |

### 22.3 Sync Controls (Alle Modi)

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 22.3.1 | "Offset"-Modus | Sync-Controls öffnen, "Offset"-Tab | Millisekunden-Eingabefeld | ⏳ |
| 22.3.2 | Offset manuell eingeben | ms-Wert eingeben (z.B. -500) | Alle Cues um diesen Betrag verschoben | ⏳ |
| 22.3.3 | "Speed"-Modus | "Speed"-Tab | Geschwindigkeitsfaktor-Eingabe (z.B. 1.001) | ⏳ |
| 22.3.4 | "Framerate"-Modus | "Framerate"-Tab | FPS-Dropdown (23.976, 24, 25, 29.97, 30) | ⏳ |
| 22.3.5 | Framerate konvertieren | Von 23.976 zu 25 wählen | Timestamps korrekt umgerechnet | ⏳ |
| 22.3.6 | "Chapter"-Modus | "Chapter"-Tab | Kapitel-Bereich-Selektor | ⏳ |
| 22.3.7 | Offset auf Kapitelbereich | Kapitel wählen + Offset | Nur Cues in diesem Kapitelbereich verschoben | ⏳ |

### 22.4 Track Panel (Eingebettete Tracks)

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 22.4.1 | Track-Liste laden | Track-Panel öffnen | Alle eingebetteten Untertitel-Streams aufgelistet | ⏳ |
| 22.4.2 | Stream-Index anzeigen | Track-Eintrag | Stream-Index (z.B. #0:3) sichtbar | ⏳ |
| 22.4.3 | Track extrahieren | "Extract"-Button auf Track | 🔗 Extraktion gestartet → Toast | ⏳ |
| 22.4.4 | Format-Konversion | Track-Extraktion mit ASS-Ziel | ASS-Datei erstellt | ⏳ |

---

## 23. WANTED — ERGÄNZUNGEN

### 23.1 Subtitle Cleanup Modal (SubtitleCleanupModal)

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 23.1.1 | Modal öffnen | "Cleanup Sidecars" in Batch-Aktionen | SubtitleCleanupModal öffnet mit Datei-Liste | ⏳ |
| 23.1.2 | Datei-Liste anzeigen | Modal betrachten | Nicht-Zielsprachen-Sidecar-Dateien aufgelistet | ⏳ |
| 23.1.3 | Sprach-Checkboxen | Checkboxen pro Sprache | Einzelne Sprachen aus/abwählen | ⏳ |
| 23.1.4 | "Select Non-Target Languages" | Bulk-Button | Alle Nicht-Zielsprachen markiert | ⏳ |
| 23.1.5 | Dry-Run-Toggle | Toggle aktivieren | Preview ohne echte Löschung | ⏳ |
| 23.1.6 | Byte-Count Preview | Dry-Run-Ergebnis | "X MB would be freed" angezeigt | ⏳ |
| 23.1.7 | Löschen bestätigen | "Delete Selected"-Button | 🔗 `cleanupSidecars()` → Dateien gelöscht | ⏳ |
| 23.1.8 | Modal schließen ohne Aktion | X-Button | Keine Änderungen | ⏳ |

### 23.2 OCR Extraction (OCRExtractor.tsx)

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 23.2.1 | OCR-Extraktion starten | "OCR Extract"-Option auf Wanted-Item | OCRExtractor-Dialog öffnet | ⏳ |
| 23.2.2 | Preview-Frame generieren | OCR-Dialog geöffnet | Vorschau-Frame mit Timestamp sichtbar | ⏳ |
| 23.2.3 | Sprache für OCR wählen | Sprach-Dropdown | Sprache ausgewählt | ⏳ |
| 23.2.4 | OCR-Fortschritt | OCR laufend | Fortschrittsbalken + "X/Y frames processed" | ⏳ |
| 23.2.5 | Qualitäts-Prozentsatz | OCR-Ergebnis | Erkennungsqualität in % angezeigt | ⏳ |
| 23.2.6 | Erfolgreiche Frames | Ergebnis-Zusammenfassung | "X frames successful" | ⏳ |
| 23.2.7 | OCR-Ergebnis speichern | "Save"-Button | Extrahierter Text als Untertiteldatei gespeichert | ⏳ |

---

## 24. DASHBOARD (Erweiterte Tests)

### 24.1 Drag-and-Drop Widget-Neuanordnung

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 24.1.1 | Edit-Modus aktivieren | "Edit Mode"-Button klicken | Drag-Handles an Widgets sichtbar, Cursor ändert sich | ⏳ |
| 24.1.2 | Widget verschieben | Widget per Drag umordnen | Widget an neue Position verschoben | ⏳ |
| 24.1.3 | Widget vergrößern | Resize-Handle ziehen | Widget nimmt mehr Platz ein | ⏳ |
| 24.1.4 | Widget verkleinern | Resize-Handle zurückziehen | Widget schrumpft | ⏳ |
| 24.1.5 | Layout speichern | Edit-Modus → "Save Layout" | Layout in localStorage gespeichert | ⏳ |
| 24.1.6 | Layout verwerfen | Edit-Modus → "Cancel" | Layout zurückgesetzt auf vorherigen Stand | ⏳ |
| 24.1.7 | Responsive Breakpoints | Viewport auf md (996px) | Layout passt sich an, Spalten reduzieren sich | ⏳ |
| 24.1.8 | Layout nach Reload | Layout ändern, Seite neu laden | Geändertes Layout bleibt erhalten | ⏳ |
| 24.1.9 | Hydrations-Guard | Seite laden mit gespeichertem Layout | Kein FOUC (Flash of Unstyled Content) | ⏳ |

---

## 25. SETTINGS (Erweiterte Tests)

### 25.1 Advanced Settings Context

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 25.1.1 | Advanced-Toggle | "Show Advanced Settings"-Toggle | Erweiterte Felder erscheinen | ⏳ |
| 25.1.2 | Advanced-Toggle persistent | Toggle aktivieren, Tab wechseln, zurück | Zustand bleibt aktiv | ⏳ |
| 25.1.3 | Advanced-Felder verbergen | Toggle deaktivieren | Erweiterte Felder verschwinden | ⏳ |

### 25.2 Lazy-geladene Tabs

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 25.2.1 | Tab-Skeleton | Ersten Tab-Wechsel beobachten | TabSkeleton-Animation kurz sichtbar vor Inhalt | ⏳ |
| 25.2.2 | Tab-Ladefehler | (JS-Fehler in Tab simulieren) | ErrorBoundary fängt Fehler ab, Fehlermeldung mit Retry | ⏳ |

### 25.3 Provider Capabilities Warning

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 25.3.1 | Capability-Warnung | Provider konfigurieren der Feature X nicht unterstützt | CapabilityWarningModal erscheint | ⏳ |
| 25.3.2 | Warnung bestätigen | "Proceed Anyway" klicken | Konfiguration gespeichert, Warnung geschlossen | ⏳ |
| 25.3.3 | Warnung abbrechen | "Go Back" klicken | Konfiguration verworfen | ⏳ |

---

## 26. GLOBAL FEATURES (Erweiterte Tests)

### 26.1 Language Switcher Details

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 26.1.1 | Browser-Sprache Fallback | Ohne localStorage-Eintrag laden | Sprache richtet sich nach Browser-Sprache | ⏳ |
| 26.1.2 | localStorage-Key `i18nextLng` | Sprache wählen, DevTools → Application → Storage | Key gesetzt | ⏳ |
| 26.1.3 | Hover-Farb-Transition | Über Language-Button hovern | Farbe ändert sich smoothly (onMouseEnter/Leave) | ⏳ |

### 26.2 Theme Switcher Details

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 26.2.1 | System-Preference Detection | System auf Dark Mode, ohne manuelle Wahl | Dark Mode automatisch aktiv | ⏳ |
| 26.2.2 | localStorage Key `sublarr-theme` | Theme wählen, DevTools → Storage | Key `sublarr-theme` = `"dark"` / `"light"` | ⏳ |
| 26.2.3 | CSS Custom Properties | Dark Mode aktiv, DevTools → Computed | `--bg-base`, `--text-primary` etc. wechseln | ⏳ |

### 26.3 Global Search (Erweitert)

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 26.3.1 | Letzte Suchen anzeigen | Modal öffnen ohne Eingabe | "Recent searches" Liste | ⏳ |
| 26.3.2 | Ergebnis-Gruppierung | Suche mit Treffern in Series+Episodes | Ergebnisse in Gruppen "Series" / "Episodes" | ⏳ |
| 26.3.3 | Lade-Zustand | Langsame API: während Suche | Lade-Spinner oder Skeleton in Ergebnisliste | ⏳ |
| 26.3.4 | Pfeil-Navigation | `↑` / `↓` in Ergebnisliste | Auswahl bewegt sich, Enter navigiert | ⏳ |

### 26.4 QuickActions FAB (Erweitert)

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 26.4.1 | Menü-Animation | FAB klicken | Smooth Aufklapp-Animation | ⏳ |
| 26.4.2 | Keyboard-Shortcut im Menü | FAB-Menü betrachten | Tastenkürzel-Hints sichtbar | ⏳ |
| 26.4.3 | Außerhalb klicken | Menü offen, außerhalb klicken | Menü schließt | ⏳ |

---

## 27. STATE MANAGEMENT & PERSISTENZ (Details)

### 27.1 localStorage Keys

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 27.1.1 | `library_view_mode` | View wechseln, DevTools → Storage | Key = `"grid"` oder `"table"` | ⏳ |
| 27.1.2 | Ungültiger localStorage-Wert | `library_view_mode` manuell auf `"invalid"` setzen | Fallback auf Default (grid) | ⏳ |
| 27.1.3 | `sublarr_api_key` | API-Key in Settings setzen | Key in localStorage gespeichert | ⏳ |
| 27.1.4 | Dashboard-Layout pro Breakpoint | Layout bei lg und md separat speichern | Unterschiedliche Layouts bei verschiedenen Viewports | ⏳ |

### 27.2 Selection Store

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 27.2.1 | Seitenübergreifende Selektion | Items wählen, Seite wechseln, zurück | Selektion bleibt erhalten | ⏳ |
| 27.2.2 | Clear bei Navigation | Items wählen, zu anderer Hauptseite navigieren | Selektion wird gecleart | ⏳ |

---

## 28. FEHLERSZENARIEN & EDGE CASES

### 28.1 Netzwerk-Fehler

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 28.1.1 | Backend nicht erreichbar | Backend stoppen, Seite laden | Fehlermeldung "Could not connect" statt endlosem Spinner | ⏳ |
| 28.1.2 | 403 Forbidden | Datei außerhalb Media-Pfad anfordern | 403-Fehlermeldung in UI | ⏳ |
| 28.1.3 | 409 Conflict | Editor: extern geänderte Datei speichern | "File modified externally"-Dialog | ⏳ |
| 28.1.4 | Timeout bei langer Operation | Langsame Translation simulieren | Timeout-Fehlermeldung nach X Sekunden | ⏳ |
| 28.1.5 | Malformed API Response | Fehlerhafte JSON-Antwort | Generische Fehlermeldung, kein White-Screen | ⏳ |

### 28.2 Leere Zustände

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 28.2.1 | Leere Library | Library ohne Serien | "No series found. Configure Sonarr/Radarr"-Nachricht | ⏳ |
| 28.2.2 | Leere Wanted-Liste | Alle Subs vorhanden | "All subtitles found"-Nachricht | ⏳ |
| 28.2.3 | Leere Activity | Keine Jobs | "No translation jobs"-Nachricht | ⏳ |
| 28.2.4 | Leere History | Keine Downloads | "No download history"-Nachricht | ⏳ |
| 28.2.5 | Leere Logs | Keine Log-Einträge | "No log entries"-Nachricht | ⏳ |
| 28.2.6 | Search 0 Treffer | Globale Suche ohne Ergebnis | "No results for '...'" | ⏳ |
| 28.2.7 | Health Check: kein Problem | Perfekte Untertiteldatei prüfen | "No issues found ✓" | ⏳ |

### 28.3 Datei-Edge Cases

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 28.3.1 | Große Datei (>10MB) | Sehr große ASS-Datei öffnen | Editor lädt (evtl. mit Warnung), kein Freeze | ⏳ |
| 28.3.2 | Leere Untertiteldatei | 0-byte SRT öffnen | Leerer Editor, keine Crash | ⏳ |
| 28.3.3 | Fehlende Datei | Gelöschte Datei editieren wollen | 404-Fehlermeldung, kein Crash | ⏳ |

---

## 29. WEBSOCKET (Erweiterte Tests)

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 29.1 | WS-Verbindungsaufbau | Seite laden, DevTools → Network → WS | Socket.IO-Handshake sichtbar | ⏳ |
| 29.2 | Auto-Reconnect | WS-Verbindung unterbrechen (DevTools offline) | Automatischer Reconnect nach Wiederherstellung | ⏳ |
| 29.3 | Event-Handler Cleanup | Komponente unmounten (Tab wechseln) | Keine Event-Handler-Memory-Leaks (DevTools Memory) | ⏳ |
| 29.4 | `batch_extract_progress` Payload | Batch-Extract starten | `{current, total, succeeded, failed, current_item}` korrekt verarbeitet | ⏳ |
| 29.5 | `config_updated` Event | Config extern ändern | TanStack-Query-Cache invalidiert, frische Daten | ⏳ |
| 29.6 | `retranslation_completed` | Re-translation-Batch starten | Toast "Retranslation complete: X succeeded, Y failed" | ⏳ |

---

## 30. BARRIEREFREIHEIT (Erweiterte Tests)

### 30.1 ARIA-Attribute Details

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 30.1.1 | Icon-Button Labels | Screen-Reader auf Icon-Buttons | `aria-label` vorgelesen (z.B. "Close", "Search", "Delete") | ⏳ |
| 30.1.2 | `aria-labelledby` in Modal | Modal öffnen, DOM inspizieren | `aria-labelledby` auf Dialog-div zeigt auf `<h2>`-ID | ⏳ |
| 30.1.3 | `autoFocus` auf Close-Button | Modal öffnen, Tab-Fokus prüfen | Erster Fokus auf Close-Button | ⏳ |
| 30.1.4 | Fokus-Trap im Modal | Modal offen, Tab durchklicken | Fokus verlässt Modal nicht | ⏳ |
| 30.1.5 | Fokus-Rückkehr nach Modal | Modal schließen | Fokus kehrt zum auslösenden Button zurück | ⏳ |
| 30.1.6 | Live-Region Updates | Toast erscheint | Screen-Reader kündigt Toast an (`aria-live`) | ⏳ |

### 30.2 Tastatur-Bedienbarkeit

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 30.2.1 | Tab-Reihenfolge konsistent | Tab durch gesamte Seite | Logische, visuelle Reihenfolge | ⏳ |
| 30.2.2 | Fokus sichtbar | Tab-Fokus durch UI | Deutlicher Fokus-Ring auf allen interaktiven Elementen | ⏳ |
| 30.2.3 | Dropdown per Tastatur | Dropdown mit Enter öffnen, Pfeil navigieren, Enter wählen | Vollständig ohne Maus bedienbar | ⏳ |
| 30.2.4 | Dateitabelle per Tastatur | Tabelle per Tab navigieren | Zeilen fokussierbar, Aktionen erreichbar | ⏳ |

---

## 31. PERFORMANCE (Erweiterte Tests)

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 31.1 | Code-Split Laden | DevTools → Network, Providers-Tab öffnen | `ProvidersTab-[hash].js` chunk wird geladen | ⏳ |
| 31.2 | Suspense-Skeleton bei Tab | Ersten Tab-Load beobachten | Kurzes Skeleton sichtbar vor Inhalt | ⏳ |
| 31.3 | Virtual-Scrolling Library | Library-Tabelle mit 200+ Serien | Nur sichtbare Zeilen im DOM (DevTools → Elements) | ⏳ |
| 31.4 | Virtual-Scrolling Wanted | Wanted-Liste mit 100+ Items | Nur sichtbare Rows im DOM | ⏳ |
| 31.5 | Query Cache Invalidation | Mutationen ausführen | Nur betroffene Queries refetchen, nicht alle | ⏳ |
| 31.6 | Stale-While-Revalidate | Seite wechseln, zurückkommen | Gecachte Daten sofort sichtbar, dann frische Daten | ⏳ |
| 31.7 | Keep-Previous-Data | Zwischen Paginierungsseiten wechseln | Alte Daten sichtbar während neue laden | ⏳ |

---

---

## 32. SETTINGS — FIELD-LEVEL TESTS (Vollständig)

> Abschnitt 9 enthielt nur Tab-Ebenen-Tests. Hier sind alle Felder, Toggles, Buttons und Zustände auf Feldebene.

### 32.1 Security Tab (Vollständig)

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 32.1.1 | "Require Login"-Toggle aktivieren | Toggle auf ON | Auth aktiviert, Passwort-Änderungs-Card erscheint | ⏳ |
| 32.1.2 | "Require Login"-Toggle deaktivieren | Toggle auf OFF | Card verschwindet, kein Login mehr nötig | ⏳ |
| 32.1.3 | Passwort-Sichtbarkeit umschalten | Eye-Icon in einem PW-Feld | Alle drei Passwortfelder wechseln zwischen `type=password` und `type=text` | ⏳ |
| 32.1.4 | "Change Password" — alle Felder leer | Button anklicken ohne Eingabe | Button disabled, kein API-Call | ⏳ |
| 32.1.5 | Min-Länge Passwort | Neues Passwort < 4 Zeichen eingeben | Validierungsfehler oder Button disabled | ⏳ |
| 32.1.6 | Passwörter stimmen nicht überein | Neues PW ≠ Confirm PW | Inline-Fehlermeldung "Passwords do not match" | ⏳ |
| 32.1.7 | Falsches aktuelles Passwort | Falsches PW → "Change Password" | 🔗 API-Fehler → Inline-Meldung "Current password incorrect" | ⏳ |
| 32.1.8 | Passwort erfolgreich geändert | Korrekte Eingabe → "Change Password" | 🔗 `changePassword()` → Toast "Password changed" | ⏳ |
| 32.1.9 | Ladestate während Änderung | Button klicken, Netzwerk verlangsamen | Button zeigt "Saving…", disabled | ⏳ |

### 32.2 Providers Tab (Vollständig)

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 32.2.1 | "Configured" / "Marketplace" Tab-Wechsel | Tabs klicken | Inhalt wechselt | ⏳ |
| 32.2.2 | Provider-Zähler-Text | Tab aufrufen | "X aktiv / Y konfiguriert" korrekt | ⏳ |
| 32.2.3 | "Clear Cache (Alle)"-Button | Button klicken | 🔗 `clearProviderCache()` → Toast "Cache cleared" | ⏳ |
| 32.2.4 | Versteckter Provider wiederherstellen | "+" Add-Provider-Button | Modal mit versteckten Providern öffnet | ⏳ |
| 32.2.5 | Provider aus versteckter Liste hinzufügen | Provider wählen, bestätigen | Provider in Grid sichtbar, enabled | ⏳ |
| 32.2.6 | Provider verstecken (Remove) | Remove-Button auf Kachel | Kachel verschwindet, Provider zu `providers_hidden` hinzugefügt | ⏳ |
| 32.2.7 | Priority-Anzeige | Grid betrachten | Nummern 1, 2, 3... auf Kacheln | ⏳ |
| 32.2.8 | "Move Up"-Button in EditModal | Modal öffnen, "Move Up" klicken | Provider steigt in Priorität (Zahl sinkt) | ⏳ |
| 32.2.9 | "Move Down"-Button | "Move Down" klicken | Provider sinkt in Priorität | ⏳ |
| 32.2.10 | Cache-Count-Anzeige | Kachel betrachten | Gecachte Ergebnisse-Zahl sichtbar | ⏳ |
| 32.2.11 | "Clear Cache (Einzeln)" in Modal | Cache-Clear-Button im EditModal | 🔗 `clearProviderCache(name)` → Toast | ⏳ |
| 32.2.12 | "Re-enable" bei Circuit-Broken | Provider wurde circuit-broken | "Re-enable"-Button sichtbar, Klick reaktiviert Provider | ⏳ |
| 32.2.13 | PW-Feld Show/Hide | Eye-Icon in ProviderEditModal | API-Key zwischen Sternchen und Klartext | ⏳ |
| 32.2.14 | Sentinel `***configured***` | Gespeicherten Key bearbeiten | Feld zeigt "(configured)" als Placeholder | ⏳ |
| 32.2.15 | Pflichtfeld-Validierung | Pflichtfeld leeren, Test klicken | Fehler-Highlight, kein API-Call | ⏳ |
| 32.2.16 | Anti-Captcha Backend "Disabled" | Backend-Dropdown betrachten | API-Key-Feld NICHT sichtbar | ⏳ |
| 32.2.17 | Anti-Captcha Backend aktivieren | Dropdown → "Anti-Captcha.com" | API-Key-Feld erscheint | ⏳ |
| 32.2.18 | Anti-Captcha Key eingeben | Feld ausfüllen, Speichern | 🔗 Gespeichert | ⏳ |
| 32.2.19 | Modal Escape/Cancel | Escape oder X | Modal schließt, keine Änderung | ⏳ |

### 32.3 Translation Tab (Vollständig)

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 32.3.1 | Backend-Cards laden | Tab aufrufen | Je eine Card pro Backend (Ollama, OpenAI, Claude, etc.) | ⏳ |
| 32.3.2 | "Configured"-Badge | Konfigurierten Backend betrachten | Grünes "Configured"-Badge | ⏳ |
| 32.3.3 | "Not Configured"-Badge | Unkonfigurierten Backend | Graues "Not configured"-Badge | ⏳ |
| 32.3.4 | GPU-Badge | Backend mit GPU-Support betrachten | GPU-Badge sichtbar | ⏳ |
| 32.3.5 | Backend-Card expandieren | Chevron/Card-Header klicken | Config-Felder erscheinen | ⏳ |
| 32.3.6 | Backend-Card kollabieren | Erneut klicken | Felder verschwinden | ⏳ |
| 32.3.7 | Backend-Feld: Text-Input | Text-Feld ausfüllen | Eingabe gespeichert | ⏳ |
| 32.3.8 | Backend-Feld: PW Show/Hide | Eye-Icon bei API-Key-Feld | Klartext ↔ Sternchen | ⏳ |
| 32.3.9 | Help-Text pro Feld | Feld betrachten | Kleine graue Beschreibung unter Feld | ⏳ |
| 32.3.10 | "Test Backend"-Button | Test-Button klicken | 🔗 `testBackendConfig()` → Status-Badge (grün/rot + Meldung) | ⏳ |
| 32.3.11 | Ladestate beim Testen | Test klicken, langsame API | "testing"-State, Spinner | ⏳ |
| 32.3.12 | "Save"-Button (pro Backend) | Config ändern, Save klicken | 🔗 `saveBackendConfig()` → Toast | ⏳ |
| 32.3.13 | Whisper Enable-Toggle | Toggle aktivieren | 🔗 `localConfig.whisper_enabled = true` gespeichert | ⏳ |
| 32.3.14 | Whisper Active Backend | Dropdown wählen | Gespeichert | ⏳ |
| 32.3.15 | Max Concurrent Jobs | Zahl eingeben (1–4) | Werte außerhalb Bereich werden geclamped | ⏳ |
| 32.3.16 | Max Concurrent Jobs < 1 | 0 eingeben | Wird auf 1 gesetzt (Math.max clamp) | ⏳ |
| 32.3.17 | Max Concurrent Jobs > 4 | 5 eingeben | Wird auf 4 gesetzt (Math.min clamp) | ⏳ |
| 32.3.18 | Fallback Min Score | 0–100 eingeben | Gespeichert | ⏳ |
| 32.3.19 | "Save Whisper Config"-Button | Button klicken | 🔗 `saveWhisperConfig(localConfig)` → Toast | ⏳ |
| 32.3.20 | Stats-Zusammenfassung | Nach Jobs betrachten | Total, Avg-Processing-Time, Succeeded/Failed angezeigt | ⏳ |

### 32.4 Whisper Tab (Vollständig)

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 32.4.1 | Separate Whisper-Tab-Cards | Tab öffnen | Separate Backend-Cards für Whisper-Backends | ⏳ |
| 32.4.2 | Modell-Tabelle (faster_whisper) | faster_whisper expandieren | Tabelle mit Modell-Namen und Dateigrößen | ⏳ |
| 32.4.3 | Whisper Stats | Nach Transkriptionsjobs | Activity-Icon + Statistiken sichtbar | ⏳ |
| 32.4.4 | Alle globalen Whisper-Felder | Global-Config-Card betrachten | Enable-Toggle, Active-Backend, Max-Jobs, Min-Score alle vorhanden | ⏳ |

### 32.5 Media Servers Tab (Vollständig)

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 32.5.1 | Zähler-Text | Tab aufrufen | "X media servers configured" oder "No media servers configured" | ⏳ |
| 32.5.2 | Add-Dropdown öffnen | "+" klicken | Dropdown mit Jellyfin/Emby/Plex/Kodi | ⏳ |
| 32.5.3 | Jellyfin hinzufügen | Jellyfin wählen | Neue Card mit Jellyfin-Feldern erscheint | ⏳ |
| 32.5.4 | Emby hinzufügen | Emby wählen | Emby-spezifische Felder | ⏳ |
| 32.5.5 | Plex hinzufügen | Plex wählen | Plex-spezifische Felder (x_plex_token) | ⏳ |
| 32.5.6 | Kodi hinzufügen | Kodi wählen | Kodi-spezifische Felder | ⏳ |
| 32.5.7 | Server-Card expandieren | Chevron klicken | Felder expandieren | ⏳ |
| 32.5.8 | Server-Name bearbeiten | Name-Input ändern | Gespeichert | ⏳ |
| 32.5.9 | PW-Feld Show/Hide | Eye-Icon bei PW/Token | Klartext ↔ Sternchen | ⏳ |
| 32.5.10 | Sentinel für Token | Gespeicherten Token betrachten | "(configured)" als Placeholder | ⏳ |
| 32.5.11 | Path Mapping eingeben | Monospace-Feld ausfüllen (z.B. `/media:/data`) | Gespeichert im korrekten Format | ⏳ |
| 32.5.12 | "Enabled"-Toggle deaktivieren | Toggle auf OFF | Card-Opacity reduziert (0.7), Server inaktiv | ⏳ |
| 32.5.13 | "Enabled"-Toggle reaktivieren | Toggle auf ON | Opacity normal | ⏳ |
| 32.5.14 | "Test Connection" klicken | Button klicken | 🔗 `testMediaServer()` → Inline-Ergebnis "OK: ..." (grün) oder "Error: ..." (rot) | ⏳ |
| 32.5.15 | Test-Ladestate | Test klicken, langsame API | "testing"-Spinner sichtbar | ⏳ |
| 32.5.16 | "Save"-Button | Felder ändern, Save klicken | 🔗 Gespeichert → Toast | ⏳ |
| 32.5.17 | "Remove"-Button | Remove klicken | Bestätigungs-Dialog erscheint | ⏳ |
| 32.5.18 | Remove bestätigen | "Confirm" | Server-Card entfernt | ⏳ |
| 32.5.19 | Remove abbrechen | "Cancel" | Dialog schließt, Card bleibt | ⏳ |
| 32.5.20 | Mehrere Instanzen gleichen Typs | 2x Jellyfin hinzufügen | Beide Cards vorhanden, unabhängig konfigurierbar | ⏳ |
| 32.5.21 | Feld-Beschreibungen | Felder betrachten | Descriptions wie "Jellyfin Server URL" korrekt per Typ | ⏳ |

### 32.6 Automation/Events Tab (Vollständig)

#### 32.6.1 Shell Hooks

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 32.6.1.1 | Hook-Liste laden | Tab aufrufen | Hooks mit Name, Event-Badge, Status | ⏳ |
| 32.6.1.2 | "Add Hook"-Button | Button klicken | Hook-Formular erscheint | ⏳ |
| 32.6.1.3 | Hook Name eingeben | Name-Input | Gespeichert | ⏳ |
| 32.6.1.4 | Event-Dropdown Optionen | Dropdown öffnen | Alle verfügbaren Events aufgelistet | ⏳ |
| 32.6.1.5 | Script-Pfad eingeben | Monospace-Input | Gespeichert | ⏳ |
| 32.6.1.6 | Timeout-Feld validieren | Negative Zahl eingeben | Kein negativer Wert akzeptiert | ⏳ |
| 32.6.1.7 | "Create"-Button | Formular ausfüllen, Create | 🔗 Hook erstellt, in Liste erscheint | ⏳ |
| 32.6.1.8 | "Cancel"-Button | Formular offen, Cancel | Formular verschwindet, keine Änderung | ⏳ |
| 32.6.1.9 | Hook bearbeiten | "Edit"-Button | Formular mit bestehenden Werten | ⏳ |
| 32.6.1.10 | "Update"-Button | Bearbeiten → Update | 🔗 Hook aktualisiert, Toast | ⏳ |
| 32.6.1.11 | Hook testen | "Test"-Button | 🔗 Script ausgeführt, Ergebnis angezeigt | ⏳ |
| 32.6.1.12 | Hook Enable/Disable | Toggle | Hook aktiv/inaktiv, Badge ändert sich | ⏳ |
| 32.6.1.13 | Hook löschen | "Delete"-Button | Bestätigungs-Dialog → 🗑️ | ⏳ |
| 32.6.1.14 | Trigger-Zähler | Hook betrachten | "Triggered X times" sichtbar | ⏳ |
| 32.6.1.15 | Letzter Trigger | Hook betrachten | Timestamp "Last triggered: ..." | ⏳ |

#### 32.6.2 Outgoing Webhooks

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 32.6.2.1 | Webhook-Liste laden | Tab aufrufen | Webhooks mit Name, Event, letztem HTTP-Status | ⏳ |
| 32.6.2.2 | "Add Webhook"-Button | Button klicken | Webhook-Formular erscheint | ⏳ |
| 32.6.2.3 | Webhook Name | Name-Input | Gespeichert | ⏳ |
| 32.6.2.4 | Event "All Events" wählen | Dropdown → "All Events" | Webhook triggert bei allen Events | ⏳ |
| 32.6.2.5 | Spezifisches Event wählen | Dropdown → spezifisches Event | Nur bei diesem Event | ⏳ |
| 32.6.2.6 | Webhook URL eingeben | URL-Input | Gespeichert | ⏳ |
| 32.6.2.7 | Secret (HMAC) eingeben | Passwort-Feld | Gespeichert maskiert | ⏳ |
| 32.6.2.8 | Secret Show/Hide | Eye-Icon | Klartext ↔ Sternchen | ⏳ |
| 32.6.2.9 | Retry-Count Feld | Zahl eingeben | Gespeichert | ⏳ |
| 32.6.2.10 | Letzter HTTP-Status-Badge | Nach Trigger | Status-Code (200, 404, 500) als Badge | ⏳ |
| 32.6.2.11 | Consecutive Failures | Webhook betrachten | Fehleranzahl sichtbar | ⏳ |
| 32.6.2.12 | Webhook bearbeiten | "Edit" | Formular mit Werten | ⏳ |
| 32.6.2.13 | Webhook testen | "Test" | 🔗 HTTP POST gesendet, Status angezeigt | ⏳ |
| 32.6.2.14 | Webhook Enable/Disable | Toggle | Aktiv/Inaktiv | ⏳ |
| 32.6.2.15 | Webhook löschen | "Delete" | Bestätigung → 🗑️ | ⏳ |

#### 32.6.3 Execution Log

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 32.6.3.1 | Log-Tabelle laden | Tab aufrufen (nach Trigger) | Zeit, Event, Typ-Badge, Status-Icon, Dauer | ⏳ |
| 32.6.3.2 | Log-Eintrag expandieren | Zeile klicken | Detail-Panel: stdout, stderr, exit_code | ⏳ |
| 32.6.3.3 | Detail-Panel Monospace | Expandierter Eintrag | stdout/stderr in Monospace-Font | ⏳ |
| 32.6.3.4 | "Clear Logs"-Button | Button klicken | Bestätigungs-Dialog → 🗑️ Alle Logs gelöscht | ⏳ |
| 32.6.3.5 | Leerer Log-Zustand | Ohne Logs | "No execution logs yet." | ⏳ |

### 32.7 Notifications Tab (Vollständig)

#### 32.7.1 Notification Toggles & URLs

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 32.7.1.1 | Apprise-URL-Textarea | URL eingeben (z.B. `tgram://...`) | Gespeichert | ⏳ |
| 32.7.1.2 | Mehrere URLs (mehrzeilig) | Mehrere Zeilen | Alle URLs gespeichert | ⏳ |
| 32.7.1.3 | "Test Notification"-Button | Button klicken | 🔗 `testNotification()` → Toast "Test sent" | ⏳ |
| 32.7.1.4 | "Notify on Download"-Toggle | Toggle klicken | Aktiv/Inaktiv, Farbe ändert sich | ⏳ |
| 32.7.1.5 | "Notify on Upgrade"-Toggle | Toggle klicken | Aktiv/Inaktiv | ⏳ |
| 32.7.1.6 | "Notify on Batch Complete" | Toggle | Aktiv/Inaktiv | ⏳ |
| 32.7.1.7 | "Notify on Error" | Toggle | Aktiv/Inaktiv | ⏳ |
| 32.7.1.8 | "Notify Manual Actions" | Toggle | Aktiv/Inaktiv | ⏳ |
| 32.7.1.9 | Toggle-Farb-Feedback | Toggle aktiv/inaktiv | Farbe wechselt (aktiv = accent, inaktiv = grey) | ⏳ |

#### 32.7.2 Templates

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 32.7.2.1 | Template-Liste laden | Tab betrachten | Templates mit Name und Event-Type-Badge | ⏳ |
| 32.7.2.2 | "New Template"-Button | Button klicken | TemplateEditor-Formular erscheint | ⏳ |
| 32.7.2.3 | Template-Name eingeben | Input | Gespeichert | ⏳ |
| 32.7.2.4 | Title-Template eingeben | Input mit `{{series}}` | Variable als Text akzeptiert | ⏳ |
| 32.7.2.5 | Body-Template eingeben | Textarea mit Variablen | Gespeichert | ⏳ |
| 32.7.2.6 | Event-Type-Dropdown | Dropdown wählen | Korrektes Event gespeichert | ⏳ |
| 32.7.2.7 | Service-Name | Input | Optional, gespeichert | ⏳ |
| 32.7.2.8 | "Enabled"-Checkbox | Checkbox | Aktiviert/Deaktiviert | ⏳ |
| 32.7.2.9 | TemplatePreview | Felder ausfüllen | Preview-Panel zeigt gerenderten Inhalt | ⏳ |
| 32.7.2.10 | "Create"-Button | Formular ausfüllen | 🔗 Template erstellt, in Liste | ⏳ |
| 32.7.2.11 | Template bearbeiten | "Edit"-Button | Formular mit bestehenden Werten | ⏳ |
| 32.7.2.12 | "Save"-Button | Änderung → Save | 🔗 Aktualisiert, Toast | ⏳ |
| 32.7.2.13 | Template löschen | "Delete" | Bestätigung → 🗑️ | ⏳ |

#### 32.7.3 Quiet Hours

| # | Funktion | Wie testen | Erwartetes Ergebnis |--------|--------|
|---|---------|------------|---------------------|--------|
| 32.7.3.1 | "Add Quiet Hours"-Button | Button klicken | QuietHoursEditor-Formular | ⏳ |
| 32.7.3.2 | Name eingeben | Input | Gespeichert | ⏳ |
| 32.7.3.3 | Start-Zeit (HH:MM) | Zeit-Input | 24-Stunden-Format | ⏳ |
| 32.7.3.4 | End-Zeit (HH:MM) | Zeit-Input | Gespeichert | ⏳ |
| 32.7.3.5 | Wochentag-Checkboxen | 7 Checkboxen (Mo–So) | Einzelne Tage an/abwählen | ⏳ |
| 32.7.3.6 | Exception Events | Multi-Select | Ausgewählte Events auch in Quiet Hours gesendet | ⏳ |
| 32.7.3.7 | "Enabled"-Checkbox | Checkbox | Quiet-Hours aktiv/inaktiv | ⏳ |
| 32.7.3.8 | Zeit-Anzeige in Liste | Config betrachten | Monospace-Zeitbereich "22:00 – 08:00" | ⏳ |
| 32.7.3.9 | Quiet Hours löschen | "Delete" | Bestätigung → 🗑️ | ⏳ |

#### 32.7.4 Notification History

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 32.7.4.1 | History laden | Tab aufrufen (nach Notifications) | Einträge mit Titel, Status, Event-Typ, Timestamp | ⏳ |
| 32.7.4.2 | Status "Sent"-Badge | Erfolgreicher Eintrag | Grünes "sent"-Badge | ⏳ |
| 32.7.4.3 | Status "Failed"-Badge | Fehlgeschlagener Eintrag | Rotes "failed"-Badge | ⏳ |
| 32.7.4.4 | Event-Filter-Dropdown | Dropdown → spezifisches Event | Nur Einträge dieses Events | ⏳ |
| 32.7.4.5 | "Resend"-Button | Button neben Eintrag | 🔗 `resend.mutate(id)` → Toast | ⏳ |
| 32.7.4.6 | Pagination Prev/Next | Buttons | Entsprechende Seite | ⏳ |
| 32.7.4.7 | Leerer History-Zustand | Ohne History | "No notification history yet." | ⏳ |

#### 32.7.5 Event Filter

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 32.7.5.1 | Event-Filter Section öffnen | Collapsible aufklappen | "Exclude Events" + "Include Only" Bereiche | ⏳ |
| 32.7.5.2 | Event ausschließen | "Exclude Events" → Event-Button | Button rot, dieses Event wird nicht gesendet | ⏳ |
| 32.7.5.3 | Ausschluss aufheben | Roten Button erneut klicken | Normal-Farbe, Event wieder aktiv | ⏳ |
| 32.7.5.4 | "Include Only" aktivieren | Event-Button in "Include Only" | Grünes Button, NUR dieses Event gesendet | ⏳ |
| 32.7.5.5 | Help-Text | Section betrachten | "If set, only these events generate notifications" | ⏳ |

### 32.8 Integrations Tab (Vollständig)

#### 32.8.1 Bazarr Migration

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 32.8.1.1 | DB-Pfad-Input | Monospace-Input ausfüllen | Pfad gespeichert | ⏳ |
| 32.8.1.2 | "Generate Report"-Button leer | Leeres Feld, Button klicken | Button disabled, kein Call | ⏳ |
| 32.8.1.3 | "Generate Report"-Button | Pfad eingeben, klicken | 🔗 `mappingReport.mutate(dbPath)` → Ergebnis | ⏳ |
| 32.8.1.4 | Compatibility-Card | Report-Ergebnis betrachten | Bazarr-Version, Schema-Version angezeigt | ⏳ |
| 32.8.1.5 | Migration-Summary | Report betrachten | Grid: Profiles, Blacklist, Shows, Movies, History Counts | ⏳ |
| 32.8.1.6 | Tables-Inventory expandieren | Collapsible öffnen | Tabellennamen + Zeilen-/Spalten-Zähler | ⏳ |
| 32.8.1.7 | Warnings-Anzeige | Report mit Warnungen | Amber-Box mit AlertTriangle-Icon + Text | ⏳ |
| 32.8.1.8 | Navigations-Hinweis | Report betrachten | "Settings > API Keys > Bazarr Migration" Text | ⏳ |

#### 32.8.2 Compatibility Check

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 32.8.2.1 | Section öffnen | Collapsible aufklappen | Target-Dropdown, Video-Path, Subtitle-Paths-Textarea | ⏳ |
| 32.8.2.2 | Target "Plex" wählen | Dropdown → Plex | Plex-spezifische Validierung | ⏳ |
| 32.8.2.3 | Target "Kodi" wählen | Dropdown → Kodi | Kodi-spezifische Validierung | ⏳ |
| 32.8.2.4 | Video-Path eingeben | Input | Gespeichert | ⏳ |
| 32.8.2.5 | Mehrere Subtitle-Pfade | Textarea (mehrzeilig) | Alle Pfade gespeichert | ⏳ |
| 32.8.2.6 | "Run Check" klicken | Button | 🔗 Ergebnisse laden | ⏳ |
| 32.8.2.7 | Summary-Bar anzeigen | Ergebnis betrachten | "X / Y compatible" | ⏳ |
| 32.8.2.8 | Grüne Result-Card | Kompatibler Sub | CheckCircle grün + Pfad | ⏳ |
| 32.8.2.9 | Rote Result-Card | Inkompatibler Sub | XCircle rot + Issues-Liste | ⏳ |
| 32.8.2.10 | Warnings in Card | Sub mit Warnings | Gelber Text | ⏳ |
| 32.8.2.11 | Recommendations | Card betrachten | Accent-Color-Text | ⏳ |

#### 32.8.3 Extended Health Diagnostics

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 32.8.3.1 | Section öffnen | Collapsible aufklappen | "Run Diagnostics"-Button | ⏳ |
| 32.8.3.2 | "Run Diagnostics" klicken | Button | 🔗 Health-Check alle Services → Cards laden | ⏳ |
| 32.8.3.3 | Connected-Badge | Erreichbarer Service | Grünes "Connected"-Badge | ⏳ |
| 32.8.3.4 | Disconnected-Badge | Nicht erreichbarer Service | Rotes "Disconnected"-Badge | ⏳ |
| 32.8.3.5 | Library-Access-Daten | Service betrachten | Series/Movies/Libraries Counts | ⏳ |
| 32.8.3.6 | Webhook-Status | Service betrachten | "Webhook configured: Yes/No" | ⏳ |
| 32.8.3.7 | Health Issues | Service mit Problemen | Gelbe/Rote Issue-Liste | ⏳ |
| 32.8.3.8 | "No issues found ✓" | Gesunder Service | Grüner Text | ⏳ |

#### 32.8.4 Export Configuration

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 32.8.4.1 | Section öffnen | Collapsible aufklappen | Format-Dropdown, Secrets-Checkbox, Export-Buttons | ⏳ |
| 32.8.4.2 | Format "Bazarr Compatible" | Dropdown wählen | Bazarr-spezifische Hinweistexte | ⏳ |
| 32.8.4.3 | Format "Generic JSON" | Dropdown wählen | Allgemeine Export-Optionen | ⏳ |
| 32.8.4.4 | "Include Secrets" deaktiviert | Checkbox OFF | Kein Warning angezeigt | ⏳ |
| 32.8.4.5 | "Include Secrets" aktivieren | Checkbox ON | Warning-Box "This will include API keys!" sichtbar | ⏳ |
| 32.8.4.6 | "Export"-Button | Button klicken | 🔗 `exportConfig.mutate()` → Datei-Download | ⏳ |
| 32.8.4.7 | "Export All Formats (ZIP)"-Button | Button klicken | 🔗 ZIP mit allen Formaten heruntergeladen | ⏳ |
| 32.8.4.8 | Help-Text pro Format | Format wählen | Format-spezifische Erklärung | ⏳ |

### 32.9 API Keys Tab (Vollständig)

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 32.9.1 | Service-Cards laden | Tab aufrufen | Karten pro Service (OpenSubtitles, OpenAI, etc.) | ⏳ |
| 32.9.2 | ShieldCheck-Icon | Alle Keys konfiguriert | Grünes ShieldCheck-Icon | ⏳ |
| 32.9.3 | ShieldAlert-Icon | Manche Keys fehlen | Gelbes ShieldAlert-Icon | ⏳ |
| 32.9.4 | Shield-Icon | Kein Key konfiguriert | Graues Shield-Icon | ⏳ |
| 32.9.5 | "Configured"-Badge pro Key | Gespeicherten Key betrachten | Grünes "configured"-Badge | ⏳ |
| 32.9.6 | "Missing"-Badge | Fehlenden Key betrachten | Rotes "missing"-Badge | ⏳ |
| 32.9.7 | Key maskiert anzeigen | Key konfiguriert | `••••••••` (Sternchen) | ⏳ |
| 32.9.8 | Key einblenden (Eye-Icon) | Eye-Icon klicken | Klartext des Keys angezeigt | ⏳ |
| 32.9.9 | Key ausblenden | Eye-Icon erneut | Sternchen wieder | ⏳ |
| 32.9.10 | "Edit/Set"-Button | Button klicken | Inline-Formular erscheint | ⏳ |
| 32.9.11 | Inline-Input ausfüllen | PW-Feld | Eintippen | ⏳ |
| 32.9.12 | Inline-Save (Checkmark) | Grüner Button | 🔗 Key gespeichert, Badge ändert sich | ⏳ |
| 32.9.13 | Inline-Cancel (X) | Grauer Button | Formular schließt, keine Änderung | ⏳ |
| 32.9.14 | "Test"-Button (testable Services) | Test klicken | 🔗 API-Verbindung geprüft, Status-Badge | ⏳ |
| 32.9.15 | Bazarr-Import-Dateitypen | Datei hochladen (.yaml, .yml, .ini, .db) | Alle Typen akzeptiert | ⏳ |
| 32.9.16 | Bazarr-Preview Warnings | Preview mit Warnungen | Amber-Box mit Warnungstext | ⏳ |
| 32.9.17 | Bazarr-Preview Config-Block | Preview betrachten | Code-Block mit key=value-Paaren, scrollbar | ⏳ |
| 32.9.18 | Bazarr-Preview Summary | Preview betrachten | "N config entries, M blacklist entries" | ⏳ |
| 32.9.19 | "Confirm Import"-Button | Preview → Confirm | 🔗 Keys importiert, Toast | ⏳ |
| 32.9.20 | "Cancel"-Button in Preview | Cancel | Modal schließt, nichts importiert | ⏳ |
| 32.9.21 | "Export Keys"-Button | Button klicken | 🔗 `exportKeys.mutate()` → ZIP-Download | ⏳ |
| 32.9.22 | "Import Keys"-Button | Datei hochladen | 🔗 `importKeys.mutate(file)` → Toast mit Anzahl | ⏳ |
| 32.9.23 | Export-Button Ladestate | Button klicken, langsam | Disabled während Export | ⏳ |

### 32.10 Advanced Tab (Vollständig)

#### 32.10.1 Language Profiles

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 32.10.1.1 | Profile-Liste laden | Tab aufrufen | Alle Profile mit Name, Sprachen, Backend | ⏳ |
| 32.10.1.2 | "Create Profile"-Button | "+" klicken | Formular erscheint | ⏳ |
| 32.10.1.3 | Profil-Name eingeben | Input | Gespeichert | ⏳ |
| 32.10.1.4 | Source-Language-Dropdown | Dropdown | Alle verfügbaren Sprachen | ⏳ |
| 32.10.1.5 | Target-Languages Multi-Select | Mehrere Sprachen wählen | Alle gespeichert | ⏳ |
| 32.10.1.6 | Translation-Backend | Dropdown | Gespeichert | ⏳ |
| 32.10.1.7 | Forced-Preference | Dropdown (disabled/separate/auto) | Gespeichert | ⏳ |
| 32.10.1.8 | "Set as Default"-Checkbox | Checkbox aktivieren | Profil wird Default, andere deselektiert | ⏳ |
| 32.10.1.9 | Profil bearbeiten | "Edit" | Formular mit Werten | ⏳ |
| 32.10.1.10 | Profil löschen | "Delete" | Bestätigung → 🗑️ | ⏳ |

#### 32.10.2 Watched Folders

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 32.10.2.1 | Folder-Liste laden | Tab aufrufen | Alle überwachten Ordner aufgelistet | ⏳ |
| 32.10.2.2 | "Add Folder"-Button | "+" klicken | Formular erscheint | ⏳ |
| 32.10.2.3 | Ordner-Pfad eingeben | Path-Input | Gespeichert | ⏳ |
| 32.10.2.4 | Profil zuweisen | Dropdown | Zugewiesenes Profil gespeichert | ⏳ |
| 32.10.2.5 | Scan-Interval | Zahl (Minuten) | Gespeichert | ⏳ |
| 32.10.2.6 | Folder bearbeiten | "Edit" | Formular | ⏳ |
| 32.10.2.7 | Folder löschen | "Delete" | Bestätigung → 🗑️ | ⏳ |

#### 32.10.3 Full Backups

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 32.10.3.1 | Backup-Zähler | Section betrachten | "X backups available" | ⏳ |
| 32.10.3.2 | "Create Full Backup" | Button klicken | 🔗 Backup erstellt, Liste aktualisiert | ⏳ |
| 32.10.3.3 | "Download Backup" | Button pro Backup | Backup-Datei heruntergeladen | ⏳ |
| 32.10.3.4 | "Restore Backup" | Datei hochladen | Bestätigungs-Dialog | ⏳ |
| 32.10.3.5 | Restore bestätigen | "Confirm Restore" | 🔗 Restore ausgeführt, Toast | ⏳ |

---

## 33. CLEANUP TAB (Komplett fehlend — neu)

> Dieser gesamte Tab war nicht im Testplan enthalten.

### 33.1 Disk Space Analyse

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 33.1.1 | Disk-Space-Widget | Tab aufrufen (nach Scan) | Balken mit used/total % | ⏳ |
| 33.1.2 | Leerer Zustand | Vor erstem Scan | "Run a scan to see disk space analysis" | ⏳ |

### 33.2 Deduplizierung

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 33.2.1 | "Scan for Duplicates" | Button klicken | 🔗 `startScan.mutate()` → Button disabled + "Scanning..." | ⏳ |
| 33.2.2 | Fortschrittsbalken | Scan laufend | Balken + "123 / 456" Counter | ⏳ |
| 33.2.3 | Duplikat-Gruppen anzeigen | Nach Scan | DedupGroupList mit Dateigruppen | ⏳ |
| 33.2.4 | "Behalten/Löschen" auswählen | Dateien in Gruppe markieren | Auswahl gespeichert | ⏳ |
| 33.2.5 | CleanupPreview öffnen | Aktionen wählen, Preview | Dry-Run-Ergebnis angezeigt | ⏳ |
| 33.2.6 | "Confirm Delete" | Button in Preview | 🔗 Duplikate gelöscht, Toast | ⏳ |
| 33.2.7 | "Cancel" in Preview | Button | Preview schließt, nichts gelöscht | ⏳ |
| 33.2.8 | Leerer Zustand | Keine Duplikate | "No duplicates found" | ⏳ |

### 33.3 Orphaned Subtitles

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 33.3.1 | "Scan for Orphaned" | Button klicken | 🔗 `orphanedScan.mutate()` → Ergebnis | ⏳ |
| 33.3.2 | Orphaned-Liste | Nach Scan | Dateipfad, Format-Badge, Dateigröße | ⏳ |
| 33.3.3 | Einzelne Datei wählen | Checkbox | Ausgewählt | ⏳ |
| 33.3.4 | Mehrere Dateien wählen | Mehrere Checkboxen | Batch-Auswahl | ⏳ |
| 33.3.5 | "Delete Selected" erscheint | Nach Auswahl | Button erscheint (error color) | ⏳ |
| 33.3.6 | "Delete Selected" klicken | Button | 🔗 `deleteOrphaned.mutate(paths)` → Gelöscht | ⏳ |
| 33.3.7 | Leerer Zustand | Keine Orphaned | "No orphaned subtitles found" | ⏳ |

### 33.4 Cleanup Rules

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 33.4.1 | Regel-Liste | Tab aufrufen | "X rules configured" + Regel-Liste | ⏳ |
| 33.4.2 | "Create Rule" | "+" klicken | Formular erscheint | ⏳ |
| 33.4.3 | Regel-Name | Input | Gespeichert | ⏳ |
| 33.4.4 | Regel-Typ | Dropdown (dedup/orphaned/old_backups) | Gespeichert | ⏳ |
| 33.4.5 | "Enabled"-Checkbox | Checkbox | Aktiv/Inaktiv | ⏳ |
| 33.4.6 | "Save Regel"-Button | Button | 🔗 Regel erstellt | ⏳ |
| 33.4.7 | "Cancel"-Button | Button | Formular schließt | ⏳ |
| 33.4.8 | Enable/Disable-Icon | Power/PowerOff-Icon klicken | Regel aktiv/inaktiv, Icon wechselt | ⏳ |
| 33.4.9 | "Run Now"-Button | Button neben Regel | 🔗 Regel wird ausgeführt, Toast | ⏳ |
| 33.4.10 | "Delete Regel" | Trash-Icon | Bestätigung → 🗑️ | ⏳ |
| 33.4.11 | Typ-Badge | Regel-Eintrag | Badge mit Regel-Typ | ⏳ |
| 33.4.12 | "Last Run"-Timestamp | Regel-Eintrag nach Ausführung | "Last run: 2026-03-14 12:00" | ⏳ |

### 33.5 Cleanup History

| # | Funktion | Wie testen | Erwartetes Ergebnis | Status |
|---|---------|------------|---------------------|--------|
| 33.5.1 | History-Section öffnen | Collapsible aufklappen | Tabelle mit Cleanup-Einträgen | ⏳ |
| 33.5.2 | Tabellen-Spalten | Einträge betrachten | Datum, Action, Processed, Deleted, Freed | ⏳ |
| 33.5.3 | Pagination Prev/Next | Buttons (wenn >50 Einträge) | Korrekte Seite | ⏳ |
| 33.5.4 | Seiten-Zähler | Pagination betrachten | "1 / 5" Format | ⏳ |
| 33.5.5 | Leerer Zustand | Keine History | Leere Tabelle oder Hinweistext | ⏳ |

---

## ÄNDERUNGSLOG

| Datum | Version | Änderung |
|-------|---------|----------|
| 2026-03-14 | Initial | Erster vollständiger Testplan erstellt (Abschnitte 1–19) |
| 2026-03-14 | Revision 1 | Audit durchgeführt: 137+ fehlende Testfälle ergänzt (Abschnitte 20–31) |

---

*Letzte Aktualisierung: 2026-03-14 | Sublarr v0.29.0-beta*
*Erstellt auf Basis vollständiger Frontend-Codebase-Analyse + nachgelagertem Coverage-Audit*
