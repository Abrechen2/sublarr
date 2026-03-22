# Sublarr Brand & Design Guideline

> **Version:** 2.0 — Frontend Redesign (Streamlined Hub + Cinematic Settings)
> **Approved:** 2026-03-20
> **Applies to:** All Sublarr frontend UI (React 19 + Tailwind v4)

---

## 1. Brand Identity

### Logo
- **Mark:** Stylized "S" in teal gradient (`#0f9bb5` → `#1DB8D4`)
- **Container:** Rounded square (10px radius), white text on gradient
- **Minimum size:** 36×36px
- **Clear space:** 8px on all sides
- **Usage:** Top of icon sidebar, login page, setup wizard, favicon

### Brand Colors (IMMUTABLE)
These colors define Sublarr's identity and must not be changed:

| Token | Light Mode | Dark Mode | Usage |
|-------|-----------|-----------|-------|
| `--accent` | `#0f9bb5` | `#1DB8D4` | Primary actions, active states, links |
| `--accent-hover` | `#0d8aa1` | `#19a5bf` | Hover state for accent elements |
| `--accent-dim` | `#0a7089` | `#116d7e` | Subtle accent references |

### Product Name
- **Full:** Sublarr
- **Tagline:** Self-hosted subtitle manager
- **In UI:** Always "Sublarr" (capital S, lowercase rest), never "SubLarr" or "SUBLARR"

---

## 2. Color System

### Surface Colors

| Token | Light | Dark | Purpose |
|-------|-------|------|---------|
| `--bg-deep` | — | `#131519` | Deepest background (body) |
| `--bg-primary` | `#eff1f4` | `#1a1d23` | Page background |
| `--bg-surface` | `#ffffff` | `#1f2228` | Cards, panels |
| `--bg-surface-hover` | `#f5f7fa` | `#252830` | Hovered cards/rows |
| `--bg-elevated` | `#f9fafb` | `#282c35` | Dropdowns, tooltips, modals |

### Border Colors

| Token | Light | Dark |
|-------|-------|------|
| `--border` | `#dde0e8` | `#2a2e38` |
| `--border-hover` | `#c6cad5` | `#3a3f4d` |

### Text Colors

| Token | Light | Dark | Usage |
|-------|-------|------|-------|
| `--text-primary` | `#18191f` | `#e0e4ec` | Headings, body text |
| `--text-secondary` | `#525968` | `#848b9e` | Labels, descriptions |
| `--text-muted` | `#8c95a6` | `#4a5168` | Hints, timestamps, disabled |

### Status Colors

| Token | Light | Dark | Usage |
|-------|-------|------|-------|
| `--success` / `--success-bg` | `#22a55b` / 10% | `#2ed573` / 10% | Connected, completed, high score |
| `--error` / `--error-bg` | `#e5334b` / 10% | `#f43f5e` / 10% | Failed, missing, errors |
| `--warning` / `--warning-bg` | `#d48a08` / 10% | `#f59e0b` / 10% | Needs attention, low score |
| `--upgrade` / `--upgrade-bg` | `#7c3aed` / 10% | `#a78bfa` / 10% | Upgradeable, translation feature |

### Accent Utilities

| Token | Value | Usage |
|-------|-------|-------|
| `--accent-subtle` | `rgba(accent, 0.08)` | Subtle tinted backgrounds |
| `--accent-bg` | `rgba(accent, 0.10–0.12)` | Active chip/tab backgrounds |
| `--accent-glow` | `rgba(accent, 0.25)` | Glow effects on active elements |

---

## 3. Typography

### Font Stack
```css
--font-sans: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
--font-mono: 'JetBrains Mono', 'SF Mono', 'Fira Code', 'Cascadia Code', monospace;
```

**Inter** is the primary typeface. Load weights 300, 400, 500, 600, 700 via Google Fonts or self-hosted.

### Type Scale

