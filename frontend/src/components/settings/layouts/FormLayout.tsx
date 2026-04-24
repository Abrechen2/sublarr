import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

/**
 * FormLayout — Settings Template B (Scroll-form + right TOC).
 *
 * Use for BOUNDED categorical pages where the user reads/edits a finite set
 * of related settings grouped into sections. Examples: General, Languages &
 * Matching, Automation Cadence, Subtitle Scoring, About.
 *
 * NOT for: lists of objects (CollectionLayout) or inheritance (RulesLayout).
 *
 * Scaling rule: cap at 5–6 sections. At 7+, split into a sub-page — TOC is
 * for orientation inside one mental model, not license for unbounded forms.
 *
 * Reference mockup: mockups/settings-templates-concept.html (§ Template B).
 */

export interface FormSectionDef {
  readonly id: string
  /**
   * i18n key for the section title. Resolved by FormLayout via
   * useTranslation(ns). This is the ONLY contract — do not pass raw
   * display strings. The ns defaults to 'settings' but can be overridden
   * per-layout via FormLayoutProps.i18nNamespace.
   */
  readonly titleKey: string
  readonly advancedCount?: number
  readonly expertOnly?: boolean
}

export interface FormLayoutProps {
  /** The scrollable form body. Caller renders its own <section id="…"> blocks. */
  readonly children: ReactNode
  /** Section metadata used by the right-side TOC. Order matches scroll order. */
  readonly sections: readonly FormSectionDef[]
  /** Optional right-side health rail. Rendered below the TOC. */
  readonly healthRail?: ReactNode
  /** Currently-active section id for scroll-spy highlight. Caller-managed. */
  readonly activeSectionId?: string | null
  /**
   * Fired when the user clicks a TOC entry. Callers use this to push the
   * anchor to the URL (#section-id) and/or scroll with their own smoothing
   * policy. If omitted, the <a href="#id"> fallback handles navigation
   * natively.
   */
  readonly onSectionChange?: (id: string) => void
  /** True when the user has enabled Expert Mode globally. */
  readonly expertMode?: boolean
  /** Maximum visible sections before a split-page warning is logged to console. */
  readonly sectionCap?: number
  /** i18n namespace used to resolve FormSectionDef.titleKey. Default 'settings'. */
  readonly i18nNamespace?: string
  readonly tocWidth?: number
}

const DEFAULT_SECTION_CAP = 6
const DEFAULT_TOC_WIDTH = 200

export function FormLayout({
  children,
  sections,
  healthRail,
  activeSectionId = null,
  onSectionChange,
  expertMode = false,
  sectionCap = DEFAULT_SECTION_CAP,
  i18nNamespace = 'settings',
  tocWidth = DEFAULT_TOC_WIDTH,
}: FormLayoutProps) {
  const { t } = useTranslation(i18nNamespace)
  const visibleSections = expertMode
    ? sections
    : sections.filter((s) => !s.expertOnly)

  if (import.meta.env.DEV && visibleSections.length > sectionCap) {
    console.warn(
      `FormLayout: ${visibleSections.length} sections > cap ${sectionCap}. ` +
        `Consider splitting this page — see Codex blueprint / mockups/settings-templates-concept.html.`,
    )
  }

  const hiddenExpertCount = sections.filter((s) => s.expertOnly).length

  return (
    <div
      data-testid="form-layout"
      className="grid gap-5"
      style={{ gridTemplateColumns: `1fr ${tocWidth}px` }}
    >
      {/* Scroll content */}
      <div
        data-testid="form-content"
        className="bg-[var(--bg-surface)] border border-[var(--border)] rounded-lg p-6"
      >
        {children}
      </div>

      {/* Right rail: TOC + health */}
      <aside
        data-testid="form-toc"
        className="self-start sticky top-4 flex flex-col gap-3"
      >
        <nav
          className="bg-[var(--bg-surface)] border border-[var(--border)] rounded-lg p-3"
          aria-label="Page sections"
        >
          <h3 className="text-[10px] font-bold uppercase tracking-wider text-muted m-0 mb-2 px-1">
            On this page
          </h3>
          <ul className="flex flex-col gap-0.5 m-0 p-0 list-none">
            {visibleSections.map((s) => (
              <li key={s.id}>
                <a
                  href={`#${s.id}`}
                  data-testid="form-toc-item"
                  data-active={s.id === activeSectionId ? 'true' : 'false'}
                  onClick={(e) => {
                    if (onSectionChange) {
                      e.preventDefault()
                      onSectionChange(s.id)
                    }
                  }}
                  className={`flex items-center justify-between text-[11px] px-2 py-1 rounded no-underline ${
                    s.id === activeSectionId
                      ? 'bg-[var(--accent-bg)] text-[var(--accent)] font-semibold border-l-2 border-l-[var(--accent)] pl-1.5'
                      : 'text-secondary hover:bg-[var(--bg-elevated)]'
                  }`}
                >
                  <span>{t(s.titleKey)}</span>
                  {s.advancedCount !== undefined && s.advancedCount > 0 && (
                    <span className="text-[9px] text-muted">{s.advancedCount}</span>
                  )}
                </a>
              </li>
            ))}
          </ul>

          {hiddenExpertCount > 0 && !expertMode && (
            <div
              data-testid="form-expert-hint"
              className="mt-3 p-2 bg-[var(--bg-elevated)] rounded text-[10px] text-muted border border-[var(--border)]"
            >
              <strong className="text-[var(--accent)]">Expert mode: off</strong>
              <br />
              Toggle to reveal {hiddenExpertCount} hidden item
              {hiddenExpertCount > 1 ? 's' : ''}.
            </div>
          )}
        </nav>

        {healthRail && <div data-testid="form-rail">{healthRail}</div>}
      </aside>
    </div>
  )
}
