# Step 06: Add Library Scan Fields to AutomationSettings — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `wanted_scan_interval_hours` (number input, 0 = disabled/event-driven) and `wanted_scan_on_startup` (toggle) to `AutomationSettings.tsx` inside `SearchScanContent`. These fields form a new "Bibliotheks-Scan" sub-group that appears **above** the existing "Untertitel-Suche" fields within `section-search-scan`.

**Architecture:** Pure frontend change. Three tasks: tests first (RED), component update (GREEN), lint + commit. No backend changes — both keys must already exist in `backend/config.py`.

**Tech Stack:** React 19, TypeScript, Vitest + Testing Library

---

## Task 1: Tests schreiben (danach ROT)

- [ ] **1.1 — mockConfig ergänzen**

  In `frontend/src/pages/Settings/__tests__/AutomationSettings.test.tsx`, add the two new keys to the `data` object inside the `useConfig` mock (currently starting around line 32). Insert after `wanted_search_on_startup`:

  ```typescript
  wanted_scan_interval_hours: '0',
  wanted_scan_on_startup: 'false',
  ```

- [ ] **1.2 — Sub-Gruppen-Überschriften testen**

  Add these two tests inside the `describe('AutomationSettings', ...)` block, in a new nested `describe` called `'Search & Scan — sub-group headings'`:

  ```typescript
  describe('Search & Scan — sub-group headings', () => {
    it('renders "Bibliotheks-Scan" sub-group heading inside section-search-scan', () => {
      renderPage()
      const section = screen.getByTestId('section-search-scan')
      expect(section).toHaveTextContent('Bibliotheks-Scan')
    })

    it('renders "Untertitel-Suche" sub-group heading inside section-search-scan', () => {
      renderPage()
      const section = screen.getByTestId('section-search-scan')
      expect(section).toHaveTextContent('Untertitel-Suche')
    })

    it('"Bibliotheks-Scan" heading appears before "Untertitel-Suche" heading in the DOM', () => {
      renderPage()
      const section = screen.getByTestId('section-search-scan')
      const headings = section.querySelectorAll('[data-testid^="search-scan-subheading-"]')
      expect(headings).toHaveLength(2)
      expect(headings[0]).toHaveAttribute('data-testid', 'search-scan-subheading-scan')
      expect(headings[1]).toHaveAttribute('data-testid', 'search-scan-subheading-search')
    })
  })
  ```

- [ ] **1.3 — wanted_scan_interval_hours Tests hinzufügen**

  Add these tests inside a new nested `describe` called `'Search & Scan — scan interval'`:

  ```typescript
  describe('Search & Scan — scan interval', () => {
    it('renders form-group for wanted_scan_interval_hours', () => {
      renderPage()
      expect(screen.getByTestId('form-group-wanted-scan-interval-hours')).toBeInTheDocument()
    })

    it('displays wanted_scan_interval_hours value from config', () => {
      renderPage()
      const input = screen.getByTestId('input-wanted-scan-interval-hours') as HTMLInputElement
      expect(input.value).toBe('0')
    })

    it('input has min="0" attribute (0 = disabled)', () => {
      renderPage()
      const input = screen.getByTestId('input-wanted-scan-interval-hours') as HTMLInputElement
      expect(input).toHaveAttribute('min', '0')
    })

    it('calls updateConfig with wanted_scan_interval_hours as number on change', () => {
      renderPage()
      const input = screen.getByTestId('input-wanted-scan-interval-hours')
      fireEvent.change(input, { target: { value: '4' } })
      expect(mockMutate).toHaveBeenCalledWith({ wanted_scan_interval_hours: 4 })
    })

    it('calls updateConfig with 0 when input value is "0"', () => {
      renderPage()
      const input = screen.getByTestId('input-wanted-scan-interval-hours')
      fireEvent.change(input, { target: { value: '0' } })
      expect(mockMutate).toHaveBeenCalledWith({ wanted_scan_interval_hours: 0 })
    })
  })
  ```

