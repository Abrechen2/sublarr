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

### [2026-03-21] SeriesDetailPage

**Status:** Bestätigt als korrekt (Mockup-konform)
**Dateien:**
- `frontend/src/pages/SeriesDetail.tsx`
- `frontend/src/components/series/SeriesHero.tsx`
- `frontend/src/components/series/SeriesSettingsPanel.tsx`
- `frontend/src/components/series/` (alle weiteren Series-Komponenten)

**Was geschützt ist:**
- Hero-Bereich (Poster, Metadaten, 3 Action-Buttons)
- Season-Tabs
- Episode-Grid/Rows
- SeriesSettingsPanel (Sprach-/Untertitel-Einstellungen pro Serie)
- Gesamtes Layout und Design der Seite

**Darf nicht verändert werden ohne Rückfrage:** Layout, Komponenten-Struktur, Design, bestehende Props

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

## 📋 Ausstehend (noch nicht bestätigt)

Diese Bereiche sind im Plan, aber noch nicht implementiert/bestätigt:

- GeneralSettings (Phase 1+2 — Key-Fixes + Design)
- AutomationSettings (Phase 1+2 — Komplett-Rewrite + Design)
- SubtitlesSettings (Phase 2)
- ProvidersSettings (Phase 2)
- TranslationSettings (Phase 2)
- NotificationsSettings (Phase 2)
- SystemSettings (Phase 2)
- Re-scan Series Feature (Phase 3)
- Glossar-Verwaltung (Phase 3)
- Sprachprofil-Verwaltungsseite (Phase 3)
- Backup-Management UI (Phase 3)
- MovieDetailPage (Phase 3)

---

*Letzte Aktualisierung: 2026-03-21*
