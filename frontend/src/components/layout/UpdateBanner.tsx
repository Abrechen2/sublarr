import { useTranslation } from 'react-i18next'
import { useUpdateInfo } from '@/hooks/useApi'
import { useDismissedVersion } from '@/hooks/useDismissedVersion'
import { formatVersion } from '@/lib/version'

/**
 * Full-width announcement bar shown at the top of the app when a newer
 * stable release exists. Styled like the marketing site's announce bar.
 * Dismissible per-version (see useDismissedVersion).
 */
export function UpdateBanner() {
  const { t } = useTranslation()
  const { data: updateInfo } = useUpdateInfo()
  const { dismissedVersion, dismiss } = useDismissedVersion()

  if (!updateInfo?.available || !updateInfo.url || !updateInfo.latest) return null

  const latest = updateInfo.latest
  const url = updateInfo.url
  if (dismissedVersion === latest) return null

  return (
    <div
      data-testid="update-banner"
      className="relative z-30 flex items-center justify-center gap-2 border-b border-emerald-400/20 bg-emerald-400/10 px-4 py-2 text-center text-xs text-emerald-300"
    >
      <svg
        className="h-3.5 w-3.5 shrink-0"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d="M12 19V5M5 12l7-7 7 7" />
      </svg>
      <span>{t('update.banner.message', { version: formatVersion(latest) })}</span>
      <a
        data-testid="update-banner-link"
        href={url}
        target="_blank"
        rel="noreferrer"
        className="rounded-full border border-emerald-400/30 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider hover:bg-emerald-400/10"
      >
        {t('update.view_release')}
      </a>
      <button
        type="button"
        data-testid="update-banner-dismiss"
        onClick={() => dismiss(latest)}
        aria-label={t('update.banner.dismiss')}
        className="absolute right-3 top-1/2 -translate-y-1/2 leading-none text-emerald-300/70 hover:text-emerald-200"
      >
        ✕
      </button>
    </div>
  )
}