- [ ] **1.4 — wanted_scan_on_startup Tests hinzufügen**

  Add these tests inside a new nested `describe` called `'Search & Scan — scan on startup'`:

  ```typescript
  describe('Search & Scan — scan on startup', () => {
    it('renders form-group for wanted_scan_on_startup', () => {
      renderPage()
      expect(screen.getByTestId('form-group-wanted-scan-on-startup')).toBeInTheDocument()
    })

    it('wanted_scan_on_startup toggle reflects config value (false)', () => {
      renderPage()
      const fg = screen.getByTestId('form-group-wanted-scan-on-startup')
      const toggle = fg.querySelector('[role="switch"]')
      expect(toggle).toHaveAttribute('aria-checked', 'false')
    })

    it('calls updateConfig with wanted_scan_on_startup=true when toggled', () => {
      renderPage()
      const fg = screen.getByTestId('form-group-wanted-scan-on-startup')
      const toggle = fg.querySelector('[role="switch"]') as HTMLElement
      fireEvent.click(toggle)
      expect(mockMutate).toHaveBeenCalledWith({ wanted_scan_on_startup: true })
    })
  })
  ```

- [ ] **1.5 — DOM-Reihenfolge testen**

  Add this test to verify the two new fields appear before the existing search fields. Add it to the `'Search & Scan — sub-group headings'` describe block:

  ```typescript
  it('wanted_scan_interval_hours input appears before wanted_search_interval_hours input in the DOM', () => {
    renderPage()
    const section = screen.getByTestId('section-search-scan')
    const allInputs = section.querySelectorAll('input[type="number"]')
    const ids = Array.from(allInputs).map((el) => el.getAttribute('data-testid'))
    const scanIdx = ids.indexOf('input-wanted-scan-interval-hours')
    const searchIdx = ids.indexOf('input-wanted-search-interval-hours')
    expect(scanIdx).toBeGreaterThanOrEqual(0)
    expect(searchIdx).toBeGreaterThanOrEqual(0)
    expect(scanIdx).toBeLessThan(searchIdx)
  })
  ```

- [ ] **1.6 — Tests ausführen und ROT bestätigen**

  ```bash
  cd D:/Sublarr_Projekt/Sublarr/frontend && npm run test -- --run src/pages/Settings/__tests__/AutomationSettings.test.tsx
  ```

  Erwartetes Ergebnis: Die 9 neuen Tests schlagen fehl (testids nicht gefunden, sub-group headings nicht vorhanden). Erst wenn Tests ROT sind, weiter mit Task 2.

---

## Task 2: Komponente anpassen (GREEN)

- [ ] **2.1 — Sub-Gruppen-Struktur in SearchScanContent einbauen**

  In `frontend/src/pages/Settings/AutomationSettings.tsx`, modify the `SearchScanContent` function. Replace the opening `<div data-testid="search-scan-content">` and its immediate children so the content is structured as two sub-groups. Insert the following block **at the top**, before the first existing `<FormGroup>`:

  ```tsx
  {/* ─── Bibliotheks-Scan sub-group ─── */}
  <p
    data-testid="search-scan-subheading-scan"
    style={{
      fontSize: '11px',
      fontWeight: 600,
      letterSpacing: '0.06em',
      textTransform: 'uppercase',
      color: 'var(--text-muted)',
      margin: '4px 0 10px',
    }}
  >
    Bibliotheks-Scan
  </p>

  <FormGroup
    label="Scan-Intervall (Stunden)"
    hint="Wie oft (in Stunden) Sublarr die Bibliothek auf neue Dateien scannt. 0 = nur event-gesteuert."
    htmlFor="wanted-scan-interval-hours"
    data-testid="form-group-wanted-scan-interval-hours"
  >
    <input
      id="wanted-scan-interval-hours"
      type="number"
      data-testid="input-wanted-scan-interval-hours"
      style={{ ...inputStyle, maxWidth: '120px' }}
      value={strVal(config, 'wanted_scan_interval_hours', '0')}
      onChange={(e) => save({ wanted_scan_interval_hours: Number(e.target.value) })}
      disabled={updateConfig.isPending}
      min={0}
      placeholder="0"
    />
  </FormGroup>

  <FormGroup
    label="Scan beim Start"
    hint="Bibliothek beim Start von Sublarr automatisch scannen."
    data-testid="form-group-wanted-scan-on-startup"
  >
    <Toggle
      checked={boolVal(config, 'wanted_scan_on_startup', false)}
      onChange={(v) => save({ wanted_scan_on_startup: v })}
      disabled={updateConfig.isPending}
    />
  </FormGroup>

  {/* ─── Untertitel-Suche sub-group ─── */}
  <p
    data-testid="search-scan-subheading-search"
    style={{
      fontSize: '11px',
      fontWeight: 600,
      letterSpacing: '0.06em',
      textTransform: 'uppercase',
      color: 'var(--text-muted)',
      margin: '16px 0 10px',
    }}
  >
    Untertitel-Suche
  </p>
  ```

  The first existing `<FormGroup>` (for `wanted_search_interval_hours`) follows immediately after this block. No existing FormGroup is removed or reordered.

