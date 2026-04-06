# Version Display & Update Indicator — Design

## Goal

Zeige die aktuelle Versionsnummer prominent in der StatusBar an und informiere den User mit einem pulsierenden Amber-Dot im Sidebar + einem Popover in der StatusBar, wenn ein neueres Sublarr-Release auf GitHub verfügbar ist.

## Architecture

Alle benötigten Daten kommen aus zwei bestehenden Hooks:
- `useHealth()` — liefert `version` (bereits genutzt in IconSidebar + StatusBar)
- `useUpdateInfo()` — liefert `{ available, latest, current, url }`, 6h-Cache + Refetch

Keine neuen API-Endpoints, keine neuen Hooks. Beide Komponenten rufen `useUpdateInfo()` zusätzlich auf.

## Tech Stack

React 19, TypeScript, Tailwind CSS (animate-ping), Lucide Icons, react-i18next (`common` namespace)

---

## Component 1: IconSidebar

**File:** `frontend/src/components/layout/IconSidebar.tsx`

### Collapsed-Zustand (Sidebar-Breite 48px)

Wenn `updateInfo?.available === true`, wird auf dem Settings-Icon-Container ein Dot gerendert:
- Äußerer Ring: `absolute top-0 right-0 w-2 h-2 rounded-full bg-amber-400 animate-ping opacity-75`
- Innerer Dot: `absolute top-0 right-0 w-2 h-2 rounded-full bg-amber-400`
- Der Icon-Container braucht `relative` positioning

Kein Update → nichts gerendert, kein Layout-Impact.

### Expanded-Zustand (Sidebar-Breite 220px)

Direkt neben der bestehenden Versionsnummer (`v{health?.version ?? '...'}`) erscheint ein Chip:
- Nur gerendert wenn `updateInfo?.available === true`
- Inhalt: `↑ v{updateInfo.latest}`
- Style: `text-[10px] px-1 rounded bg-amber-400/20 text-amber-400 font-mono ml-1`

### i18n

Kein eigener Label-Text im Sidebar — die Chip-Anzeige ist rein visuell (Versionsnummer).

---

## Component 2: StatusBar

**File:** `frontend/src/components/layout/StatusBar.tsx`

### Kein Update verfügbar

Versionsnummer wie bisher: `v{health?.version ?? '...'}` als statischer Text.

### Update verfügbar

Die Versionsnummer wird zu einem `<button>` (oder `<div role="button">`) mit:
- Amber-Dot links daneben: `w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse`
- Text in amber: `text-amber-400`
- Klick-Handler: öffnet/schließt den Popover

### Popover

Kleines Overlay, direkt **oberhalb** des Buttons positioniert (absolute, `bottom-full mb-2`):
```
┌─────────────────────────────┐
│  ↑ v0.42.0 verfügbar       │
│  Jetzt auf GitHub ansehen → │
└─────────────────────────────┘
```
- Schließt sich bei Klick außerhalb (`useEffect` + `mousedown`-Listener)
- Öffnet `updateInfo.url` in `_blank`
- Style: `bg-[var(--bg-secondary)] border border-[var(--border)] rounded p-2 text-xs shadow-lg min-w-48`
- State: `const [open, setOpen] = useState(false)` lokal im StatusBar

### i18n

Neue Keys im `common`-Namespace:
```json
"update": {
  "available_chip": "↑ {{version}} verfügbar",
  "view_release": "Jetzt auf GitHub ansehen →"
}
```
(EN: `"↑ {{version}} available"`, `"View on GitHub →"`)

---

## Error Handling

`useUpdateInfo()` hat bereits `retry: 1` und degradiert gracefully zu `available: false` bei Netzwerkfehler — kein Fehler-Handling nötig in den Komponenten.

---

## Testing

- `IconSidebar.test.tsx`: Test mit `updateInfo.available = true` → Dot + Chip gerendert; `false` → nicht gerendert
- `StatusBar.test.tsx`: Test mit `updateInfo.available = true` → Button mit amber Dot; Klick → Popover sichtbar; Klick außerhalb → Popover geschlossen

---

## Out of Scope

- Auto-Update / Download des neuen Releases
- Update-Benachrichtigung per Toast beim Start
- Changelog-Anzeige innerhalb der App
- Mobile-Ansicht (StatusBar ist bereits `hidden md:flex`)
