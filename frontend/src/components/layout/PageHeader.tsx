import React from 'react';
import { Breadcrumb } from '@/components/shared/Breadcrumb';
import { cn } from '@/lib/utils';

interface BreadcrumbItem {
  readonly label: string;
  readonly href?: string;
}

interface PageHeaderProps {
  readonly title: string;
  readonly subtitle?: string;
  readonly breadcrumb?: readonly BreadcrumbItem[];
  readonly actions?: React.ReactNode;
  readonly className?: string;
}

export function PageHeader({ title, subtitle, breadcrumb, actions, className }: PageHeaderProps) {
  return (
    <div data-testid="page-header" className={cn('mb-6', className)}>
      {breadcrumb && breadcrumb.length > 0 && (
        <Breadcrumb items={breadcrumb as BreadcrumbItem[]} />
      )}
      {/* Wraps on narrow screens: the actions drop below the title. */}
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-3">
        <div className="min-w-0">
          <h1
            className="text-[var(--text-primary)]"
            style={{ fontSize: '20px', fontWeight: 700, letterSpacing: '-0.5px' }}
          >
            {title}
          </h1>
          {subtitle && (
            <p
              data-testid="page-header-subtitle"
              className="mt-1 text-[13px] text-[var(--text-secondary)]"
            >
              {subtitle}
            </p>
          )}
        </div>
        {actions && (
          <div data-testid="page-header-actions" className="flex flex-wrap items-center gap-2 shrink-0 max-w-full">
            {actions}
          </div>
        )}
      </div>
    </div>
  );
}
