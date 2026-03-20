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
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1
            className="font-semibold text-[var(--text-primary)]"
            style={{ fontSize: 'clamp(1.25rem, 2.5vw, 1.5rem)' }}
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
          <div data-testid="page-header-actions" className="flex items-center gap-2 shrink-0">
            {actions}
          </div>
        )}
      </div>
    </div>
  );
}
