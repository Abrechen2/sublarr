# Step 09: Add Missing Processing Pipeline Fields to AutomationSettings — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add three missing fields to `ProcessingPipelineContent` in `AutomationSettings.tsx`:
1. `auto_process_sync_fallback_engine` — Select (`ffsubsync` | `alass`), placed directly after the existing `auto_process_sync_threshold` number input.
2. `auto_nfo_export` — Toggle, placed after the existing `auto_process_credit_removal` toggle. **Note:** this field already exists in `AutomationSettings.tsx` and its test. Verify it is present before adding — if already there, skip the implementation step for it but keep the test assertion.
3. `streaming_enabled` — Toggle, placed last in the section (after `auto_nfo_export` / `jellyfin_play_translate_enabled`).

**Architecture:** Pure frontend change. Three tasks: tests first (RED), component update (GREEN), lint + commit. No backend changes — all three keys must already exist in `backend/config.py`.

**Tech Stack:** React 19, TypeScript, Vitest + Testing Library

---

## Task 1: Tests schreiben (danach ROT)

- [ ] **1.1 — mockConfig ergänzen**

  In `frontend/src/pages/Settings/__tests__/AutomationSettings.test.tsx`, add the two genuinely new keys to the `data` object inside the `useConfig` mock. Insert after `auto_process_sync_threshold`:

  ```typescript
  auto_process_sync_fallback_engine: 'ffsubsync',
  streaming_enabled: 'false',
  ```

  `auto_nfo_export` is already present in the mock (`'false'`). Do not add it again.

- [ ] **1.2 — auto_process_sync_fallback_engine Tests hinzufügen**

  Add these tests inside a new nested `describe` called `'Processing Pipeline — sync fallback engine'`:

  ```typescript
  describe('Processing Pipeline — sync fallback engine', () => {
    it('renders form-group for auto_process_sync_fallback_engine', () => {
      renderPage()
      expect(screen.getByTestId('form-group-auto-process-sync-fallback-engine')).toBeInTheDocument()
    })

    it('renders a <select> for auto_process_sync_fallback_engine', () => {
      renderPage()
      expect(screen.getByTestId('select-auto-process-sync-fallback-engine')).toBeInTheDocument()
    })

    it('select contains options "ffsubsync" and "alass"', () => {
      renderPage()
      const select = screen.getByTestId('select-auto-process-sync-fallback-engine') as HTMLSelectElement
      const options = Array.from(select.options).map((o) => o.value)
      expect(options).toContain('ffsubsync')
      expect(options).toContain('alass')
    })

    it('select shows the config value (ffsubsync)', () => {
      renderPage()
      const select = screen.getByTestId('select-auto-process-sync-fallback-engine') as HTMLSelectElement
      expect(select.value).toBe('ffsubsync')
    })

    it('calls updateConfig with auto_process_sync_fallback_engine on change', () => {
      renderPage()
      const select = screen.getByTestId('select-auto-process-sync-fallback-engine')
      fireEvent.change(select, { target: { value: 'alass' } })
      expect(mockMutate).toHaveBeenCalledWith({ auto_process_sync_fallback_engine: 'alass' })
    })

    it('select appears after input-auto-process-sync-threshold in the DOM', () => {
      renderPage()
      const section = screen.getByTestId('section-processing-pipeline')
      const threshold = section.querySelector('[data-testid="input-auto-process-sync-threshold"]')!
      const select = section.querySelector('[data-testid="select-auto-process-sync-fallback-engine"]')!
      expect(threshold.compareDocumentPosition(select) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    })
  })
  ```

- [ ] **1.3 — auto_nfo_export Test sicherstellen**

  Verify the existing test `'calls updateConfig with auto_nfo_export=true when toggled'` is already present in the file. It should be — check around line 518. If it is present, **no action needed** for this step. If it is missing (was deleted in a prior session), add:

  ```typescript
  it('calls updateConfig with auto_nfo_export=true when toggled', () => {
    renderPage()
    const fg = screen.getByTestId('form-group-auto-nfo-export')
    const toggle = fg.querySelector('[role="switch"]') as HTMLElement
    fireEvent.click(toggle)
    expect(mockMutate).toHaveBeenCalledWith({ auto_nfo_export: true })
  })
  ```

