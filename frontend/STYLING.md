# Sublarr Frontend Styling Policy

**Adopted:** 2026-04-18
**Status:** Strategic direction — all new code follows this; legacy migrates organically.

## TL;DR

Pure Tailwind utility classes for all static styling. Inline `style={{ ... }}`
is reserved for **runtime-computed values only** (dynamic widths, transforms,
data-dependent colors).

## Token system

Design tokens live in [`src/index.css`](./src/index.css). The `@theme inline`
block maps Tailwind utility classes to the existing CSS variables, so
`className="bg-surface text-muted rounded-md p-3"` produces the exact same
style as the legacy `style={{ background: 'var(--bg-surface)', color:
'var(--text-muted)', borderRadius: 'var(--radius-md)', padding:
'var(--space-3)' }}` form.

Light/dark variants are handled by the existing `:root` / `.dark` CSS-var
overrides — **no `dark:` class suffixes are needed** on Tailwind utilities.

## Migration map

| Legacy inline-style | New Tailwind |
|---|---|
| `background: 'var(--bg-surface)'` | `className="bg-surface"` |
| `color: 'var(--text-muted)'` | `className="text-muted"` |
| `border: '1px solid var(--border)'` | `className="border border-border"` |
| `borderRadius: 'var(--radius-md)'` | `className="rounded-md"` |
| `padding: 'var(--space-3)'` | `className="p-3"` |
| `padding: '12px'` (hardcoded) | `className="p-3"` |
| `gap: '8px'` | `className="gap-2"` |
| `fontSize: '14px'` | `className="text-sm"` |
| `fontFamily: 'var(--font-mono)'` | `className="font-mono"` |

## Available color tokens

Defined in the `@theme inline` block at the top of `src/index.css`. Each
generates `bg-*`, `text-*`, `border-*`, `ring-*`, `outline-*` utilities.

**Backgrounds:** `page`, `surface`, `surface-hover`, `elevated`, `deep`

**Borders:** `border`, `border-hover`

**Text:** `foreground`, `secondary`, `muted`

**Brand:** `accent`, `accent-hover`, `accent-dim`, `accent-subtle`, `accent-bg`

**Status:** `success`, `success-bg`, `error`, `error-bg`, `warning`, `warning-bg`, `upgrade`, `upgrade-bg`

## Allowed inline-style patterns

Do **NOT** migrate these — they are legitimate runtime-computed values:

- Dynamic dimensions: `style={{ width: \`${pct}%\` }}`
- Dynamic transforms: `style={{ transform: \`rotate(${deg}deg)\` }}`
- Custom CSS properties: `style={{ '--custom-prop': value }}`
- Third-party component overrides where Tailwind can't reach (e.g. CodeMirror theme props)
- Runtime-computed colors: `style={{ color: someState }}`
- Position + z-index combinations that need precise pixel values

## Migration workflow

1. **Never a "Big Bang" sweep.** Legacy inline-styles migrate organically —
   every time you edit a TSX file for any reason, convert its inline-styles
   as part of the change.

2. **Use the tool:**
   ```bash
   python tools/migrate_inline_styles.py frontend/src/pages/YourFile.tsx
   ```
   The tool scans the file and emits a per-attribute report:
   - `[OK] FULLY CONVERTIBLE` → apply the suggested `className`, delete `style={{...}}`
   - `[PARTIAL] needs manual review` → extract the convertible keys into `className`, leave the rest in `style={{...}}`
   - `[DYN] DYNAMIC-ONLY` → leave as-is

3. **Visual smoke test before committing.** Run `npm run dev` and click
   through the pages you edited. Tailwind's atomic classes should produce
   pixel-identical output to the legacy inline styles (modulo known
   arbitrary-value approximations documented in the tool).

4. **ESLint warns on new inline styles.** See `eslint.config.js`
   (`no-restricted-syntax` rule). Warnings don't block CI but surface as a
   reminder during code review.

## Future direction

When the legacy inline-style count drops below ~100, the ESLint rule is
promoted from `warn` to `error` in a dedicated cleanup cycle. Until then,
existing inline-styles are tolerated; new ones are discouraged.

## References

- [`src/index.css`](./src/index.css) — design tokens + `@theme inline` block
- [`tools/migrate_inline_styles.py`](../tools/migrate_inline_styles.py) — conversion tool
- [`eslint.config.js`](./eslint.config.js) — ESLint rule (`no-restricted-syntax`)
- Tailwind v4 docs: [Theme configuration](https://tailwindcss.com/docs/theme), [@theme directive](https://tailwindcss.com/docs/functions-and-directives#theme-directive)
