import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { X } from 'lucide-react'
import { useSetupStatus, useCompleteSetup } from '@/hooks/useSystemApi'
import type { SetupBenchmark, SetupProfile, CompleteSetupResult } from '@/api/health'

export const WIZARD_POSTPONED_KEY = 'sublarr_wizard_postponed'
const PROFILES: readonly SetupProfile[] = ['light', 'balanced', 'aggressive'] as const

type Step = 'welcome' | 'profile' | 'done'

interface FirstRunWizardProps {
  readonly onClose: () => void
}

// ─── Shell ──────────────────────────────────────────────────────────────────

interface ModalShellProps {
  readonly onClose: () => void
  readonly labelledBy: string
  readonly children: React.ReactNode
}

function ModalShell({ onClose, labelledBy, children }: ModalShellProps) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onClose])

  return (
    <div
      data-testid="first-run-wizard"
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ backgroundColor: 'rgba(0,0,0,0.6)' }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy}
        className="relative flex flex-col gap-5 rounded-xl"
        style={{
          backgroundColor: 'var(--bg-surface)',
          border: '1px solid var(--border)',
          padding: 28,
          maxWidth: 640,
          width: '92vw',
          maxHeight: '90vh',
          overflow: 'auto',
        }}
      >
        {children}
      </div>
    </div>
  )
}

// ─── Welcome step ───────────────────────────────────────────────────────────

interface WelcomeStepProps {
  readonly onNext: () => void
  readonly onPostpone: () => void
}

function WelcomeStep({ onNext, onPostpone }: WelcomeStepProps) {
  const { t } = useTranslation('setup')
  return (
    <>
      <button
        type="button"
        onClick={onPostpone}
        className="absolute top-4 right-4 p-1 rounded"
        style={{ color: 'var(--text-muted)' }}
        aria-label={t('common.postpone')}
        data-testid="wizard-close"
      >
        <X size={16} />
      </button>
      <h2
        id="first-run-wizard-title"
        className="font-bold text-xl"
        style={{ color: 'var(--text-primary)' }}
      >
        {t('welcome.title')}
      </h2>
      <p className="text-sm leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
        {t('welcome.intro')}
      </p>
      <div className="flex justify-between items-center gap-3 mt-2">
        <button
          type="button"
          onClick={onPostpone}
          className="px-4 py-2 rounded-md text-sm font-medium"
          style={{
            backgroundColor: 'transparent',
            color: 'var(--text-muted)',
            border: 'none',
          }}
          data-testid="wizard-postpone"
        >
          {t('common.postpone')}
        </button>
        <button
          type="button"
          onClick={onNext}
          autoFocus
          className="px-5 py-2 rounded-md text-sm font-semibold"
          style={{ backgroundColor: 'var(--accent)', color: '#fff' }}
          data-testid="wizard-next"
        >
          {t('welcome.next')}
        </button>
      </div>
    </>
  )
}

// ─── Profile pick step ──────────────────────────────────────────────────────

interface ProfileStepProps {
  readonly benchmark: SetupBenchmark | undefined
  readonly onPick: (profile: SetupProfile) => void
  readonly onBack: () => void
  readonly onPostpone: () => void
  readonly loading: boolean
}

function ProfileCard({
  profile,
  recommended,
  selected,
  onSelect,
}: {
  readonly profile: SetupProfile
  readonly recommended: boolean
  readonly selected: boolean
  readonly onSelect: () => void
}) {
  const { t } = useTranslation('setup')
  return (
    <button
      type="button"
      onClick={onSelect}
      data-testid={`wizard-profile-${profile}`}
      data-recommended={recommended ? 'true' : 'false'}
      data-selected={selected ? 'true' : 'false'}
      className="text-left rounded-lg p-4 flex flex-col gap-2"
      style={{
        backgroundColor: selected ? 'var(--bg-elevated)' : 'var(--bg-secondary)',
        // Border reflects ONLY the current selection so exactly one card reads as
        // active. The recommendation is conveyed by the badge, not the border —
        // otherwise the recommended card stays accent-bordered even after the user
        // picks a different one, making two cards look selected at once. (Fixes #148.)
        border: `2px solid ${selected ? 'var(--accent)' : 'var(--border)'}`,
        cursor: 'pointer',
      }}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>
          {t(`profile.${profile}.title`)}
        </span>
        {recommended && (
          <span
            data-testid={`wizard-recommended-${profile}`}
            className="text-xs font-semibold rounded-full px-2 py-0.5"
            style={{ backgroundColor: 'var(--accent)', color: '#fff' }}
          >
            {t('profile.recommended_badge')}
          </span>
        )}
      </div>
      <p className="text-xs leading-snug" style={{ color: 'var(--text-secondary)' }}>
        {t(`profile.${profile}.desc`)}
      </p>
    </button>
  )
}

