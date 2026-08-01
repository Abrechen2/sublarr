import React from 'react'
import { useTranslation } from 'react-i18next'
import { PageHeader } from '@/components/layout/PageHeader'
import { cn } from '@/lib/utils'

interface BreadcrumbItem {
  readonly label: string
  readonly href?: string
}

interface SettingsDetailLayoutProps {
  readonly title: string
  readonly subtitle?: string
  readonly breadcrumb?: readonly BreadcrumbItem[]
  readonly actions?: React.ReactNode
  readonly children: React.ReactNode
  readonly className?: string
}

export function SettingsDetailLayout({
  title,
  subtitle,
  breadcrumb,
  actions,
  children,
  className,
}: SettingsDetailLayoutProps) {
  const { t } = useTranslation('common')
  const resolvedBreadcrumb: readonly BreadcrumbItem[] = breadcrumb ?? [
    { label: t('settings.breadcrumb'), href: '/settings' },
    { label: title },
  ]

  return (
    // max-w-form is the shared responsive tier (780 → 960 → 1100px), not a
    // per-page number. Widened from the fixed 780px on 2026-08-01 with the
    // owner's approval — see docs/PROTECTED.md. Only this outer container
    // changes; SettingsSection / FormGroup / SettingsCard are untouched.
    <div
      data-testid="settings-detail-layout"
      className={cn('mx-auto w-full max-w-form', className)}
    >
      <PageHeader
        title={title}
        subtitle={subtitle}
        breadcrumb={resolvedBreadcrumb}
        actions={actions}
      />

      <div data-testid="settings-detail-content" className="flex flex-col" style={{ gap: '14px' }}>
        {children}
      </div>
    </div>
  )
}
