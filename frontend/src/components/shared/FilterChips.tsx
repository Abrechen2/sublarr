interface FilterChip {
  id: string;
  label: string;
}

interface FilterChipsProps {
  chips: FilterChip[];
  activeChip: string;
  onChange: (chipId: string) => void;
}

export function FilterChips({ chips, activeChip, onChange }: FilterChipsProps) {
  return (
    <div className="flex gap-1.5 overflow-x-auto pb-1 scrollbar-none">
      {chips.map(chip => (
        <button
          key={chip.id}
          onClick={() => onChange(chip.id)}
          className={`px-3 py-1 rounded-full text-xs font-medium border whitespace-nowrap transition-all duration-150 ${
            activeChip === chip.id
              ? 'bg-[var(--accent-bg)] border-[var(--accent)] text-[var(--accent)]'
              : 'border-[var(--border)] text-[var(--text-secondary)] hover:border-[var(--border-hover)] hover:text-[var(--text-primary)]'
          }`}
        >
          {chip.label}
        </button>
      ))}
    </div>
  );
}
