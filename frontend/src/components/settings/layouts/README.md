# Settings Layout Scaffolds

Three unified templates for every Settings page in Sublarr, per the
Codex architectural blueprint (see `mockups/settings-templates-concept.html`
and `docs/DECISIONS.md` for rationale).

## The three templates

### A — `<CollectionLayout>` (Master-Detail)

Use when the page is a **list of objects** where the user picks one at a
time to edit.

**Used for:** Providers · Connections (Sonarr/Radarr/MediaServer instances)
· Notification Channels · Scheduler Jobs · Plugins · Hooks · Profiles ·
Prompt Presets · Post-Processing Pipeline steps.

```tsx
<CollectionLayout
  items={providers}
  selectedId={selectedId}
  getItemId={(p) => p.id}
  renderListItem={(p, active) => <ProviderTile provider={p} active={active} />}
  renderDetail={(p) => p ? <ProviderDetail provider={p} /> : <EmptyHint />}
  onSelect={setSelectedId}
  onAdd={handleAddProvider}
  healthRail={<HealthRail items={providerHealth} />}
/>
```

### B — `<FormLayout>` (Scroll-form + Section TOC)

Use when the page is a **bounded set of related settings** grouped into
finite sections. The right rail provides scroll-spy navigation.

**Used for:** General · Languages & Matching · Automation Cadence ·
Subtitle Scoring · About.

**Cap at 5–6 sections.** At 7+ sections, split into a sub-page — the TOC
is for orientation inside one mental model, not license for unbounded
forms. A dev-mode `console.warn` fires if you exceed the cap.

```tsx
<FormLayout
  sections={[
    { id: 'appearance', title: 'Appearance' },
    { id: 'identity',   title: 'Identity' },
    { id: 'logging',    title: 'Logging', advancedCount: 2 },
    { id: 'backups',    title: 'Backups' },
    { id: 'security',   title: 'API & security', expertOnly: true },
  ]}
  expertMode={showExpert}
  activeSectionId={activeSection}
>
  <section id="appearance"><SettingsSection title="Appearance">…</SettingsSection></section>
  <section id="identity"><SettingsSection title="Identity">…</SettingsSection></section>
  {/* … */}
</FormLayout>
```

### C — `<RulesLayout>` (Inheritance / Overrides)

Use when the primary UX is **"understand what wins, what's inherited,
where to override"** — not "edit this object" (A) and not "fill this
page" (B).

**Used for:** Profiles & Overrides · per-Series overrides · per-Movie
overrides · Quiet-Hours policies.

The scope tree is a **control inside the left pane**, not a separate
template. Nested hierarchies (Global → Profile → Series) are rendered
as indented rows in the `scopeTree` slot — caller decides tree vs.
flat-with-indent.

```tsx
<RulesLayout
  breadcrumb={<Breadcrumbs trail={['Profiles', profile.name, series.title]} />}
  scopeTree={<ScopeTree selected={selectedScope} onSelect={setScope} />}
  resolvedHeader={
    <ResolvedValueBox
      setting="cleanup_foreign_tracks"
      chain={['Global: Off', 'Profile: Inherit', 'Series: Always']}
      effective="Always strip"
    />
  }
  overrideWidget={<OverrideTriState value={value} onChange={setValue} />}
  otherRules={
    <RuleSummaryList rules={[
      { label: 'priority_override', source: 'overridden', effective: 'premium' },
      { label: 'min_attempts_per_day', source: 'inherited', effective: '3' },
    ]} />
  }
/>
```

## Shared primitives

Located in `../primitives/`. Use them inside all three templates instead
of re-rolling each concept per page:

- `<InheritanceRow>` — inherited/overridden pill + effective value.
- `<BudgetBar>` — live quota with remaining/reset/hard-stop pills.
- `<ApiKeyField>` — masked input + Test-Connection + scope detection.
- `<ConnectionTest>` — stand-alone state-machine button (idle → testing
  → ok / fail). Use for Sonarr/Radarr/MediaServer/Ollama/provider tests.
- `<HealthRail>` — the right-edge rail itself, rendered as a prop.

### Not primitives yet (Codex recommendation — wait until second use)

- Priority drag-drop list — extract when a second screen needs it.
- Cron builder (with inline preview) — extract when used in 2+ screens.
  Preview stays inside the builder, no separate primitive.
- Regex live-tester — wait.
- Notification-template editor — wait.

## Migration strategy — Hybrid Ratchet

Per Codex's explicit recommendation for a solo maintainer:

1. **Land the scaffold** (this folder). No page rewrites yet. ✓ Done.
2. **Migrate three reference pages immediately:**
   - `General` → `FormLayout`
   - `Providers` → `CollectionLayout`
   - `Profiles & Overrides` → `RulesLayout`
