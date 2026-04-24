import type { ReactNode } from 'react'

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
  readonly title: string
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
  /** True when the user has enabled Expert Mode globally. */
  readonly expertMode?: boolean
  /** Maximum visible sections before a split-page warning is logged to console. */
  readonly sectionCap?: number
  readonly tocWidth?: number
}

const DEFAULT_SECTION_CAP = 6
const DEFAULT_TOC_WIDTH = 200

export function FormLayout({
  children,
  sections,
  healthRail,
  activeSectionId = null,
  expertMode = false,
  sectionCap = DEFAULT_SECTION_CAP,
  tocWidth = DEFAULT_TOC_WIDTH,
}: FormLayoutProps) {
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
                  className={`flex items-center justify-between text-[11px] px-2 py-1 rounded no-underline ${
                    s.id === activeSectionId
                      ? 'bg-[var(--accent-bg)] text-[var(--accent)] font-semibold border-l-2 border-l-[var(--accent)] pl-1.5'
                      : 'text-secondary hover:bg-[var(--bg-elevated)]'
                  }`}
                >
                  <span>{s.title}</span>
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
