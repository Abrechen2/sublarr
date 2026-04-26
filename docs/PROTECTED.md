# Sublarr — Geschützte UI-Bereiche

**KRITISCHE REGEL:** Alle hier aufgeführten Bereiche wurden vom User als korrekt bestätigt.
Sie dürfen unter **KEINEN UMSTÄNDEN** verändert werden, ohne den User vorher explizit gefragt und eine explizite Freigabe erhalten zu haben.

Diese Datei muss vor jeder UI-Änderung geprüft werden.

---

## Wie diese Datei genutzt wird

- Nach jeder abgeschlossenen und bestätigten Implementierungseinheit wird der Bereich hier eingetragen
- Der Eintrag enthält: was geschützt ist, welche Dateien betroffen sind, und was genau nicht angefasst werden darf
- "Bestätigt" bedeutet: der User hat explizit gesagt, dass dieser Bereich gut aussieht / korrekt ist

---

## ✅ Bestätigte & geschützte Bereiche

### [2026-03-21] Design-Tokens & CSS

**Status:** Bestätigt als korrekt
**Dateien:** `frontend/src/index.css`
**Was geschützt ist:**
- Alle CSS Custom Properties (--bg-*, --text-*, --accent, --border, --space-*, --radius-*, --shadow-*)
- Dark-mode `.dark` class Overrides
- Animationen: fadeSlideUp, shimmer, dotGlow
- Accent-Farbe: `#0f9bb5` (teal), dark: `#1DB8D4`
- 8px Grid-System (--space-1 bis --space-12)

**Darf nicht verändert werden ohne Rückfrage:** Farbwerte, Spacing-Skala, Animationen, Token-Namen

---

### [2026-03-21] Basis-Komponenten (Settings-Pattern)

**Status:** Bestätigt als korrekt
**Dateien:**
- `frontend/src/components/settings/SettingsSection.tsx`
- `frontend/src/components/settings/FormGroup.tsx`
- `frontend/src/components/settings/SettingsDetailLayout.tsx`
- `frontend/src/components/settings/SettingsCard.tsx`

**Was geschützt ist:**
- SettingsSection: Icon-Box (32px, accent-bg) + Titel + Beschreibung + optionaler Advanced-Bereich
- FormGroup: Label+Hint links (max-width 320px) + Control rechts (min-width 260px), responsive
- SettingsDetailLayout: Seitenstruktur für Settings-Seiten
- Das gesamte visuelle Erscheinungsbild und die API dieser Komponenten

**Darf nicht verändert werden ohne Rückfrage:** Props-API, CSS-Klassen, Layout-Struktur

---

### [2026-03-21 / überarbeitet 2026-04-24] SeriesDetailPage

**Status:** Bestätigt als korrekt (Mockup-konform) — letzte Änderung 2026-04-24 für 0.71.1-beta bewusst durch den User genehmigt.
**Dateien:**
- `frontend/src/pages/SeriesDetail.tsx`
- `frontend/src/components/series/SeriesHero.tsx`
- `frontend/src/components/series/SeriesSettingsPanel.tsx`
- `frontend/src/components/series/` (alle weiteren Series-Komponenten)

**Was geschützt ist:**
- Hero-Bereich (Poster, Metadaten, 3 Action-Buttons)
- Season-Tabs
- Episode-Grid/Rows
- SeriesSettingsPanel (Sprach-/Untertitel-Einstellungen pro Serie) — inkl. Three-State `cleanup_foreign_tracks`-Toggle in der Subtitles-Section (hinzugefügt 0.71.1-beta, 2026-04-24, expliziter User-OK nach Konflikt-Diskussion Codex/FE/UX/Architect).
- Gesamtes Layout und Design der Seite

**Darf nicht verändert werden ohne Rückfrage:** Layout, Komponenten-Struktur, Design, bestehende Props + `onSetCleanupForeignTracks` Callback-Interface. Änderungshistorie:
- 2026-04-24 (Commit `aa2df5d`): Three-State-Select (Inherit/Always/Never) für `cleanup_foreign_tracks_override` eingebaut. Liest `SeriesDetail.cleanup_foreign_tracks_effective` für den „Inherit (on|off)"-Hint. PATCH via `/api/v1/series/<id>/settings`.

---

### [2026-03-21] ConnectionsSettings (Basis)

**Status:** Bestätigt als korrekt (korrektes Pattern + korrekte Keys)
**Dateien:** `frontend/src/pages/Settings/ConnectionsSettings.tsx`
**Was geschützt ist:**
- Sonarr-Verbindungsfelder (korrekte Config-Keys)
- Radarr-Verbindungsfelder (korrekte Config-Keys)
- MediaServer-Verbindungsfelder (korrekte Config-Keys)
- Design und SettingsSection/FormGroup-Pattern

**Hinweis:** Schritt 9 des Plans (Multi-Instanz UI) ERWEITERT diese Datei — das ist erlaubt, aber das bestehende Design darf dabei nicht verändert werden.

**Darf nicht verändert werden ohne Rückfrage:** Bestehende Key-Namen, bestehendes Design, bestehende Felder

---

### [2026-04-26] Profiles & Overrides Page (Codex Settings Template C reference)