- [ ] **2.2 — TypeScript-Check ausführen**

  ```bash
  cd D:/Sublarr_Projekt/Sublarr/frontend && npx tsc --noEmit
  ```

  Erwartetes Ergebnis: keine Fehler. Alle auftretenden Fehler vor dem nächsten Schritt beheben.

---

## Task 3: Tests grün + committen

- [ ] **3.1 — Tests ausführen und GREEN bestätigen**

  ```bash
  cd D:/Sublarr_Projekt/Sublarr/frontend && npm run test -- --run src/pages/Settings/__tests__/AutomationSettings.test.tsx
  ```

  Erwartetes Ergebnis: alle Tests (alte + 9 neue) bestehen. Falls Tests fehlschlagen, Abweichungen bei `data-testid`-Attributen und der DOM-Reihenfolge prüfen.

- [ ] **3.2 — ESLint ausführen**

  ```bash
  cd D:/Sublarr_Projekt/Sublarr/frontend && npm run lint
  ```

  Alle durch die Änderungen entstandenen Warnungen und Fehler beheben.

- [ ] **3.3 — Vollständige Testsuite ausführen**

  ```bash
  cd D:/Sublarr_Projekt/Sublarr/frontend && npm run test -- --run
  ```

  Sicherstellen, dass keine anderen Tests durch die Änderungen gebrochen wurden.

- [ ] **3.4 — Commit erstellen**

  ```bash
  git add frontend/src/pages/Settings/AutomationSettings.tsx \
          frontend/src/pages/Settings/__tests__/AutomationSettings.test.tsx
  git commit -m "feat: add scan interval and scan-on-startup fields to AutomationSettings"
  ```

  Inhalt des Commits:
  - Zwei neue Felder in `SearchScanContent`: `wanted_scan_interval_hours` (Number, 0 = deaktiviert) und `wanted_scan_on_startup` (Toggle)
  - Sub-Gruppen-Überschriften "Bibliotheks-Scan" und "Untertitel-Suche" hinzugefügt
  - mockConfig in Tests um beide Schlüssel erweitert
  - 9 neue Tests für Rendering, Werte, Interaktionen und DOM-Reihenfolge

---

## Referenz: Neue Felder

| Config-Schlüssel | Typ | Default | Control | testid (form-group) | testid (input/toggle) |
|---|---|---|---|---|---|
| `wanted_scan_interval_hours` | Number | `0` | `<input type="number" min={0}>` | `form-group-wanted-scan-interval-hours` | `input-wanted-scan-interval-hours` |
| `wanted_scan_on_startup` | Boolean | `false` | `<Toggle>` | `form-group-wanted-scan-on-startup` | (via `role="switch"` inside FormGroup) |

## Referenz: Sub-Gruppen-Struktur nach der Änderung

```
section-search-scan
  └─ search-scan-content
      ├─ search-scan-subheading-scan        ← NEU
      ├─ form-group-wanted-scan-interval-hours  ← NEU
      ├─ form-group-wanted-scan-on-startup      ← NEU
      ├─ search-scan-subheading-search      ← NEU
      ├─ form-group-wanted-search-interval-hours   (bestehend)
      ├─ form-group-wanted-search-on-startup       (bestehend)
      ├─ form-group-wanted-search-max-items-per-run (bestehend)
      ├─ form-group-wanted-max-search-attempts      (bestehend)
      ├─ form-group-wanted-auto-extract             (bestehend)
      ├─ form-group-wanted-anime-only               (bestehend)
      ├─ form-group-wanted-anime-movies-only        (bestehend)
      ├─ form-group-wanted-skip-srt-on-no-ass       (bestehend)
      └─ form-group-wanted-adaptive-backoff-enabled (bestehend)
```