- [ ] **1.4 — streaming_enabled Tests hinzufügen**

  Add these tests inside a new nested `describe` called `'Processing Pipeline — streaming'`:

  ```typescript
  describe('Processing Pipeline — streaming', () => {
    it('renders form-group for streaming_enabled', () => {
      renderPage()
      expect(screen.getByTestId('form-group-streaming-enabled')).toBeInTheDocument()
    })

    it('streaming_enabled toggle reflects config value (false)', () => {
      renderPage()
      const fg = screen.getByTestId('form-group-streaming-enabled')
      const toggle = fg.querySelector('[role="switch"]')
      expect(toggle).toHaveAttribute('aria-checked', 'false')
    })

    it('calls updateConfig with streaming_enabled=true when toggled', () => {
      renderPage()
      const fg = screen.getByTestId('form-group-streaming-enabled')
      const toggle = fg.querySelector('[role="switch"]') as HTMLElement
      fireEvent.click(toggle)
      expect(mockMutate).toHaveBeenCalledWith({ streaming_enabled: true })
    })

    it('streaming_enabled form-group is the last element inside processing-pipeline-content', () => {
      renderPage()
      const content = screen.getByTestId('processing-pipeline-content')
      const formGroups = content.querySelectorAll('[data-testid^="form-group-"]')
      const last = formGroups[formGroups.length - 1]
      expect(last).toHaveAttribute('data-testid', 'form-group-streaming-enabled')
    })
  })
  ```

- [ ] **1.5 — Tests ausführen und ROT bestätigen**

  ```bash
  cd D:/Sublarr_Projekt/Sublarr/frontend && npm run test -- --run src/pages/Settings/__tests__/AutomationSettings.test.tsx
  ```

  Erwartetes Ergebnis: Die neuen Tests für `auto_process_sync_fallback_engine` (5) und `streaming_enabled` (4) schlagen fehl. Der `auto_nfo_export`-Test (falls vorhanden) bleibt grün. Erst wenn neue Tests ROT sind, weiter mit Task 2.

---

## Task 2: Komponente anpassen (GREEN)

- [ ] **2.1 — auto_process_sync_fallback_engine Select hinzufügen**

  In `frontend/src/pages/Settings/AutomationSettings.tsx`, in `ProcessingPipelineContent`, locate the existing `<FormGroup>` for `auto_process_sync_threshold` (ends around the closing `</FormGroup>`). Insert the following `<FormGroup>` immediately after it:

  ```tsx
  <FormGroup
    label="Sync Fallback Engine"
    hint="Synchronisation engine used when the primary sync attempt fails. ffsubsync is audio-based; alass is AI-based."
    htmlFor="auto-process-sync-fallback-engine"
    data-testid="form-group-auto-process-sync-fallback-engine"
  >
    <select
      id="auto-process-sync-fallback-engine"
      data-testid="select-auto-process-sync-fallback-engine"
      style={{
        ...inputStyle,
        maxWidth: '160px',
        cursor: 'pointer',
      }}
      value={strVal(config, 'auto_process_sync_fallback_engine', 'ffsubsync')}
      onChange={(e) => save({ auto_process_sync_fallback_engine: e.target.value })}
      disabled={updateConfig.isPending}
    >
      <option value="ffsubsync">ffsubsync</option>
      <option value="alass">alass</option>
    </select>
  </FormGroup>
  ```