**Status:** Bestätigt als korrekt — UAT auf Cardinal grün durch Phasen 0.73.0 → 0.76.0-beta (2026-04-26)
**Dateien:**
- `frontend/src/pages/Settings/ProfilesOverridesPage.tsx`
- `frontend/src/pages/Settings/profilesOverrides/` (alle Sub-Komponenten: ScopeTree, ScopeDetail, OverrideWidget, ProfileEditDialog, useProfilesOverrides, inheritanceFields)
- `frontend/src/components/settings/primitives/InheritanceRow.tsx` (5-state Pill-Semantik: default / set / inherited / overridden / n/a)
- `frontend/src/components/settings/primitives/TriStateToggle.tsx`
- `frontend/src/lib/routes.ts` (zentrale Route-Konstanten)
- `backend/services/inheritance_resolver.py` (12-Field-Registry + Chain-Walker)
- `backend/routes/profiles_overrides.py` (GET /scopes mit nur-explizit-Filter, POST .../create-override, DELETE, /resolved/<type>/<id>, PATCH, reset)
- `backend/db/migrations/versions/2026_04_25_1925-506332eef4f7_profiles_overrides_phase1.py` (8 series_settings Override-Spalten + movie_settings-Tabelle)

**Was geschützt ist:**
- Pill-Semantik der `InheritanceRow` (default / set / inherited / overridden / n/a) — niemals ohne explizite UX-Diskussion verändern
- 12-Field-Registry-Reihenfolge in `INHERITANCE_FIELDS` (Backend + Frontend müssen gespiegelt bleiben)
- /scopes-Filter: nur Series/Movies mit `series_settings`/`movie_settings`-Row ODER Profile-Mapping erscheinen im Tree (bewusste UX-Entscheidung — Phase A)
- URL-State `?scope=<type>:<id>` + optional `?from=<route>` für Round-Trip
- Backend-Endpoints + ihre Pfade (`POST .../create-override`, `DELETE .../<id>`, `POST .../<id>/reset`)

**Darf nicht verändert werden ohne Rückfrage:** Pill-Semantik, Field-Registry-Reihenfolge, /scopes-Filter-Logik, URL-State-Format, API-Endpoint-Pfade

---

### [2026-04-26] SeriesSettingsPanel (erweitert für Phase A + B)

**Status:** Bestätigt als korrekt — Phase A (Subtitle-settings-Button) + Phase B (Profile-Selector-Dropdown)
**Dateien:**
- `frontend/src/components/series/SeriesSettingsPanel.tsx`

**Was geschützt ist:**
- Existierende Three-State `cleanup_foreign_tracks`-Toggle (bereits vor 2026-04-26 bestätigt)
- Neuer **„Subtitle settings →"-Button** (Phase A) — POSTs idempotent create-override und navigiert nach `/settings/profiles?scope=series:<id>&from=/library/series/<id>`
- Neuer **interaktiver Profile-Selector** (Phase B) — ersetzt die read-only Profile-Pill, listet alle LanguageProfiles mit Default-Star-Suffix, ändert via `useAssignProfile`
- Layout-Bereiche: LANGUAGE / SUBTITLES / TOOLS / Subtitle-settings-Footer

**Darf nicht verändert werden ohne Rückfrage:** Layout, Button-Pfad zu `/settings/profiles`, Profile-Selector-Verhalten, `data-testid="series-subtitle-settings-link"` und `data-testid="series-profile-select"`

---

### [2026-04-26] MovieDetail (Subtitle Settings Card — Phase A + B)

**Status:** Bestätigt als korrekt — Phase A (Card mit Button) + Phase B (Profile-Selector)
**Dateien:**
- `frontend/src/pages/MovieDetail.tsx`

**Was geschützt ist:**
- Hero, File-Info-Card, Subtitles-Section, Wanted-Section unverändert (waren vorher schon stabil)
- Neue **Subtitle-Settings-Card** zwischen File-Info und Existing-Subtitles — enthält Profile-Selector + Subtitle-settings-Button (testids `movie-profile-select`, `movie-subtitle-settings-link`)

**Darf nicht verändert werden ohne Rückfrage:** Card-Position, Card-Inhalt, testids

---

### [2026-04-26] Library Page — Bulk-Selection (Phase C)

**Status:** Bestätigt als korrekt — Phase C (Bulk-Profile-Assignment)
**Dateien:**
- `frontend/src/pages/Library.tsx`
- `frontend/src/components/library/LibraryCard.tsx` (Checkbox-Overlay)

**Was geschützt ist:**
- Tabs (series/movies), View-Mode (table/grid), Filter, Sortierung, Pagination — alles unverändert
- Neuer **Sticky-Bulk-Toolbar** der erscheint wenn `selectedSeries.size > 0` (testid `library-bulk-toolbar`)
- Toolbar enthält: „N selected"-Badge, „Set profile…"-Dropdown, „Clear selection"-Button (testid `library-bulk-clear`)
- Selection wird automatisch geleert beim Tab-Wechsel
- Backend-Endpoint `PUT /api/v1/language-profiles/assign-bulk`

**Darf nicht verändert werden ohne Rückfrage:** Toolbar-Position (sticky top), Tab-Switch-Reset, Backend-Endpoint-Pfad

---

## 📋 Ausstehend (noch nicht bestätigt)

Diese Bereiche sind im Plan, aber noch nicht implementiert/bestätigt:

- GeneralSettings (Phase 1+2 — Key-Fixes + Design)
- AutomationSettings (Phase 1+2 — Komplett-Rewrite + Design)
- SubtitlesSettings (Phase 2)
- TranslationSettings (Phase 2)
- NotificationsSettings (Phase 2)
- SystemSettings (Phase 2)
- Re-scan Series Feature (Phase 3)
- Glossar-Verwaltung (Phase 3)
- Sprachprofil-Verwaltungsseite (Phase 3) — **OBSOLET**: durch Profiles & Overrides Page (siehe oben) ersetzt
- Backup-Management UI (Phase 3)

---

*Letzte Aktualisierung: 2026-04-26 — Profiles & Overrides + Series/Movie/Library-Erweiterungen*
