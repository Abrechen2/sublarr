# AutomationSettings Config Key Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 8 wrong config keys in `AutomationSettings.tsx`, remove 2 non-existent fields, and remove the now-empty Sidecar & Cleanup section.

**Architecture:** Pure frontend change. Three tasks: tests first (RED), component fix (GREEN), lint + commit. No backend changes needed — all target keys exist in `backend/config.py`.

**Tech Stack:** React 19, TypeScript, Vitest + Testing Library

---

## Task 1: Tests anpassen (danach ROT)

- [ ] **1.1 — mockConfig ersetzen**

  In `frontend/src/pages/Settings/__tests__/AutomationSettings.test.tsx`, replace the `data` block inside `mockConfig` (currently lines 32–56) with the corrected keys:

  ```typescript
  data: {
    wanted_search_interval_hours: '6',
    webhook_auto_search: 'true',
    wanted_search_on_startup: 'false',
    upgrade_enabled: 'false',
    upgrade_min_score_delta: '10',
    upgrade_scan_interval_hours: '24',
    wanted_auto_translate: 'false',
    auto_sync_after_download: 'false',
    auto_cleanup_after_extract: 'false',
  },
  ```

- [ ] **1.2 — Tests für Sidecar & Cleanup entfernen**

  Remove the following test cases entirely from the test file:

  - `'renders the Sidecar & Cleanup section'`
  - `'shows "Sidecar & Cleanup" section title'`
  - `'keep_original_subs toggle reflects config value (true)'`
  - `'calls updateConfig with keep_original_subs=false when toggle is clicked'`
  - `'displays sidecar_format value from config'`
  - `'calls updateConfig with sidecar_format on change'`

- [ ] **1.3 — Sektionsanzahl-Test aktualisieren**

  Find the test `'renders exactly 6 settings sections'` and change the assertion from `6` to `5`:

  ```typescript
  it('renders exactly 5 settings sections', () => {
    render(<AutomationSettings />);
    const sections = screen.getAllByTestId(/^section-/);
    expect(sections).toHaveLength(5);
  });
  ```

- [ ] **1.4 — Search-Scan-Tests aktualisieren**

  Replace the following tests with the corrected versions:

  ```typescript
  it('displays wanted_search_interval_hours value from config', () => {
    render(<AutomationSettings />);
    const input = screen.getByTestId('input-wanted-search-interval-hours');
    expect(input).toHaveValue(6);
  });

  it('calls updateConfig with wanted_search_interval_hours on change', async () => {
    render(<AutomationSettings />);
    const input = screen.getByTestId('input-wanted-search-interval-hours');
    fireEvent.change(input, { target: { value: '120' } });
    await waitFor(() => {
      expect(mockMutate).toHaveBeenCalledWith({ wanted_search_interval_hours: 120 });
    });
  });

  it('auto_search_on_download toggle reflects config value (true)', () => {
    render(<AutomationSettings />);
    const formGroup = screen.getByTestId('form-group-webhook-auto-search');
    const toggle = within(formGroup).getByRole('checkbox');
    expect(toggle).toBeChecked();
  });

  it('scan_on_start toggle reflects config value (false)', () => {
    render(<AutomationSettings />);
    const formGroup = screen.getByTestId('form-group-wanted-search-on-startup');
    const toggle = within(formGroup).getByRole('checkbox');
    expect(toggle).not.toBeChecked();
  });

  it('calls updateConfig with wanted_search_on_startup=true when toggle is clicked', async () => {
    render(<AutomationSettings />);
    const formGroup = screen.getByTestId('form-group-wanted-search-on-startup');
    const toggle = within(formGroup).getByRole('checkbox');
    fireEvent.click(toggle);
    await waitFor(() => {
      expect(mockMutate).toHaveBeenCalledWith({ wanted_search_on_startup: true });
    });
  });
  ```

