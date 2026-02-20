interface ToggleProps {
  checked: boolean
  onChange: (val: boolean) => void
  disabled?: boolean
}

export function Toggle({ checked, onChange, disabled = false }: ToggleProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => !disabled && onChange(!checked)}
      className="relative inline-flex shrink-0 items-center rounded-full transition-all duration-200 focus:outline-none"
      style={{
        width: 40,
        height: 22,
        backgroundColor: checked ? 'var(--accent)' : 'var(--border)',
        opacity: disabled ? 0.5 : 1,
        cursor: disabled ? 'not-allowed' : 'pointer',
      }}
    >
      <span
        className="inline-block rounded-full bg-white shadow transition-transform duration-200"
        style={{
          width: 16,
          height: 16,
          transform: checked ? 'translateX(20px)' : 'translateX(3px)',
        }}
      />
    </button>
  )
}
