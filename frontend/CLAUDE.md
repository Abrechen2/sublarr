# Frontend — React 19 + TypeScript

Stack: React 19, TypeScript, Tailwind v4, TanStack Query, Socket.IO, Vite.

## Struktur

```
src/
  App.tsx              # Router (React Router v6), QueryClient, WebSocketProvider
  api/client.ts        # Axios-Client, alle API-Funktionen, Basis-URL /api/v1/
  hooks/
    useApi.ts          # TanStack Query Hooks (useProviders, useLibrary, ...)
    useWebSocket.ts    # Socket.IO Hook (onWantedScanProgress, ...)
  lib/types.ts         # Zentrale TypeScript-Interfaces
  components/
    layout/Sidebar.tsx # Navigation (*arr-Style, Teal-Theme)
    shared/            # StatusBadge, ProgressBar, Toast, ErrorBoundary, ScanProgressIndicator
    dashboard/         # Widget-System (widgetRegistry.ts)
    editor/            # SubtitleEditorModal
  pages/               # Dashboard, Library, Wanted, Activity, Queue, History,
                       # Blacklist, Settings/*, SeriesDetail, Logs, Statistics, Tasks
```

## API-Client-Muster

`api/client.ts` exportiert typisierte Funktionen — **nie rohen Axios direkt in Komponenten nutzen.**

Backend-Antworten sind oft verschachtelt. Immer pruefen ob Daten auf Top-Level oder in einem Subkey (z.B. `data.health_check.healthy`) liegen.

```typescript
// Korrekt: verschachtelte Antwort entpacken
const { data } = await api.post(`/providers/test/${name}`)
return { healthy: data.health_check?.healthy ?? false, message: data.health_check?.message }
```

## Styling-Konventionen

CSS Custom Properties — keine hardcodierten Farben:
```css
--bg-primary, --bg-surface, --bg-surface-hover
--text-primary, --text-secondary, --text-muted
--accent, --accent-dim, --accent-bg
--border, --success, --error, --warning
```

Tailwind v4 fuer Layout/Spacing, CSS-Vars fuer alle Farben (Theme-Switching).

## State-Management

- **Server-State:** TanStack Query (automatisches Refetching, Caching)
- **Live-Updates:** Socket.IO via `useWebSocket` Hook
- **Lokaler UI-State:** `useState` — kein globaler Store
- **Immutability:** Immer neue Objekte via Spread, nie direkt mutieren

## Settings-Seite

`pages/Settings/` ist in Tabs aufgeteilt:
`ProvidersTab`, `TranslationTab`, `WhisperTab`, `MediaServersTab`, `IntegrationsTab`, `ApiKeysTab`, ...
Jeder Tab hat eigene Test-Funktionen die Ergebnisse lokal in `useState` halten.
