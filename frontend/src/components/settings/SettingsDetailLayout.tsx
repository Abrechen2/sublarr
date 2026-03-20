import React from 'react'
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
  const resolvedBreadcrumb: readonly BreadcrumbItem[] = breadcrumb ?? [
    { label: 'Settings', href: '/settings' },
    { label: title },
  ]

  return (
    <div
      data-testid="settings-detail-layout"
      className={cn('mx-auto w-full', className)}
      style={{ maxWidth: '780px' }}
    >
      <PageHeader
        title={title}
        subtitle={subtitle}
        breadcrumb={resolvedBreadcrumb}
        actions={actions}
      />

      <div data-testid="settings-detail-content" className="space-y-4">
        {children}
      </div>
    </div>
  )
}