| Role | Size | Weight | Letter-spacing | Usage |
|------|------|--------|---------------|-------|
| Page Title | 20px | 700 | -0.5px | Page headers |
| Section Title | 14–15px | 600 | -0.2px | Card titles, section headers |
| Body | 13px | 400–500 | 0 | Default text, form labels |
| Small | 12px | 500 | 0 | Table cells, badges, buttons |
| Caption | 11px | 500–600 | 0 | Hints, descriptions, metadata |
| Micro | 10px | 600 | 0.3–0.5px | Status labels, counters (uppercase) |
| Stat Value | 20–26px | 700 | -1px | Hero stat numbers |

### Text Rules
- Body line-height: `1.5`
- Max line width: `65–75ch` for readable text blocks
- Use `font-weight` for hierarchy, not `font-size` jumps
- Truncate with ellipsis (`...`) only on card titles; prefer wrapping elsewhere
- Tabular numbers for data columns (`font-variant-numeric: tabular-nums`)

---

## 4. Spacing & Layout

### Spacing Scale (8px grid)

| Token | Value | Usage |
|-------|-------|-------|
| `--space-1` | `4px` | Icon-text gap, tight padding |
| `--space-2` | `8px` | Between related elements |
| `--space-3` | `12px` | Card internal padding, grid gaps |
| `--space-4` | `16px` | Section spacing |
| `--space-6` | `24px` | Between content sections |
| `--space-8` | `32px` | Page-level padding |
| `--space-12` | `48px` | Large section separation |

### Border Radius

| Token | Value | Usage |
|-------|-------|-------|
| `--radius-sm` | `6px` | Buttons, badges, inputs |
| `--radius-md` | `10px` | Episode rows, small cards |
| `--radius-lg` | `12px` | Main cards, panels, sections |
| `--radius-xl` | `16px` | Modal overlays, posters |
| `--radius-full` | `9999px` | Pills, chips, toggles, dots |

### Shadows

| Token | Value | Usage |
|-------|-------|-------|
| `--shadow-sm` | `0 1px 2px rgba(0,0,0,0.05)` | Subtle element lift |
| `--shadow-md` | `0 2px 8px rgba(0,0,0,0.08)` | Dropdown menus |
| `--shadow-lg` | `0 4px 16px rgba(0,0,0,0.12)` | Modals, expanded sidebar |
| `--shadow-glass` | `0 4px 24px rgba(0,0,0,0.06)` | Floating elements |

### Layout Structure

```
┌──────────────────────────────────────────────┐
│ Icon Sidebar (60px fixed, 220px on hover)    │
│ ┌──────────────────────────────────────────┐ │
│ │ Main Content (margin-left: 60px)         │ │
│ │ max-width: 1380px                        │ │
│ │ padding: 24px 32px 60px                  │ │
│ └──────────────────────────────────────────┘ │
│ Status Bar (fixed bottom, h: 26px)           │
└──────────────────────────────────────────────┘
```

### Breakpoints

| Name | Width | Behavior |
|------|-------|----------|
| Mobile | `≤ 768px` | Sidebar hidden, bottom nav, stacked grids |
| Tablet | `769–1024px` | Sidebar collapsed (icon only), 2-col grids |
| Desktop | `1025–1440px` | Full layout |
| Wide | `> 1440px` | Content max-width constrained |

---

## 5. Component Patterns

### Icon Sidebar
- **Width:** 60px collapsed, 220px on hover
- **Background:** `--bg-primary`
- **Border:** 1px right `--border`
- **Items:** 24px icon + 13px label (label fades in on hover)
- **Active state:** `--accent` text + 3px left accent bar
- **Badge:** Pill right-aligned, `--warning` bg, `#000` text
- **Sections:** Separated by 1px `--border` line
- **Bottom items:** Settings + Theme toggle, pushed to `margin-top: auto`

### Cards
- **Background:** `--bg-surface`
- **Border:** 1px `--border`, hover → `--border-hover`
- **Radius:** `--radius-lg` (12px)
- **Padding:** 18–22px
- **No shadows** in default state (border-only design)
- **Hover:** border-color change, optional translateY(-2px) for clickable cards

### Settings Cards (Category Grid)
- Same as cards but with:
  - 40px icon box (10px radius, `--accent-bg` background)
  - 15px title, 11px description
  - Top-right counter or feature tag
  - Hover: translateY(-2px) + accent border + subtle shadow
