# MediaCrawler WebUI Design System

## Source Of Truth

The implementation uses a three-layer token architecture:

```text
Primitive -> Semantic -> Component
```

Primary files:

| File | Purpose |
|------|---------|
| `webui/tokens/design-tokens.json` | Editable token source |
| `webui/src/styles/design-tokens.css` | Generated CSS variables |
| `webui/tailwind.config.ts` | Tailwind semantic mapping |
| `webui/src/index.css` | Legacy aliases and application primitives |
| `design-system/tk-media-command/MASTER.md` | Visual direction and anti-patterns |

## Token Layers

### Primitive

Raw values only. Components must not consume primitive tokens directly.

Examples:

```css
var(--primitive-color-gray-50)
var(--primitive-space-4)
var(--primitive-radius-md)
```

### Semantic

Purpose-based aliases for theme switching and readable component code.

Examples:

```css
var(--color-background)
var(--color-surface)
var(--color-foreground)
var(--color-primary)
var(--color-success)
var(--color-danger)
```

### Component

Component-specific decisions. Page components should consume these first.

Examples:

```css
var(--button-bg)
var(--input-border)
var(--card-radius)
var(--table-row-hover-bg)
var(--sidebar-width)
var(--statusbar-height)
```

Overview banner tokens:

```css
var(--banner-bg)
var(--banner-border)
var(--banner-title)
var(--banner-muted)
var(--banner-brand)
var(--banner-tech)
var(--banner-radius)
var(--banner-min-height)
```

## Color Rules

- Page background uses `--color-background`.
- Cards and panels use `--color-surface`.
- Primary buttons use `--button-bg`.
- Brand CTA uses `--color-brand-strong`.
- Cyan is an accent only; it is not used for normal text on white.
- Status colors use semantic tokens:
  - Success: `--color-success`
  - Warning: `--color-warning`
  - Danger: `--color-danger`
  - Information: `--color-info`
- Dark mode overrides semantic colors; components must not define separate dark colors unless the component has a documented exception.

## Typography

| Role | Size | Weight | Token |
|------|------|--------|-------|
| Page title | 18px | 600 | `--primitive-font-size-lg` |
| Section title | 14px | 600 | `--primitive-font-size-sm` |
| Body | 14px | 400 | `--primitive-font-size-sm` |
| Data value | 20px | 600 | `--primitive-font-size-xl` |
| Label / caption | 12px | 500 | `--primitive-font-size-xs` |

Data values, IDs, timestamps and table numbers use tabular numerals.

## Spacing

Use the 4px base scale:

```css
var(--primitive-space-1)
var(--primitive-space-2)
var(--primitive-space-3)
var(--primitive-space-4)
var(--primitive-space-6)
```

Component spacing defaults:

- Compact control gap: 4px
- Form field gap: 8px
- Card padding: 12-16px
- Section gap: 16-24px

## Radius And Elevation

- Default control radius: 8px
- Large surface radius: 12px maximum
- Pills and badges: full radius
- Default shadow: `--primitive-shadow-sm`
- Dropdowns and dialogs: `--primitive-shadow-lg`
- Do not stack multiple glow shadows.

## Component States

| Component | Default | Hover | Active | Focus | Disabled |
|-----------|---------|-------|--------|-------|----------|
| Button | primary bg | primary hover | primary active | 2px ring | 50% opacity |
| Input | surface bg | border strong | unchanged | primary ring | muted bg |
| Card | surface + border | border strong | unchanged | inner ring when interactive | 50% opacity |
| Nav item | transparent | subtle bg | red tint | visible ring | 50% opacity |
| Table row | surface | muted bg | selected tint | visible outline | muted text |

## Navigation

- Primary navigation lives in the fixed left sidebar on desktop.
- Maximum five top-level destinations.
- Active navigation uses the brand red tint and a left indicator.
- Main content must remain reachable from every page.
- Deep links use query parameters and browser history.

## Charts And Data

- Charts must have text summaries or table alternatives.
- Tooltips must also be available through keyboard focus.
- Status and theme cannot rely on color alone.
- Numeric columns must be right-aligned and tabular.
- Long titles use truncation or line clamping with full-text access.

## Token Generation

Regenerate CSS after editing the token source:

```powershell
node "C:\Users\24281\.codex\skills\design-system\scripts\generate-tokens.cjs" --config webui/tokens/design-tokens.json --output webui/src/styles/design-tokens.css
```

Validate token usage:

```powershell
node "C:\Users\24281\.codex\skills\design-system\scripts\validate-tokens.cjs" --dir webui/src
```

Do not edit `design-tokens.css` directly.

## Current Migration Status

The core WebUI shell, layout, status bar, form controls and primary components now consume generated semantic and component tokens.

The token validator still reports legacy violations in these areas:

1. Terminal and terminal-line colors
2. License/environment fallback screens
3. AI report accent colors
4. Chart theme colors
5. Older spacing and radius values in `index.css`

New code must not add more raw colors or dimensions. Existing violations should be migrated in this order:

1. Terminal and console
2. AI report colors
3. Chart palettes
4. License and environment screens
5. Remaining spacing and radius cleanup

Until migration is complete, legacy values are allowed only in existing files. They must not be copied into new components.
