import { useTranslation } from 'react-i18next'
import { Sparkles } from 'lucide-react'
import { Tooltip } from './Tooltip'
import type { AIQualityInfo } from '@/types/system'

const VERDICT_COLORS: Record<string, string> = {
  green: 'var(--success)',
  yellow: 'var(--warning)',
  red: 'var(--error)',
}

/**
 * AIQualityBadge — advisory LLM verdict for a downloaded subtitle.
 * Renders nothing when no verdict is stored (feature off / not yet analyzed).
 */
export function AIQualityBadge({ quality }: { quality?: AIQualityInfo | null }) {
  const { t } = useTranslation('activity')
  if (!quality || !VERDICT_COLORS[quality.verdict]) return null

  const label = t(`history.ai_quality.${quality.verdict}`)
  const reasons = (quality.reasons ?? []).filter(Boolean).join(' · ')
  const content = reasons ? `${label} — ${reasons}` : label

  return (
    <Tooltip content={content} maxWidth={320}>
      <span className="inline-flex items-center" aria-label={label}>
        <Sparkles size={12} style={{ color: VERDICT_COLORS[quality.verdict] }} />
      </span>
    </Tooltip>
  )
}