- **Disabled state:** `opacity: 0.4`, `pointer-events: none`

### Buttons

| Variant | Background | Border | Text | Usage |
|---------|-----------|--------|------|-------|
| Default | transparent | `--border` | `--text-secondary` | Secondary actions |
| Primary | `--accent` | `--accent` | `#000` | Primary CTA |
| Danger | transparent | `--error` | `--error` | Destructive actions |
| Small (.sm) | Same | Same | 10px, 3px 8px padding | Inline actions |

### Pill Tabs (Segmented Control)
- Container: `--bg-surface`, 3px padding, `--radius-md`
- Tab: 6px 14px padding, 12px font, `--text-secondary`
- Active: `--bg-elevated` bg, `--text-primary`, subtle shadow
- Badge: 10px accent-colored count after label

### Filter Chips
- Horizontal scrollable row
- Pill shape: `--radius-full`
- Default: `--border` border, `--text-secondary`
- Active: `--accent-bg` bg, `--accent` border + text

### Status Pills

| Type | Background | Text | Usage |
|------|-----------|------|-------|
| Missing | `--warning-bg` | `--warning` | Missing subtitles |
| Searching | `--accent-bg` | `--accent` | Active search |
| Failed | `--error-bg` | `--error` | No match / error |
| Done | `--success-bg` | `--success` | Completed |
| Low Score | `--upgrade-bg` | `--upgrade` | Below threshold |

### Score Badges
- 12px font, 700 weight, 3px 10px padding, 6px radius
- High (≥70): `--success-bg` / `--success`
- Medium (50–69): `--accent-bg` / `--accent`
- Low (<50): `--warning-bg` / `--warning`
- Missing: `--error-bg` / `--error`

### Form Fields
- **Input:** `--bg-elevated` bg, 1px `--border`, 6px radius, 13px font
- **Focus:** border → `--accent`
- **Select:** Same + custom chevron SVG, `appearance: none`
- **Toggle:** 40×22px, `--border` off / `--accent` on, white circle
- **Labels:** 13px, 500 weight, with 11px `--text-muted` hint below

### Toast Notifications
- Fixed bottom-right
- `--bg-elevated` bg, 1px status-color border
- Auto-dismiss 3s for success, manual dismiss for errors
- "Undo" link in accent color for auto-saved settings

### Data Tables
- Header: 10px uppercase, 600 weight, `--text-muted`
- Rows: 12px, 10–12px padding, `--border` bottom
- Hover: `--bg-surface-hover`
- Checkbox column: 24px width

---

## 6. Animation & Motion

### Timing Tokens

| Token | Value | Usage |
|-------|-------|-------|
| `--duration-fast` | `150ms` | Hover states, color changes |
| `--duration-normal` | `250ms` | Transitions, accordions |
| `--duration-slow` | `400ms` | Page transitions, modals |

### Easing

| Token | Value | Usage |
|-------|-------|-------|
| `--ease-out` | `cubic-bezier(0.16, 1, 0.3, 1)` | Enter animations |
| `--ease-spring` | `cubic-bezier(0.34, 1.56, 0.64, 1)` | Bouncy interactions |

### Rules
- All transitions use `transform` and `opacity` only (GPU-accelerated)
- Exit animations: 60–70% of enter duration
- Respect `prefers-reduced-motion`: reduce to opacity-only crossfade
- Sidebar expansion: 300ms with `--ease-out`
- Card hover lift: `translateY(-2px)`, 200ms
- Accordion open/close: 250ms height + opacity
- Page transition: fade 200ms
- Pulse animation on automation dot: 2s infinite
- Toast slide-up: 300ms with opacity

---

## 7. Iconography

### Icon Library
- **Primary:** Lucide React (`lucide-react`)
- **Size:** 24px for sidebar, 18px for section icons, 16px inline, 14px in buttons
- **Stroke width:** 2px (consistent across all icons)
- **Color:** Inherits from text color via `currentColor`

### Icon Mapping (Key UI Elements)

