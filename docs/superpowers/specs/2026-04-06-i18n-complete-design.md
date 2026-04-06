# i18n Vollständige Lokalisierung — Design Spec

**Datum:** 2026-04-06  
**Branch:** `feat/i18n-complete`  
**Status:** Approved

---

## Ziel

Die gesamte Sublarr-UI auf vollständige i18n-Unterstützung umstellen. Deutsch ist Hauptsprache, Englisch ist Zweitsprache. Die App erkennt die Browser-Sprache automatisch und fällt auf Deutsch zurück wenn keine passende Sprache erkannt wird.

---

## Ist-Zustand

- **Struktur:** 9 Namespace-Paare (`common`, `dashboard`, `settings`, `library`, `activity`, `logs`, `onboarding`, `editor`, `statistics`) — vollständige Key-Parität zwischen EN und DE
- **Problem 1:** ~15 TSX-Dateien enthalten hardcoded englische Strings statt `t()` — diese erscheinen immer auf Englisch unabhängig von der gewählten Sprache
- **Problem 2:** 12 DE-Values sind nicht übersetzt (Dashboard, Common, Settings) — API-Key-Labels bleiben bewusst englisch
- **Problem 3:** `fallbackLng: 'en'` → muss `'de'` werden

---

## Entscheidungen

| Thema | Entscheidung |
|-------|-------------|
| API-Key-Felder (z.B. "Sonarr API Key") | Bleiben englisch — sind Produktnamen |
| Browser-Erkennung | Bleibt aktiv (`LanguageDetector` mit `localStorage` + `navigator`) |
| Fallback-Sprache | `'de'` statt `'en'` |
| Scope | Alle TSX-Dateien — auch Migration, Legacy, Protokoll |

---

## Architektur

### i18n-Konfiguration (`index.ts`)
- `fallbackLng: 'en'` → `'de'`
- Keine weiteren Änderungen an Namespace-Struktur oder Detection-Order

### Namespace-Zuordnung neuer Keys

Hardcoded Strings werden dem Namespace zugeordnet, der zur Komponente passt:

| Namespace | Neue Keys für |
|-----------|---------------|
| `settings` | Alle Settings-Tabs (EventsHooks, Integrations, LanguageProfiles, Migration, Security, WhisperTab, SubtitleTools, SystemSettings, PathMapping, Providers) |
| `library` | Library.tsx Optionen ("Entire Library", "Single Series", "Default engine") |
| `onboarding` | Setup.tsx ("Confirm Password") |
| `statistics` | Statistics.tsx ("Last Download") |

### Key-Namenskonvention

- Snake_case, beschreibend, nicht zu generisch
- Nested entsprechend der logischen Gruppierung im Namespace
- Beispiel: `settings.hooks.shell_hooks_title`, `settings.integrations.not_configured`

---

## Betroffene Dateien

### TSX-Dateien mit hardcoded Strings

| Datei | Strings (Auswahl) |
|-------|-------------------|
| `Settings/EventsHooksTabContent.tsx` | "Shell Hooks", "Outgoing Webhooks", "Execution Log", "All Events" |
| `Settings/IntegrationsTab.tsx` | "Not configured", "Media Servers", "Bazarr Compatible", "Plex Manifest", "Generic JSON" |
| `Settings/LanguageProfilesTab.tsx` | "Forced Subtitles", "Translation Backend", "Fallback Chain" |
| `Settings/MigrationTab.tsx` | "Bazarr Migration", "Config Entries", "Language Profiles", "Blacklist Entries", "History Entries", "Profiles Imported" |
| `Settings/PathMappingEditor.tsx` | "Remote Path", "Local Path" |
| `Settings/ProvidersTab.tsx` | "Rate limited" |
| `Settings/SecurityTab.tsx` | "Current Password", "New Password" |
| `Settings/SubtitleToolsTab.tsx` | "Common Fixes", "Preview Subtitle" |
| `Settings/WhisperTab.tsx` | "Approx Size" |
| `Settings/SystemSettings.tsx` | Hardcoded Satz über Events/Hooks |
| `Settings/LegacySettings.tsx` | "Import Preview" |
| `Library.tsx` | "Entire Library", "Single Series", "Default engine" |
| `Setup.tsx` | "Confirm Password" |
| `Statistics.tsx` | "Last Download" |
| `Plugins.tsx` | "Plugin Marketplace", "All Categories" |

### Locale-Dateien mit fehlenden DE-Übersetzungen

| Datei | Keys |
|-------|------|
| `dashboard.json` | `attention.title`, `attention.skip`, `metrics.lowScore` |
| `common.json` | `language.en` (Anmerkung: "English" ist als Eigenname korrekt, aber Konvention prüfen) |
| `settings.json` | `support_diagnostic_title` |

---

## Vorgehen

**Methode:** Datei für Datei (Option A)

Für jede betroffene TSX-Datei:
1. Alle hardcoded Strings identifizieren
2. Keys in `de/[namespace].json` + `en/[namespace].json` anlegen
3. `t()` in der TSX-Datei einsetzen (Namespace-Import falls neu)
4. Lint + TypeCheck

Abschließend:
- `fallbackLng` in `index.ts` ändern
- 12 fehlende DE-Values fixen

---

## Nicht im Scope

- Neue Namespaces anlegen (alle Strings passen in existierende Namespaces)
- Backend-Strings übersetzen
- RTL-Unterstützung
- Weitere Sprachen hinzufügen

---

## Erfolgskriterien

- `npm run lint` + `npx tsc --noEmit` + `npm run test -- --run` grün
- Kein sichtbarer englischer String in der DE-UI (außer Produktnamen/API-Keys)
- Alle neuen Keys in beiden Locale-Dateien vorhanden
- `fallbackLng: 'de'` aktiv
