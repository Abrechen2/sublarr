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
- `<HealthRail>` — the right-edge rail itself, rendered as a prop.

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

## Reference files

- `mockups/settings-templates-concept.html` — visual reference for all
  three templates side-by-side with annotations.
- `mockups/settings-ui-concept.html` — detailed provider editor showing
  every Codex principle in one screen.
- `mockups/onboarding-wizard-concept.html` — the separate WizardLayout
  (not covered here).