| Element | Icon | Lucide Name |
|---------|------|-------------|
| Dashboard | LayoutDashboard | `layout-dashboard` |
| Library | BookOpen | `book-open` |
| Activity | Bell | `bell` |
| Settings | Settings | `settings` |
| Theme (dark) | Moon | `moon` |
| Theme (light) | Sun | `sun` |
| Search | Search | `search` |
| Refresh | RotateCw | `rotate-cw` |
| Close | X | `x` |
| Checkmark | Check | `check` |
| Warning | AlertTriangle | `alert-triangle` |
| Info | Info | `info` |
| Edit | Pencil | `pencil` |
| Delete | Trash2 | `trash-2` |
| Download | Download | `download` |
| Upload | Upload | `upload` |
| Play | Play | `play` |
| Pause | Pause | `pause` |
| Skip | SkipForward | `skip-forward` |
| Filter | Filter | `filter` |
| Sort | ArrowUpDown | `arrow-up-down` |
| Expand | ChevronDown | `chevron-down` |
| Back | ChevronLeft | `chevron-left` |
| External link | ExternalLink | `external-link` |
| Connection | Link | `link` |
| Provider | Package | `package` |
| Automation | Zap | `zap` |
| Translation | Globe | `globe` |
| Notification | BellRing | `bell-ring` |
| System | Wrench | `wrench` |
| Subtitles | FileText | `file-text` |
| Score | Star | `star` |
| Keyboard | Keyboard | `keyboard` |

### Rules
- Never use emoji as functional icons
- Always pair icon-only buttons with `aria-label`
- Use `title` tooltips on icon-only sidebar items (collapsed state)
- Maintain consistent stroke width within the same visual layer

---

## 8. Navigation Architecture

### Primary Navigation (Icon Sidebar)

```
Logo (S)
v0.33.0-beta
────────────
Dashboard       (LayoutDashboard)
Library         (BookOpen)
Activity        (Bell) [badge: needs-attention count]
────────────
Settings        (Settings)        ← pushed to bottom
Theme Toggle    (Moon/Sun)        ← pushed to bottom
```

### Page Routing

| Page | Route | Old Routes Merged |
|------|-------|-------------------|
| Dashboard | `/` | Dashboard, Statistics (partial) |
| Library | `/library` | Library |
| Library Detail | `/library/series/:id` | SeriesDetail |
| Activity | `/activity` | Wanted, Queue, History, Blacklist |
| Settings | `/settings` | Settings (all 18 tabs) |
| Settings Detail | `/settings/:category` | Individual settings categories |
| Login | `/login` | Login |
| Setup | `/setup` | Setup |
| Onboarding | `/onboarding` | Onboarding |

### Removed Pages (Features Relocated)
- `/wanted` → Activity tab "Wanted"
- `/queue` → Activity tab "In Progress"
- `/history` → Activity tab "Completed"
- `/blacklist` → Activity tab "Blacklist"
- `/statistics` → Dashboard widgets + Settings/System
- `/tasks` → Settings/Automation (scheduling section)
- `/logs` → Settings/System (log viewer section)
- `/plugins` → Settings/Providers (marketplace section)

---

## 9. Settings Architecture

### Category Grid (Overview Page: `/settings`)

| # | Category | Route | Icon | Content |
|---|----------|-------|------|---------|
| 1 | General | `/settings/general` | Settings | Language, paths, port, logging, **Translation feature toggle** |
| 2 | Connections | `/settings/connections` | Link | Sonarr, Radarr, Media Servers, API Keys |
| 3 | Subtitles | `/settings/subtitles` | FileText | Scoring, format prefs, fansub prefs, cleanup, embedded extraction |
| 4 | Providers | `/settings/providers` | Package | Provider list + marketplace, anti-captcha, cache |
| 5 | Automation | `/settings/automation` | Zap | Auto-ranking, upgrades, scheduling, wanted scan, processing pipeline, tasks |
| 6 | Translation | `/settings/translation` | Globe | Backends, prompts, glossary, memory, Whisper (conditionally visible) |
| 7 | Notifications | `/settings/notifications` | BellRing | Templates, quiet hours, webhook channels |
| 8 | System | `/settings/system` | Wrench | Security, backup/restore, migration, events/hooks, logs, protocol |