- [ ] **2.2 — auto_nfo_export prüfen**

  Verify `form-group-auto-nfo-export` is already present in `ProcessingPipelineContent` (it should be — it was added in the prior key-fix session). The expected JSX is:

  ```tsx
  <FormGroup
    label="Export NFO Sidecar"
    hint="Write an NFO metadata sidecar file alongside each downloaded subtitle."
    data-testid="form-group-auto-nfo-export"
  >
    <Toggle
      checked={boolVal(config, 'auto_nfo_export', false)}
      onChange={(v) => save({ auto_nfo_export: v })}
      disabled={updateConfig.isPending}
    />
  </FormGroup>
  ```

  If the block is missing, insert it after the `auto_process_credit_removal` FormGroup. If it is already present, skip this sub-step.

- [ ] **2.3 — streaming_enabled Toggle als letztes Feld hinzufügen**

  In `ProcessingPipelineContent`, add the following `<FormGroup>` as the **last element** before the closing `</div>` of the `processing-pipeline-content` wrapper:

  ```tsx
  <FormGroup
    label="Streaming aktiviert"
    hint="Subtitle-Streaming-Modus aktivieren (experimentell). Erlaubt Live-Übertragung von Untertiteln an kompatible Player."
    data-testid="form-group-streaming-enabled"
  >
    <Toggle
      checked={boolVal(config, 'streaming_enabled', false)}
      onChange={(v) => save({ streaming_enabled: v })}
      disabled={updateConfig.isPending}
    />
  </FormGroup>
  ```

  Ensure this is placed after `form-group-jellyfin-play-translate-enabled` (the currently-last FormGroup in the section).

- [ ] **2.4 — TypeScript-Check ausführen**

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

  Erwartetes Ergebnis: alle Tests (alte + 9 neue) bestehen. Bei Fehlern die `data-testid`-Attribute und DOM-Reihenfolge mit den Testerwarungen abgleichen.

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
  git commit -m "feat: add sync fallback engine, auto NFO export and streaming fields to AutomationSettings"
  ```

  Inhalt des Commits:
  - `auto_process_sync_fallback_engine`: neues Select-Feld nach `auto_process_sync_threshold` (Optionen: `ffsubsync`, `alass`)
  - `auto_nfo_export`: falls fehlend ergänzt (Toggle nach `auto_process_credit_removal`)
  - `streaming_enabled`: neues Toggle-Feld als letztes Element im Processing-Pipeline-Abschnitt
  - mockConfig in Tests um beide neuen Schlüssel erweitert
  - 9 neue Tests für Rendering, Werte, Interaktionen und DOM-Reihenfolge

---

## Referenz: Neue und geprüfte Felder

| Config-Schlüssel | Typ | Default | Control | testid (form-group) | testid (control) |
|---|---|---|---|---|---|
| `auto_process_sync_fallback_engine` | String | `'ffsubsync'` | `<select>` | `form-group-auto-process-sync-fallback-engine` | `select-auto-process-sync-fallback-engine` |
| `auto_nfo_export` | Boolean | `false` | `<Toggle>` | `form-group-auto-nfo-export` | (via `role="switch"`) |
| `streaming_enabled` | Boolean | `false` | `<Toggle>` | `form-group-streaming-enabled` | (via `role="switch"`) |

## Referenz: Processing Pipeline Feldreihenfolge nach der Änderung

```
processing-pipeline-content
  ├─ form-group-wanted-auto-translate          (bestehend)
  ├─ form-group-auto-sync-after-download       (bestehend)
  ├─ form-group-auto-cleanup-after-extract     (bestehend)
  ├─ form-group-auto-process-common-fixes      (bestehend)
  ├─ form-group-auto-process-hi-removal        (bestehend)
  ├─ form-group-auto-process-credit-removal    (bestehend)
  ├─ form-group-auto-process-sync-threshold    (bestehend)
  ├─ form-group-auto-process-sync-fallback-engine  ← NEU
  ├─ form-group-auto-nfo-export                (bestehend / prüfen)
  ├─ form-group-jellyfin-play-translate-enabled (bestehend)
  └─ form-group-streaming-enabled              ← NEU (last)
```
