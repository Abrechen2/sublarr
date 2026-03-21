# GeneralSettings Config Key Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 3 wrong config keys in `GeneralSettings.tsx` so all values are actually saved to the backend.

**Architecture:** Pure frontend change. Three targeted edits in one component file + corresponding test updates. No backend changes needed — the correct keys already exist in `backend/config.py`.

**Tech Stack:** React 19, TypeScript, Vitest + Testing Library

---

## What changes and why

| Location | Was (falsch) | Wird (korrekt) | Warum falsch |
|---|---|---|---|
| Advanced section | `workers` (Number) | `translation_max_workers` + `scan_metadata_max_workers` (zwei Number-Inputs) | Backend kennt keinen Key `workers` |
| Logging section | `log_to_file` (Toggle/Boolean) | `log_file` (Text-Input/Pfad-String) | Backend erwartet Pfad-String, kein Boolean |
| Translation section | `translation_enabled` (FeatureAddon) | *(entfernen)* | Feld existiert nicht in `config.py` |

## Files

- Modify: `frontend/src/pages/Settings/GeneralSettings.tsx`
  - Lines 191–208 (workers → zwei Felder)
  - Lines 316–327 (log_to_file Toggle → log_file Text-Input)
  - Lines 331–339 (FeatureAddon translation_enabled → entfernen)
- Modify: `frontend/src/pages/Settings/__tests__/GeneralSettings.test.tsx`
  - `mockConfig` aktualisieren
  - Alte Tests entfernen, neue hinzufügen

---

## Task 1 — Tests anpassen (werden danach rot sein)

**File:** `frontend/src/pages/Settings/__tests__/GeneralSettings.test.tsx`

- [ ] **Schritt 1: `mockConfig` aktualisieren**

Ersetze die `mockConfig`-Definition (Zeilen 17–30) durch:

```typescript
const mockConfig: Record<string, unknown> = {
  source_language: 'en',
  target_language: 'de',
  hi_preference: 'include',
  forced_preference: 'include',
  media_path: '/media',
  port: 5765,
  translation_max_workers: 2,
  scan_metadata_max_workers: 2,
  base_url: '',
  db_path: '/config/sublarr.db',
  log_level: 'INFO',
  log_file: '',
}
```

- [ ] **Schritt 2: Alte Tests für falsche Keys entfernen**

Folgende Tests löschen (testen falsche Keys die wegkommen):
- `'renders log_to_file as a Toggle (role="switch")'`
- `'Toggle reflects log_to_file=false from config'`
- `'calls updateConfig with log_to_file=true when toggle is clicked'`
- `'renders the Translation feature addon section'`
- `'renders the FeatureAddon card'`
- `'shows "Translation" as addon title'`
- `'addon toggle reflects translation_enabled=false'`
- `'calls updateConfig with translation_enabled=true when addon toggle is clicked'`

- [ ] **Schritt 3: Neuen Test für Advanced-Felder hinzufügen**

Füge nach dem Test `'shows advanced fields after clicking the Advanced toggle in Paths section'` (Zeile 178) hinzu:

```typescript
it('shows translation_max_workers and scan_metadata_max_workers in advanced section', () => {
  renderWithProviders(<GeneralSettings />)
  const pathsSection = screen.getByTestId('section-paths')
  const advancedToggle = pathsSection.querySelector(
    '[data-testid="settings-section-advanced-toggle"]',
  ) as HTMLElement
  fireEvent.click(advancedToggle)
  expect(screen.getByTestId('input-translation-max-workers')).toBeInTheDocument()
  expect(screen.getByTestId('input-scan-metadata-max-workers')).toBeInTheDocument()
})

it('calls updateConfig with translation_max_workers on change', () => {
  renderWithProviders(<GeneralSettings />)
  const pathsSection = screen.getByTestId('section-paths')
  const advancedToggle = pathsSection.querySelector(
    '[data-testid="settings-section-advanced-toggle"]',
  ) as HTMLElement
  fireEvent.click(advancedToggle)
  const input = screen.getByTestId('input-translation-max-workers')
  fireEvent.change(input, { target: { value: '4' } })
  expect(mockMutate).toHaveBeenCalledWith({ translation_max_workers: 4 })
})

it('calls updateConfig with scan_metadata_max_workers on change', () => {
  renderWithProviders(<GeneralSettings />)
  const pathsSection = screen.getByTestId('section-paths')
  const advancedToggle = pathsSection.querySelector(
    '[data-testid="settings-section-advanced-toggle"]',
  ) as HTMLElement
  fireEvent.click(advancedToggle)
  const input = screen.getByTestId('input-scan-metadata-max-workers')
  fireEvent.change(input, { target: { value: '3' } })
  expect(mockMutate).toHaveBeenCalledWith({ scan_metadata_max_workers: 3 })
})
```

- [ ] **Schritt 4: Neuen Test für `log_file` hinzufügen**

Füge nach den Log-Level-Tests ein:

```typescript
it('renders log_file as a text input (not a toggle)', () => {
  renderWithProviders(<GeneralSettings />)
  expect(screen.getByTestId('input-log-file')).toBeInTheDocument()
  expect(screen.queryByTestId('form-group-log-to-file')).toBeNull()
})

it('displays the log_file value from config', () => {
  renderWithProviders(<GeneralSettings />)
  const input = screen.getByTestId('input-log-file') as HTMLInputElement
  expect(input.value).toBe('')
})

it('calls updateConfig with log_file string on change', () => {
  renderWithProviders(<GeneralSettings />)
  const input = screen.getByTestId('input-log-file')
  fireEvent.change(input, { target: { value: '/config/sublarr.log' } })
  expect(mockMutate).toHaveBeenCalledWith({ log_file: '/config/sublarr.log' })
})
```