- [ ] **1.5 — Upgrade-Rules-Tests aktualisieren**

  Replace the following tests with the corrected versions:

  ```typescript
  it('auto_upgrade_enabled toggle reflects config value (false)', () => {
    render(<AutomationSettings />);
    const formGroup = screen.getByTestId('form-group-upgrade-enabled');
    const toggle = within(formGroup).getByRole('checkbox');
    expect(toggle).not.toBeChecked();
  });

  it('calls updateConfig with upgrade_enabled=true when toggle is clicked', async () => {
    render(<AutomationSettings />);
    const formGroup = screen.getByTestId('form-group-upgrade-enabled');
    const toggle = within(formGroup).getByRole('checkbox');
    fireEvent.click(toggle);
    await waitFor(() => {
      expect(mockMutate).toHaveBeenCalledWith({ upgrade_enabled: true });
    });
  });

  it('displays upgrade_min_score_delta value from config', () => {
    render(<AutomationSettings />);
    const input = screen.getByTestId('input-upgrade-min-score-delta');
    expect(input).toHaveValue(10);
  });

  it('calls updateConfig with upgrade_min_score_delta as number on change', async () => {
    render(<AutomationSettings />);
    const input = screen.getByTestId('input-upgrade-min-score-delta');
    fireEvent.change(input, { target: { value: '20' } });
    await waitFor(() => {
      expect(mockMutate).toHaveBeenCalledWith({ upgrade_min_score_delta: 20 });
    });
  });
  ```

- [ ] **1.6 — Processing-Pipeline-Tests aktualisieren**

  Replace the following tests with the corrected versions:

  ```typescript
  it('auto_translate toggle reflects config value (false)', () => {
    render(<AutomationSettings />);
    const formGroup = screen.getByTestId('form-group-wanted-auto-translate');
    const toggle = within(formGroup).getByRole('checkbox');
    expect(toggle).not.toBeChecked();
  });

  it('calls updateConfig with wanted_auto_translate=true when toggle is clicked', async () => {
    render(<AutomationSettings />);
    const formGroup = screen.getByTestId('form-group-wanted-auto-translate');
    const toggle = within(formGroup).getByRole('checkbox');
    fireEvent.click(toggle);
    await waitFor(() => {
      expect(mockMutate).toHaveBeenCalledWith({ wanted_auto_translate: true });
    });
  });

  it('calls updateConfig with auto_sync_after_download=true when toggle is clicked', async () => {
    render(<AutomationSettings />);
    const formGroup = screen.getByTestId('form-group-auto-sync-after-download');
    const toggle = within(formGroup).getByRole('checkbox');
    fireEvent.click(toggle);
    await waitFor(() => {
      expect(mockMutate).toHaveBeenCalledWith({ auto_sync_after_download: true });
    });
  });

  it('calls updateConfig with auto_cleanup_after_extract=true when toggle is clicked', async () => {
    render(<AutomationSettings />);
    const formGroup = screen.getByTestId('form-group-auto-cleanup-after-extract');
    const toggle = within(formGroup).getByRole('checkbox');
    fireEvent.click(toggle);
    await waitFor(() => {
      expect(mockMutate).toHaveBeenCalledWith({ auto_cleanup_after_extract: true });
    });
  });
  ```

- [ ] **1.7 — Tests ausführen und RED bestätigen**

  ```bash
  cd frontend && npm run test -- --run src/pages/Settings/__tests__/AutomationSettings.test.tsx
  ```

  Erwartetes Ergebnis: mehrere Fehler (testids und Schlüssel stimmen noch nicht mit der Komponente überein). Erst wenn Tests ROT sind, weiter mit Task 2.

---

## Task 2: Komponente anpassen

- [ ] **2.1 — SearchScanContent ersetzen**

  In `frontend/src/pages/Settings/AutomationSettings.tsx`, replace the entire `SearchScanContent` inner function (all 3 FormGroups) with:

  ```tsx
  const SearchScanContent = () => (
    <>
      <FormGroup
        label="Wanted Search Interval (hours)"
        hint="How often (in hours) Sublarr searches for missing subtitles."
        htmlFor="wanted-search-interval-hours"
        data-testid="form-group-wanted-search-interval-hours"
      >
        <input
          id="wanted-search-interval-hours"
          type="number"
          data-testid="input-wanted-search-interval-hours"
          style={{ ...inputStyle, maxWidth: '120px' }}
          value={strVal(config, 'wanted_search_interval_hours', '6')}
          onChange={(e) => save({ wanted_search_interval_hours: Number(e.target.value) })}
          disabled={updateConfig.isPending}
          min={1}
          placeholder="6"
        />
      </FormGroup>

      <FormGroup
        label="Auto-Search on Download"
        hint="Automatically trigger a subtitle search after a new download is detected."
        data-testid="form-group-webhook-auto-search"
      >
        <Toggle
          checked={boolVal(config, 'webhook_auto_search', true)}
          onChange={(v) => save({ webhook_auto_search: v })}
          disabled={updateConfig.isPending}
        />
      </FormGroup>

      <FormGroup
        label="Search on Startup"
        hint="Run a wanted search every time Sublarr starts."
        data-testid="form-group-wanted-search-on-startup"
      >
        <Toggle
          checked={boolVal(config, 'wanted_search_on_startup', false)}
          onChange={(v) => save({ wanted_search_on_startup: v })}
          disabled={updateConfig.isPending}
        />
      </FormGroup>
    </>
  );
  ```

