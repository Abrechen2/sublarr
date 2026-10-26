interface PillTab {
  id: string;
  label: string;
  count?: number;
}

interface PillTabsProps {
  tabs: PillTab[];
  activeTab: string;
  onChange: (tabId: string) => void;
}

export function PillTabs({ tabs, activeTab, onChange }: PillTabsProps) {
  return (
    // max-w-full + overflow-x-auto: the strip scrolls on its own instead of
    // widening the page on narrow screens.
    <div className="flex gap-0.5 bg-[var(--bg-surface)] border border-[var(--border)] rounded-[var(--radius-md)] p-[3px] w-fit max-w-full overflow-x-auto">
      {tabs.map(tab => (
        <button
          key={tab.id}
          onClick={() => onChange(tab.id)}
          className={`shrink-0 whitespace-nowrap px-3.5 py-1.5 text-xs font-medium rounded-[7px] transition-all duration-150 ${
            activeTab === tab.id
              ? 'bg-[var(--bg-elevated)] text-[var(--text-primary)] shadow-sm'
              : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
          }`}
        >
          {tab.label}
          {tab.count !== undefined && (
            <span className="ml-1 text-[10px] font-semibold text-[var(--accent)]">{tab.count}</span>
          )}
        </button>
      ))}
    </div>
  );
}