- [ ] **Schritt 5: Alten `input-workers` Test anpassen**

Test `'shows advanced fields after clicking the Advanced toggle in Paths section'` (Zeile 178):
- Ersetze `expect(screen.getByTestId('input-workers')).toBeInTheDocument()` durch:
  ```typescript
  expect(screen.getByTestId('input-translation-max-workers')).toBeInTheDocument()
  expect(screen.getByTestId('input-scan-metadata-max-workers')).toBeInTheDocument()
  ```

- [ ] **Schritt 6: Tests ausführen — müssen ROT sein**

```bash
cd frontend && npm run test -- --run --reporter=verbose src/pages/Settings/__tests__/GeneralSettings.test.tsx
```

Erwartetes Ergebnis: Mehrere Tests FAIL (neue Tests finden die Elemente nicht, da Komponente noch nicht angepasst).

---

## Task 2 — Komponente anpassen

**File:** `frontend/src/pages/Settings/GeneralSettings.tsx`

- [ ] **Schritt 7: `workers` → zwei Felder (Advanced Section)**

Ersetze die `workers` FormGroup (Zeilen 191–208) durch:

```tsx
<FormGroup
  label="Translation Workers"
  hint="Parallel threads for subtitle translation jobs"
  htmlFor="translation-max-workers"
  data-testid="form-group-translation-max-workers"
>
  <input
    id="translation-max-workers"
    type="number"
    data-testid="input-translation-max-workers"
    style={{ ...inputStyle, maxWidth: '120px' }}
    value={strVal(config, 'translation_max_workers', '2')}
    onChange={(e) => save({ translation_max_workers: Number(e.target.value) })}
    disabled={isPending}
    min={1}
    max={32}
  />
</FormGroup>

<FormGroup
  label="Metadata Scan Workers"
  hint="Parallel threads for metadata scanning"
  htmlFor="scan-metadata-max-workers"
  data-testid="form-group-scan-metadata-max-workers"
>
  <input
    id="scan-metadata-max-workers"
    type="number"
    data-testid="input-scan-metadata-max-workers"
    style={{ ...inputStyle, maxWidth: '120px' }}
    value={strVal(config, 'scan_metadata_max_workers', '2')}
    onChange={(e) => save({ scan_metadata_max_workers: Number(e.target.value) })}
    disabled={isPending}
    min={1}
    max={32}
  />
</FormGroup>
```

- [ ] **Schritt 8: `log_to_file` Toggle → `log_file` Text-Input**

Ersetze die `log_to_file` FormGroup (Zeilen 316–327) durch:

```tsx
<FormGroup
  label="Log File Path"
  hint="Write logs to this file path, e.g. /config/sublarr.log. Leave empty to disable."
  htmlFor="log-file"
  data-testid="form-group-log-file"
>
  <input
    id="log-file"
    type="text"
    data-testid="input-log-file"
    style={inputStyle}
    value={strVal(config, 'log_file', '')}
    onChange={(e) => save({ log_file: e.target.value })}
    disabled={isPending}
    placeholder="/config/sublarr.log"
  />
</FormGroup>
```

- [ ] **Schritt 9: `translation_enabled` FeatureAddon entfernen**

Lösche den gesamten Block (Zeilen 330–339):

```tsx
{/* ── Translation feature addon ─────────────────────────────────── */}
<div data-testid="section-translation-addon">
  <FeatureAddon
    icon={Languages}
    title="Translation"
    description="Enable AI-powered subtitle translation between languages"
    isEnabled={boolVal(config, 'translation_enabled', false)}
    onToggle={(v) => save({ translation_enabled: v })}
  />
</div>
```

- [ ] **Schritt 10: Nicht mehr verwendete Imports entfernen**

Prüfe ob `Languages` und `FeatureAddon` noch verwendet werden. Falls nicht:
- Entferne `Languages` aus dem `lucide-react` Import
- Entferne `import { FeatureAddon }` komplett
- Entferne `boolVal` Hilfsfunktion falls nicht mehr verwendet

- [ ] **Schritt 11: TypeScript-Check**

```bash
cd frontend && npx tsc --noEmit
```

Erwartetes Ergebnis: Keine Fehler.

---

## Task 3 — Tests grün machen und committen

- [ ] **Schritt 12: Tests ausführen — müssen GRÜN sein**

```bash
cd frontend && npm run test -- --run --reporter=verbose src/pages/Settings/__tests__/GeneralSettings.test.tsx
```

Erwartetes Ergebnis: Alle Tests PASS.

- [ ] **Schritt 13: Lint**

```bash
cd frontend && npm run lint
```

Erwartetes Ergebnis: Keine Fehler.

- [ ] **Schritt 14: Commit**

```bash
git add frontend/src/pages/Settings/GeneralSettings.tsx \
        frontend/src/pages/Settings/__tests__/GeneralSettings.test.tsx
git commit -m "fix: correct config keys in GeneralSettings (workers→split, log_to_file→log_file, remove translation_enabled)"
```

---

## Verifikation nach dem Commit

Manuell in der laufenden App prüfen:
1. Settings → General aufrufen
2. Advanced-Bereich öffnen → zwei Worker-Felder sehen (`Translation Workers`, `Metadata Scan Workers`)
3. Logging-Bereich → Pfad-Input statt Toggle
4. Translation-FeatureAddon ist weg
5. Einen Worker-Wert ändern → Network-Tab im Browser → `PATCH /api/v1/config` mit Key `translation_max_workers` (nicht `workers`)
