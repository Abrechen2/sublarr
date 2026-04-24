/**
 * Settings layout scaffolds — three templates per the Codex blueprint.
 *
 *   A) CollectionLayout — master-detail list of objects (Providers, Channels, …)
 *   B) FormLayout       — scroll-form with right-side Section-TOC (General, …)
 *   C) RulesLayout      — inheritance / override resolution (Profiles, per-Series)
 *
 * See ./README.md for usage + migration strategy (Hybrid Ratchet).
 * Visual reference: mockups/settings-templates-concept.html at repo root.
 */

export { CollectionLayout } from './CollectionLayout'
export type { CollectionLayoutProps } from './CollectionLayout'

export { FormLayout } from './FormLayout'
export type { FormLayoutProps, FormSectionDef } from './FormLayout'

export { RulesLayout } from './RulesLayout'
export type { RulesLayoutProps } from './RulesLayout'