function ProfileStep({ benchmark, onPick, onBack, onPostpone, loading }: ProfileStepProps) {
  const { t } = useTranslation('setup')
  const recommended = benchmark?.recommended_profile ?? 'balanced'
  const [selected, setSelected] = useState<SetupProfile>(recommended)

  useEffect(() => {
    setSelected(recommended)
  }, [recommended])

  return (
    <>
      <h2
        id="first-run-wizard-title"
        className="font-bold text-xl"
        style={{ color: 'var(--text-primary)' }}
      >
        {t('profile.title')}
      </h2>
      <div className="grid gap-3" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))' }}>
        {PROFILES.map((p) => (
          <ProfileCard
            key={p}
            profile={p}
            recommended={p === recommended}
            selected={p === selected}
            onSelect={() => setSelected(p)}
          />
        ))}
      </div>
      {benchmark && (
        <div
          data-testid="wizard-detected"
          className="text-xs"
          style={{ color: 'var(--text-muted)' }}
        >
          {t('profile.detected', { cpu: benchmark.cpu_count, ram: benchmark.ram_gb })}
        </div>
      )}
      <a
        href="/settings/automation"
        target="_blank"
        rel="noopener noreferrer"
        className="text-xs underline"
        style={{ color: 'var(--accent)' }}
        data-testid="wizard-custom-link"
      >
        {t('profile.custom_link')}
      </a>
      <div className="flex justify-between items-center gap-3 mt-2">
        <button
          type="button"
          onClick={onPostpone}
          className="px-4 py-2 rounded-md text-sm font-medium"
          style={{ backgroundColor: 'transparent', color: 'var(--text-muted)', border: 'none' }}
          data-testid="wizard-postpone"
        >
          {t('common.postpone')}
        </button>
        <div className="flex gap-3">
          <button
            type="button"
            onClick={onBack}
            className="px-4 py-2 rounded-md text-sm font-medium"
            style={{
              backgroundColor: 'var(--bg-elevated)',
              border: '1px solid var(--border)',
              color: 'var(--text-secondary)',
            }}
            data-testid="wizard-back"
          >
            {t('common.back')}
          </button>
          <button
            type="button"
            onClick={() => onPick(selected)}
            disabled={loading}
            className="px-5 py-2 rounded-md text-sm font-semibold"
            style={{
              backgroundColor: 'var(--accent)',
              color: '#fff',
              opacity: loading ? 0.5 : 1,
            }}
            data-testid="wizard-pick"
          >
            {t('profile.pick')}
          </button>
        </div>
      </div>
    </>
  )
}

// ─── Done step ──────────────────────────────────────────────────────────────

interface DoneStepProps {
  readonly profile: SetupProfile
  readonly applied: CompleteSetupResult['applied'] | null
  readonly onClose: () => void
}

function DoneStep({ profile, applied, onClose }: DoneStepProps) {
  const { t } = useTranslation('setup')
  const appliedCount = applied ? Object.keys(applied).length : 0

  return (
    <>
      <h2
        id="first-run-wizard-title"
        className="font-bold text-xl"
        style={{ color: 'var(--text-primary)' }}
      >
        {t('done.title')}
      </h2>
      <p
        className="text-sm leading-relaxed"
        style={{ color: 'var(--text-secondary)' }}
        data-testid="wizard-done-summary"
      >
        {t('done.summary', { profile: t(`profile.${profile}.title`) })}
        {appliedCount > 0 && ` (${appliedCount})`}
      </p>
      <div className="flex justify-end items-center gap-3 mt-2">
        <button
          type="button"
          onClick={onClose}
          autoFocus
          className="px-5 py-2 rounded-md text-sm font-semibold"
          style={{ backgroundColor: 'var(--accent)', color: '#fff' }}
          data-testid="wizard-done-close"
        >
          {t('done.to_dashboard')}
        </button>
      </div>
    </>
  )
}

// ─── Container ──────────────────────────────────────────────────────────────

export default function FirstRunWizard({ onClose }: FirstRunWizardProps) {
  const { data: status } = useSetupStatus()
  const { mutate: complete, isPending } = useCompleteSetup()
  const [step, setStep] = useState<Step>('welcome')
  const [chosenProfile, setChosenProfile] = useState<SetupProfile>('balanced')
  const [applied, setApplied] = useState<CompleteSetupResult['applied'] | null>(null)

  const handlePostpone = () => {
    try {
      localStorage.setItem(WIZARD_POSTPONED_KEY, String(Date.now()))
    } catch {
      // localStorage may be unavailable (private mode) — fail quietly
    }
    onClose()
  }

  const handlePick = (profile: SetupProfile) => {
    setChosenProfile(profile)
    complete(profile, {
      onSuccess: (result) => {
        setApplied(result.applied)
        setStep('done')
      },
    })
  }

  return (
    <ModalShell onClose={handlePostpone} labelledBy="first-run-wizard-title">
      {step === 'welcome' && (
        <WelcomeStep onNext={() => setStep('profile')} onPostpone={handlePostpone} />
      )}
      {step === 'profile' && (
        <ProfileStep
          benchmark={status?.benchmark}
          onPick={handlePick}
          onBack={() => setStep('welcome')}
          onPostpone={handlePostpone}
          loading={isPending}
        />
      )}
      {step === 'done' && (
        <DoneStep profile={chosenProfile} applied={applied} onClose={onClose} />
      )}
    </ModalShell>
  )
}

// ─── Trigger predicate ──────────────────────────────────────────────────────

const SEVEN_DAYS_MS = 7 * 24 * 60 * 60 * 1000

export function shouldShowWizard(
  status: { wizard_completed: boolean } | undefined,
  now: number = Date.now(),
): boolean {
  if (!status) return false
  if (status.wizard_completed) return false
  try {
    const postponed = localStorage.getItem(WIZARD_POSTPONED_KEY)
    if (postponed) {
      const age = now - Number(postponed)
      if (Number.isFinite(age) && age >= 0 && age < SEVEN_DAYS_MS) return false
    }
  } catch {
    // Ignore localStorage read failures
  }
  return true
}
