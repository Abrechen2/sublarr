/**
 * WaveformCueList — synchronized read-only cue list under the waveform.
 *
 * Stacked-Lanes layout follow-up: gives the editor a quiet text lane for
 * reading prev/next dialogue while the wave handles audio. First pass is
 * read-only — selection only. Inline text editing, add/delete, split/merge
 * are layered in subsequent steps.
 *
 * Bidirectional-selection guard: the `selectionOrigin` prop tells us whether
 * the current selection came from a wave click ("wave"), a keyboard nudge
 * ("keyboard"), or a row click on this list ("list"). We auto-scroll the
 * active row into view ONLY when origin !== "list" — otherwise we'd fight
 * the user's own scroll position right after they clicked a row.
 */
import { useEffect, useMemo, useRef, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { detectGapsAndOverlaps } from './gapOverlap'
import { formatCueTextForDisplay } from './cueTextDisplay'

export interface CueListRow {
  start: number
  end: number
  text: string
}

export type SelectionOrigin = 'wave' | 'list' | 'keyboard' | null

interface WaveformCueListProps {
  cues: CueListRow[]
  selectedCueIdx: number | null
  selectionOrigin?: SelectionOrigin
  onSelectCue: (idx: number, origin: 'list') => void
  collapsed?: boolean
  gapToleranceMs?: number
  /**
   * Optional [startSec, endSec] visible window of the wave. Cues whose
   * [start, end] intersect this range get a visible tint and — unless the
   * editor recently scrolled the list manually — the list auto-follows the
   * wave by scrolling so the first in-viewport cue lands at the top.
   */
  visibleRange?: [number, number] | null
  /**
   * Current playhead time in seconds. The cue containing the playhead gets
   * a distinct "now-playing" highlight while audio is playing.
   */
  playheadSec?: number
  /** Drives whether the now-playing highlight is shown. */
  isPlaying?: boolean
  /**
   * Inline text-edit commit. When omitted, rows are read-only (current
   * behaviour for locked surfaces). When provided, double-click on the
   * text cell opens a textarea; Enter (without Shift) commits, Esc cancels.
   */
  onTextChange?: (idx: number, text: string) => void
}

function formatTimecode(sec: number): string {
  if (!Number.isFinite(sec) || sec < 0) sec = 0
  const totalMs = Math.round(sec * 1000)
  const ms = totalMs % 1000
  const totalSec = Math.floor(totalMs / 1000)
  const s = totalSec % 60
  const totalMin = Math.floor(totalSec / 60)
  const m = totalMin % 60
  const h = Math.floor(totalMin / 60)
  const pad2 = (n: number) => n.toString().padStart(2, '0')
  const pad3 = (n: number) => n.toString().padStart(3, '0')
  return `${pad2(h)}:${pad2(m)}:${pad2(s)}.${pad3(ms)}`
}

export function WaveformCueList({
  cues,
  selectedCueIdx,
  selectionOrigin = null,
  onSelectCue,
  collapsed = false,
  gapToleranceMs = 80,
  visibleRange = null,
  playheadSec = 0,
  isPlaying = false,
  onTextChange,
}: WaveformCueListProps) {
  const { t } = useTranslation('editor')
  const listRef = useRef<HTMLDivElement>(null)
  const activeRowRef = useRef<HTMLDivElement>(null)
  const firstInViewportRowRef = useRef<HTMLDivElement>(null)
  // Inline-edit local state. `null` = no row in edit mode. We only allow
  // ONE row at a time so the user can't fork edits across cues.
  const [editingIdx, setEditingIdx] = useState<number | null>(null)
  const [editingDraft, setEditingDraft] = useState<string>('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const beginEdit = useCallback((idx: number, displayText: string) => {
    setEditingIdx(idx)
    setEditingDraft(displayText)
  }, [])

  const commitEdit = useCallback(() => {
    if (editingIdx === null) return
    const idx = editingIdx
    const draft = editingDraft
    setEditingIdx(null)
    setEditingDraft('')
    onTextChange?.(idx, draft)
  }, [editingIdx, editingDraft, onTextChange])

  const cancelEdit = useCallback(() => {
    setEditingIdx(null)
    setEditingDraft('')
  }, [])

  // Auto-focus + select-all when entering edit mode.
  useEffect(() => {
    if (editingIdx === null) return
    const el = textareaRef.current
    if (!el) return
    el.focus()
    el.select()
  }, [editingIdx])

  // Cancel pending edit when the underlying cues array changes (e.g. an
  // undo lands while the user is mid-typing). Without this guard the
  // textarea would commit stale text against the wrong row.
  useEffect(() => {
    if (editingIdx === null) return
    if (editingIdx >= cues.length) {
      setEditingIdx(null)
      setEditingDraft('')
    }
  }, [cues.length, editingIdx])
  // Suppress wave→list auto-follow for ~3 s after the editor manually
  // scrolled the list. Without this, the list would yank itself away
  // from where they're reading every time the wave's viewport changes.
  const userScrolledAtRef = useRef<number>(0)

  // Quality-dot sets keyed by the index of the EARLIER cue in the pair.
  // We render the dot on that row because the defect lives "between this
  // cue and the next one" — placing it on the earlier row matches the
  // reading order.
  const { gapIndices, overlapIndices } = useMemo(() => {
    const ranges = cues.map((c, idx) => ({
      id: String(idx),
      start: c.start,
      end: c.end,
    }))
    const { tightGaps, overlaps } = detectGapsAndOverlaps(ranges, {
      gapToleranceMs,
    })
    const gap = new Set<number>(tightGaps.map((g) => Number(g.prevId)))
    const overlap = new Set<number>(overlaps.map((o) => Number(o.prevId)))
    return { gapIndices: gap, overlapIndices: overlap }
  }, [cues, gapToleranceMs])

  // Currently-playing cue: first cue whose [start, end) contains the
  // playhead. Recomputes on every prop change but we cap the search via
  // an early exit because cues are time-sorted in practice.
  const playingIdx = useMemo<number | null>(() => {
    if (!isPlaying || playheadSec <= 0 || cues.length === 0) return null
    for (let i = 0; i < cues.length; i++) {
      const c = cues[i]
      if (playheadSec >= c.start && playheadSec < c.end) return i
      if (c.start > playheadSec) break
    }
    return null
  }, [cues, playheadSec, isPlaying])

  // First cue whose [start, end] intersects the wave viewport. Used as
  // the auto-follow scroll anchor when the wave scrolls horizontally.
  const firstInViewportIdx = useMemo<number | null>(() => {
    if (!visibleRange) return null
    const [from, to] = visibleRange
    for (let i = 0; i < cues.length; i++) {
      const c = cues[i]
      if (c.end >= from && c.start <= to) return i
    }
    return null
  }, [cues, visibleRange])

  // Auto-scroll: only when the selection arrived from somewhere OTHER than
  // a click on this list. Wave click + keyboard nudges should center the
  // active row; a list click already put the row where the user wants it.
  useEffect(() => {
    if (selectedCueIdx === null) return
    if (selectionOrigin === 'list') return
    const el = activeRowRef.current
    if (!el) return
    el.scrollIntoView({ block: 'center', behavior: 'smooth' })
  }, [selectedCueIdx, selectionOrigin])

  // Wave→list auto-follow: when the wave scrolls horizontally and changes
  // its visible window, scroll the list so the first in-viewport cue
  // lands at the top — UNLESS the editor scrolled the list themselves in
  // the last 3 s (then we respect their intent and don't yank it back).
  useEffect(() => {
    if (firstInViewportIdx === null) return
    if (Date.now() - userScrolledAtRef.current < 3000) return
    const row = firstInViewportRowRef.current
    if (!row) return
    row.scrollIntoView({ block: 'start', behavior: 'smooth' })
  }, [firstInViewportIdx])

  if (collapsed) {
    return (
      <div
        className="px-3 py-2 text-xs text-muted text-center border border-border bg-surface rounded-md"
        role="status"
        aria-live="polite"
      >
        {t('cue_list.collapsed')}
      </div>
    )
  }

  if (cues.length === 0) {
    return (
      <div
        className="px-3 py-4 text-sm text-muted text-center border border-border bg-surface rounded-md"
        role="status"
      >
        {t('cue_list.no_cues')}
      </div>
    )
  }

  return (
    <div className="rounded-md border border-border overflow-hidden flex flex-col flex-1 min-h-0">
      <div className="px-3 py-2 flex items-center justify-between bg-surface border-b border-border flex-shrink-0">
        <div className="text-xs text-muted">
          <span className="text-primary font-medium">{t('cue_list.title')}</span>
          {' · '}
          <span>{t('cue_list.follows_wave', { count: cues.length })}</span>
        </div>
      </div>
      <div
        ref={listRef}
        role="listbox"
        aria-label={t('cue_list.aria_label')}
        className="overflow-y-auto bg-primary flex-1 min-h-0"
        onWheel={() => {
          userScrolledAtRef.current = Date.now()
        }}
        onPointerDown={() => {
          userScrolledAtRef.current = Date.now()
        }}
      >
        {cues.map((cue, idx) => {
          const isActive = idx === selectedCueIdx
          const isPlayingThisRow = idx === playingIdx
          const displayText = formatCueTextForDisplay(cue.text)
          const lines = displayText.split('\n')
          const isEditingThisRow = editingIdx === idx
          const hasGap = gapIndices.has(idx)
          const hasOverlap = overlapIndices.has(idx)
          // Sync-scroll highlight: cues that currently intersect the wave
          // viewport get a visible surface tint, so the editor can see what
          // is currently on screen without losing the active selection.
          const inViewport =
            visibleRange !== null &&
            cue.end >= visibleRange[0] &&
            cue.start <= visibleRange[1]
          const isFirstInViewport = idx === firstInViewportIdx

          // Priority order for visual state — only one wins:
          // 1. Active (selected): brightest cyan accent + ring for unambiguous focus
          // 2. Now-playing (playhead inside, not selected): amber warning tint
          // 3. In-viewport (visible on the wave, not selected/playing): cyan-tinted band
          // 4. Default: transparent
          //
          // Arbitrary color values (e.g. `bg-[rgba(...)]`) sidestep any Tailwind v4
          // token-resolution edge cases so the in-viewport band is *guaranteed*
          // visible against the dark cue list container.
          let rowClasses: string
          // Tailwind v4 keeps overriding the left-border colour through the
          // `border-border` shorthand even when arbitrary value/property
          // utilities are present. We keep the bg-tint via Tailwind (it
          // works fine) and force the left-stripe colour via inline-style,
          // which CSS specificity rules guarantee will win.
          let stripeColor: string | undefined
          if (isActive) {
            rowClasses = 'bg-accent-bg border-l-4 ring-2 ring-inset ring-[#1DB8D4]'
            stripeColor = '#1DB8D4' // bright cyan — active selection
          } else if (isPlayingThisRow) {
            rowClasses = 'bg-warning-bg border-l-4'
            stripeColor = '#f59e0b' // amber — now playing
          } else if (inViewport) {
            // Subtler than active's accent-bg (0.10), brighter than default —
            // forms a clear "wave-band" stripe down the list.
            rowClasses =
              'bg-[rgba(29,184,212,0.06)] border-l-4 hover:bg-[rgba(29,184,212,0.14)]'
            stripeColor = '#0a7089' // dim cyan — visible on the wave
          } else {
            rowClasses = 'border-l-4 hover:bg-surface'
            stripeColor = 'transparent'
          }

          // Pin the row ref. Two refs may target the same element (the
          // active row may also be the first-in-viewport row); we prefer
          // the active ref since auto-scroll on selection takes priority.
          const refForRow = isActive
            ? activeRowRef
            : isFirstInViewport
              ? firstInViewportRowRef
              : null

          return (
            <div
              key={idx}
              ref={refForRow}
              role="option"
              aria-selected={isActive}
              data-in-viewport={inViewport ? '1' : undefined}
              data-now-playing={isPlayingThisRow ? '1' : undefined}
              tabIndex={-1}
              onClick={() => onSelectCue(idx, 'list')}
              className={`grid gap-3 px-3 py-2 border-b border-border cursor-pointer text-sm leading-snug transition-colors ${rowClasses}`}
              style={{
                gridTemplateColumns: '40px 110px 1fr 60px',
                borderLeftColor: stripeColor,
              }}
            >
              <div className="text-xs text-muted tabular-nums pt-0.5">{idx + 1}</div>
              <div className="text-xs text-muted tabular-nums leading-tight">
                <div>{formatTimecode(cue.start)}</div>
                <div>→ {formatTimecode(cue.end)}</div>
              </div>
              <div
                className="text-primary"
                onDoubleClick={(ev) => {
                  if (!onTextChange) return
                  ev.stopPropagation()
                  beginEdit(idx, displayText)
                }}
                title={onTextChange ? t('cue_list.dblclick_edit') : undefined}
              >
                {isEditingThisRow ? (
                  <textarea
                    ref={textareaRef}
                    value={editingDraft}
                    onChange={(ev) => setEditingDraft(ev.target.value)}
                    onClick={(ev) => ev.stopPropagation()}
                    onKeyDown={(ev) => {
                      if (ev.key === 'Enter' && !ev.shiftKey) {
                        ev.preventDefault()
                        commitEdit()
                        return
                      }
                      if (ev.key === 'Escape') {
                        ev.preventDefault()
                        cancelEdit()
                      }
                    }}
                    onBlur={commitEdit}
                    rows={Math.max(2, editingDraft.split('\n').length)}
                    className="w-full bg-surface text-primary border border-border rounded p-1 text-sm leading-snug focus:outline-none focus:ring-2 focus:ring-[#1DB8D4] resize-none"
                    aria-label={t('cue_list.edit_cue_aria', { index: idx + 1 })}
                    data-testid={`cue-text-editor-${idx}`}
                  />
                ) : lines.length === 0 || (lines.length === 1 && lines[0] === '') ? (
                  <span className="italic text-muted">{t('cue_list.empty_cue')}</span>
                ) : (
                  lines.map((line, i) => <div key={`${idx}-${i}`}>{line}</div>)
                )}
              </div>
              <div className="flex items-start justify-end gap-1.5 pt-1">
                {hasGap && (
                  <span
                    data-testid={`quality-dot-gap-${idx}`}
                    title={t('cue_list.gap_tooltip')}
                    className="inline-block w-2 h-2 rounded-full bg-warning"
                  />
                )}
                {hasOverlap && (
                  <span
                    data-testid={`quality-dot-overlap-${idx}`}
                    title={t('cue_list.overlap_tooltip')}
                    className="inline-block w-2 h-2 rounded-full bg-error"
                  />
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