- [ ] **2.2 — UpgradeRulesContent ersetzen**

  Replace the entire `UpgradeRulesContent` inner function (all 3 FormGroups) with:

  ```tsx
  const UpgradeRulesContent = () => (
    <>
      <FormGroup
        label="Auto-Upgrade Enabled"
        hint="Automatically replace existing subtitles when a higher-scoring one is found."
        data-testid="form-group-upgrade-enabled"
      >
        <Toggle
          checked={boolVal(config, 'upgrade_enabled', false)}
          onChange={(v) => save({ upgrade_enabled: v })}
          disabled={updateConfig.isPending}
        />
      </FormGroup>

      <FormGroup
        label="Minimum Score Delta"
        hint="Minimum score improvement required before replacing an existing subtitle."
        htmlFor="upgrade-min-score-delta"
        data-testid="form-group-upgrade-min-score-delta"
      >
        <input
          id="upgrade-min-score-delta"
          type="number"
          data-testid="input-upgrade-min-score-delta"
          style={{ ...inputStyle, maxWidth: '120px' }}
          value={strVal(config, 'upgrade_min_score_delta', '10')}
          onChange={(e) => save({ upgrade_min_score_delta: Number(e.target.value) })}
          disabled={updateConfig.isPending}
          min={0}
          placeholder="10"
        />
      </FormGroup>

      <FormGroup
        label="Upgrade Scan Interval (hours)"
        hint="How often (in hours) existing subtitles are checked for upgrade candidates."
        htmlFor="upgrade-scan-interval-hours"
        data-testid="form-group-upgrade-scan-interval-hours"
      >
        <input
          id="upgrade-scan-interval-hours"
          type="number"
          data-testid="input-upgrade-scan-interval-hours"
          style={{ ...inputStyle, maxWidth: '120px' }}
          value={strVal(config, 'upgrade_scan_interval_hours', '24')}
          onChange={(e) => save({ upgrade_scan_interval_hours: Number(e.target.value) })}
          disabled={updateConfig.isPending}
          min={1}
          placeholder="24"
        />
      </FormGroup>
    </>
  );
  ```

- [ ] **2.3 — ProcessingPipelineContent ersetzen**

  Replace the entire `ProcessingPipelineContent` inner function (all 3 FormGroups) with:

  ```tsx
  const ProcessingPipelineContent = () => (
    <>
      <FormGroup
        label="Auto-Translate"
        hint="Automatically translate downloaded subtitles to the target language."
        data-testid="form-group-wanted-auto-translate"
      >
        <Toggle
          checked={boolVal(config, 'wanted_auto_translate', false)}
          onChange={(v) => save({ wanted_auto_translate: v })}
          disabled={updateConfig.isPending}
        />
      </FormGroup>

      <FormGroup
        label="Auto-Sync"
        hint="Automatically synchronise subtitles to video timing after download."
        data-testid="form-group-auto-sync-after-download"
      >
        <Toggle
          checked={boolVal(config, 'auto_sync_after_download', false)}
          onChange={(v) => save({ auto_sync_after_download: v })}
          disabled={updateConfig.isPending}
        />
      </FormGroup>

      <FormGroup
        label="Auto-Cleanup"
        hint="Remove duplicate and redundant subtitle files automatically after extract."
        data-testid="form-group-auto-cleanup-after-extract"
      >
        <Toggle
          checked={boolVal(config, 'auto_cleanup_after_extract', false)}
          onChange={(v) => save({ auto_cleanup_after_extract: v })}
          disabled={updateConfig.isPending}
        />
      </FormGroup>
    </>
  );
  ```

- [ ] **2.4 — SidecarCleanupContent Funktion entfernen**

  Remove the entire `SidecarCleanupContent` function definition from the component file. It contains FormGroups for `keep_original_subs` and `sidecar_format` — both keys do not exist in the backend.

- [ ] **2.5 — section-sidecar-cleanup aus JSX entfernen**

  In the JSX return of the component, remove the entire `<div data-testid="section-sidecar-cleanup">` block including its `<SettingsSection>` wrapper and all children. The page now renders 5 sections instead of 6.

