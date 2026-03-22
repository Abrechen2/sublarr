interface ScoreBadgeProps {
  score: number | null;
  className?: string;
}

export function ScoreBadge({ score, className = '' }: ScoreBadgeProps) {
  if (score === null) {
    return (
      <span className={`text-xs font-bold px-2.5 py-0.5 rounded-[var(--radius-sm)] bg-[var(--error-bg)] text-[var(--error)] ${className}`}>
        Missing
      </span>
    );
  }

  const variant = score >= 70
    ? 'bg-[var(--success-bg)] text-[var(--success)]'
    : score >= 50
      ? 'bg-[var(--accent-bg)] text-[var(--accent)]'
      : 'bg-[var(--warning-bg)] text-[var(--warning)]';

  return (
    <span className={`text-xs font-bold px-2.5 py-0.5 rounded-[var(--radius-sm)] ${variant} ${className}`}>
      {score}
    </span>
  );
}