3. **Ratchet rule** for everything else:
   - Any **new** Settings page MUST use a template. No exceptions.
   - Any **existing** page touched for feature work MUST be migrated as
     part of that work.
   - Pages never touched for features stay legacy — no speculative
     rewrites.

**Hard rule:** never combine a framework-migration commit with a feature
commit. Migrate first (one commit), then add features on top (second
commit). Keeps `git bisect` sane.

## Conventions (lock these before the first migration)

Codex's five watch-outs, codified here so every migration follows the
same contract. Violations caught in review.

### 1. Vocabulary — lock these four words

The Settings area uses an exact vocabulary. Every prop, test-id,
i18n key, and CSS class uses these words consistently. Do not
introduce synonyms.

| Word | Meaning | Applies to |
|------|---------|-----------|
| **scope** | A level in the inheritance hierarchy (Global, Profile, Series, Movie). Never "level", "tier", "bucket". | `RulesLayout`, `InheritanceRow`, URL params |
| **section** | A visual grouping inside a FormLayout page (Appearance, Logging, …). Never "block", "group", "card". | `FormLayout`, `FormSectionDef`, anchor ids |
| **override** | A scope-level value that replaces an inherited one. Never "customisation", "local value", "per-X setting". | `InheritanceRow`, PATCH request bodies, DB columns |
| **effective** | The resolved value AFTER applying all overrides in the chain. Never "actual", "final", "applied". | `InheritanceRow`, backend response fields (see `cleanup_foreign_tracks_effective`) |

### 2. i18n in contracts, never display strings

Primitives and layouts accept i18n **keys** (`titleKey: 'settings.general.appearance'`),
not display strings. The primitive resolves via `useTranslation(ns)`
internally. This prevents English leaking into the UI.

Exception: free-form content that is never localized (URLs, API keys,
file paths, user-entered instance names).

When passing a label to `<ConnectionTest label={...}>`: the caller
translates (`t('settings.common.test_connection')`) because the button
text often includes context from the caller's scope.

### 3. `data-testid` convention — `settings.<page>.<slot>`

All settings components emit `data-testid` values following:

```
settings.<page-or-section>.<slot>[.qualifier]
```

Examples:
- `settings.providers.list` — the master list in CollectionLayout
- `settings.providers.detail` — the detail editor pane
- `settings.providers.opensubtitles.api-key` — specific field
- `settings.rules.scope-tree` — scope tree control in RulesLayout
- `settings.rules.resolved-header` — resolved-value banner

The built-in slot test-ids (`collection-layout`, `collection-list`,
`form-toc`, `rules-scope-tree`, etc.) are the **primitive-level**
hooks — keep those. Page-level additions follow the dotted pattern
above so a test query like `[data-testid^="settings.providers."]`
yields a whole page.

### 4. Tailwind + CSS-vars: don't mix dynamic

The codebase uses Tailwind utilities with `@theme inline` mapping to
`--bg-*` / `--text-*` / `--accent` / `--border` CSS vars.
**Do not generate Tailwind classes dynamically** from CSS-var values,
e.g. `className={`bg-[${varName}]`}`. That defeats Tailwind's
tree-shaking and breaks JIT purging.

Prefer:
- Static utility classes (`bg-surface text-muted border-border`)
- Inline `style={{ background: someVar }}` for runtime-computed values
  (progress bar widths, pulse colors keyed on state)

See `frontend/STYLING.md` at repo root for the Strategic-Tailwind
direction adopted 2026-04-18.

### 5. Accessibility & keyboard

Every layout primitive must produce:

- **URL-addressable state** — the selected CollectionLayout item, the
  active FormLayout section, and the current RulesLayout scope all live
  in the URL (`?id=`, `#section-id`, `?scope=`). Page refreshes preserve
  user position.
- **Focus management on layout swap** — when the scope/item/section
  changes, move keyboard focus to the new detail heading (not the
  list). RulesLayout + CollectionLayout own this responsibility in
  their onSelect handlers.
- `aria-live="polite"` on any rail or banner that updates async (e.g.
  the `<HealthRail>` when health-check results come in).
- `aria-label` on the scope tree, list, and TOC navs.

Run the frontend a11y lint before landing any migration commit:
```
npm run lint:a11y   # (alias for eslint --rulesdir .eslintrc.a11y.js if configured)
```

## Reference files

- `mockups/settings-templates-concept.html` — visual reference for all
  three templates side-by-side with annotations.
- `mockups/settings-ui-concept.html` — detailed provider editor showing
  every Codex principle in one screen.
- `mockups/onboarding-wizard-concept.html` — the separate WizardLayout
  (not covered here).
- `frontend/STYLING.md` — Strategic-Tailwind policy (adopted
  2026-04-18).