- [ ] **2.6 — TypeScript-Check ausführen**

  ```bash
  cd frontend && npx tsc --noEmit
  ```

  Erwartetes Ergebnis: keine Fehler. Falls Fehler auftreten (z. B. durch entfernte Variablen oder falsche Typen), vor dem nächsten Schritt beheben.

---

## Task 3: Tests grün + committen

- [ ] **3.1 — Tests ausführen und GREEN bestätigen**

  ```bash
  cd frontend && npm run test -- --run src/pages/Settings/__tests__/AutomationSettings.test.tsx
  ```

  Erwartetes Ergebnis: alle Tests bestehen. Falls Tests noch fehlschlagen, Abweichungen zwischen Testerwartungen und Komponenten-testids/Schlüsseln prüfen und beheben, bevor fortgefahren wird.

- [ ] **3.2 — ESLint ausführen**

  ```bash
  cd frontend && npm run lint
  ```

  Alle Warnungen und Fehler beheben, die durch die Änderungen entstanden sind (insbesondere ungenutzte Variablen nach dem Entfernen von `SidecarCleanupContent`).

- [ ] **3.3 — Vollständige Testsuite ausführen**

  ```bash
  cd frontend && npm run test -- --run
  ```

  Sicherstellen, dass keine anderen Tests durch die Änderungen an `AutomationSettings` gebrochen wurden.

- [ ] **3.4 — Commit erstellen**

  ```bash
  git add frontend/src/pages/Settings/AutomationSettings.tsx \
          frontend/src/pages/Settings/__tests__/AutomationSettings.test.tsx
  git commit -m "fix: rewrite AutomationSettings with correct backend config keys"
  ```

  Inhalt des Commits:
  - 8 falsche Config-Schlüssel durch korrekte Backend-Schlüssel ersetzt
  - Einheiten korrigiert: Minuten → Stunden für Intervall-Felder
  - 2 nicht existierende Felder entfernt (`keep_original_subs`, `sidecar_format`)
  - Leere Sektion `section-sidecar-cleanup` entfernt (6 → 5 Sektionen)
  - Test-mockConfig und alle betroffenen Tests aktualisiert

---

## Referenz: Vollständige Schlüssel-Mapping-Tabelle

| Alter Frontend-Schlüssel | Neuer Backend-Schlüssel | Typ | Anmerkung |
|---|---|---|---|
| `wanted_search_frequency` | `wanted_search_interval_hours` | Number | Einheit: Minuten → Stunden |
| `scan_on_start` | `wanted_search_on_startup` | Boolean | |
| `auto_upgrade_enabled` | `upgrade_enabled` | Boolean | |
| `auto_upgrade_threshold` | `upgrade_min_score_delta` | Number | |
| `upgrade_check_frequency` | `upgrade_scan_interval_hours` | Number | Einheit: Minuten → Stunden |
| `auto_translate` | `wanted_auto_translate` | Boolean | |
| `auto_search_on_download` | `webhook_auto_search` | Boolean | |
| `auto_sync` | `auto_sync_after_download` | Boolean | |
| `auto_cleanup` | `auto_cleanup_after_extract` | Boolean | |
| `keep_original_subs` | ENTFERNT | — | Existiert nicht im Backend |
| `sidecar_format` | ENTFERNT | — | Existiert nicht im Backend |

## Referenz: Vollständige testid-Mapping-Tabelle

| Alter testid | Neuer testid |
|---|---|
| `input-wanted-search-frequency` | `input-wanted-search-interval-hours` |
| `form-group-wanted-search-frequency` | `form-group-wanted-search-interval-hours` |
| `form-group-auto-search-on-download` | `form-group-webhook-auto-search` |
| `form-group-scan-on-start` | `form-group-wanted-search-on-startup` |
| `form-group-auto-upgrade-enabled` | `form-group-upgrade-enabled` |
| `input-auto-upgrade-threshold` | `input-upgrade-min-score-delta` |
| `form-group-auto-upgrade-threshold` | `form-group-upgrade-min-score-delta` |
| `input-upgrade-check-frequency` | `input-upgrade-scan-interval-hours` |
| `form-group-upgrade-check-frequency` | `form-group-upgrade-scan-interval-hours` |
| `form-group-auto-translate` | `form-group-wanted-auto-translate` |
| `form-group-auto-sync` | `form-group-auto-sync-after-download` |
| `form-group-auto-cleanup` | `form-group-auto-cleanup-after-extract` |
