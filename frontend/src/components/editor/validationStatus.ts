import type { SubtitleValidation } from '@/types/system'

export type ValidationTone = 'ok' | 'warn' | 'error'

export interface ValidationStatus {
  tone: ValidationTone
  label: string
}

type Translate = (key: string, opts?: Record<string, unknown>) => string

/** Backend warning texts that have a translated label. */
const KNOWN_WARNINGS: Record<string, string> = {
  'No subtitle events found': 'validation_no_events',
}

/**
 * Badge state for an editor validation result.
 *
 * A file the backend accepts with warnings (plain text, an empty SRT) must not
 * read as unreservedly valid: the first warning is shown instead (#27).
 */
export function validationStatus(result: SubtitleValidation, t: Translate): ValidationStatus {
  if (!result.valid) {
    return { tone: 'error', label: t('validation_invalid', { error: result.error ?? '?' }) }
  }
  const warning = result.warnings?.[0]
  if (warning) {
    const key = KNOWN_WARNINGS[warning]
    return { tone: 'warn', label: key ? t(key) : warning }
  }
  return {
    tone: 'ok',
    label: t('validation_ok', { events: result.event_count ?? 0, styles: result.style_count ?? 0 }),
  }
}

export const VALIDATION_TONE_CLASSES: Record<ValidationTone, { badge: string; text: string }> = {
  ok: { badge: 'bg-emerald-500/20 text-emerald-400', text: 'text-emerald-400' },
  warn: { badge: 'bg-amber-500/20 text-amber-400', text: 'text-amber-400' },
  error: { badge: 'bg-red-500/20 text-red-400', text: 'text-red-400' },
}