### Translation Visibility
- **Toggle location:** Settings → General (bottom section, "Feature Add-on" card)
- **When disabled:** Translation card on settings grid shows `opacity: 0.4` + "Requires Enable" tag, not clickable
- **When enabled:** Translation card fully interactive, translation-related settings visible throughout app
- **Auto-detection:** If no translation backend is configured, suggest enabling on first visit

### Settings Detail Pattern
- **Breadcrumb:** Settings / [Category Name]
- **Page title + subtitle** describing the category
- **Sections** as cards with icon + title + description header
- **Form fields:** Label group (left) + Control group (right), separated by subtle border
- **Progressive disclosure:** "Advanced" expandable sections for power-user options
- **Auto-save:** Every change saves immediately with debounce, "Setting saved [Undo]" toast

---

## 10. Accessibility

### Requirements
- WCAG 2.1 AA compliance minimum
- Color contrast: 4.5:1 for normal text, 3:1 for large text
- All interactive elements: `min-height: 44px` touch targets
- Focus rings: 2px `--accent` outline on keyboard focus (not on click)
- `prefers-reduced-motion`: disable all transform animations, keep opacity transitions
- Skip-to-main-content link (sr-only, visible on focus)
- `aria-label` on all icon-only buttons
- `aria-current="page"` on active nav item
- Form inputs: visible labels (never placeholder-only)
- Error messages: `role="alert"` or `aria-live="polite"`
- Tables: proper `<thead>`, `<th scope="col">`, sortable headers with `aria-sort`

### Keyboard Navigation
- `Tab`: Navigate through interactive elements in logical order
- `Enter`/`Space`: Activate buttons, toggles, links
- `Escape`: Close modals, dropdowns, expanded sidebar
- `Ctrl+K`: Open global search (command palette)
- `?`: Open keyboard shortcuts reference
- Arrow keys: Navigate within tab groups, dropdown menus

---

## 11. Dark/Light Mode

### Implementation
- CSS custom properties (design tokens) swap via `.dark` class on `<html>`
- Toggle in sidebar bottom (Moon/Sun icon)
- Persisted to `localStorage` key `sublarr-theme`
- Respects `prefers-color-scheme` on first visit

### Design Rules
- Both themes must be tested for every new component
- Dark mode is the **primary** design target (most users use dark)
- Light mode uses desaturated tints, never pure white cards on pure white background
- Status colors use same hue but adjusted saturation per theme
- Borders visible in both modes (test explicitly)
- Glass effects (if any) only in dark mode; solid cards in light mode

---

## 12. Responsive Behavior

### Mobile (≤768px)
- Sidebar → hidden, replaced by bottom tab bar (4 items: Dashboard, Library, Activity, Settings)
- Hero stats → 2×2 grid
- Content grids → single column
- Automation banner stats → hidden (keep dot + title)
- Settings grid → single column
- Episode rows → simplified (hide format, provider columns)
- Status bar → full width (no sidebar offset)

### Tablet (769–1024px)
- Sidebar → icon-only (60px, no hover expand)
- Grids → 2 columns
- Settings grid → 2 columns

### Desktop (1025px+)
- Full layout as designed
- Sidebar hover-expand enabled
- All grid columns active

---

## 13. File Naming & Code Conventions

### Component Files
- PascalCase: `IconSidebar.tsx`, `SettingsGrid.tsx`
- One component per file
- Co-locate styles with component (Tailwind classes)
- Test files: `ComponentName.test.tsx`

### CSS
- Tailwind v4 utility classes as primary styling
- CSS custom properties for design tokens (in `index.css`)
- No CSS modules, no styled-components
- Complex animations: `@keyframes` in `index.css`

### Icons
- Import individually: `import { Settings } from 'lucide-react'`
- Never `import * from 'lucide-react'`
- Pass `size`, `strokeWidth`, `className` as props

### i18n
- All user-visible strings must use `t()` from `react-i18next`
- Namespaces: `common`, `dashboard`, `settings`, `library`, `activity`, `editor`, `onboarding`
- Key format: `namespace:section.label` (e.g., `settings:general.mediaPath`)
