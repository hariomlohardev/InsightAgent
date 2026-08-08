# 03 — Components

All components consume tokens; no hardcoded values. Two radii, one accent, outline icons.

## Controls (8px radius)

**Button:**
- Primary: `bg: var(--accent)`, `text: var(--accent-text)`, `500 medium`, `8px`, `height 36px`, `px 16`. Hover: `var(--accent-hover)`. No gradient, no shadow, no `scale`.
- Secondary: `bg: white`, `border: 0.5px var(--border-hairline)`, `text-primary`. Hover: `var(--surface-muted)`.
- Ghost: no border, `text-secondary` → hover `surface-muted`.
- Danger: semantic `danger`, not accent reuse. `bg: var(--danger-bg)`, `text: var(--danger)`, `border: 0.5px`.

Sentence case labels (`Create dashboard`, not `Create Dashboard`). Max two weights.

**Input / select / textarea:**
- `height 36px`, `8px`, `0.5px` hairline, `bg: white`, `text: 14px`.
- Focus: `border: var(--accent)`, `ring: 0 0 0 2px var(--accent-ring)` — only shadow in system.
- No floating labels; placeholder `text-muted` `13px`.

**Badge / pill:**
- `999px`, `12px` height, `500`, `8px` padding, `0.5px` border.
- Neutral: `surface-muted` + `text-secondary`. Accent only for active state. Semantic `success/warning/danger` only for status (`fresh`, `stale`, `error`).

## Cards

**Standard card (12px, hairline):**
- `bg: white`, `border: 0.5px var(--border-hairline)`, `12px`, `padding 20px`, no shadow.
- Header: `500` `14px` + `text-secondary` `13px` caption below, not bold.
- Never nest card inside card with another border.

**Metric / KPI card (no border):**
- `bg: var(--surface-tint)`, `no border`, `12px`, `padding 16px 20px`.
- Structure: muted label `12px 500 text-secondary` above, large number `30px 500 text-primary` below, delta `12px` semantic if needed.
- Group in `grid 2–4` with `16px` gap, not floating with shadows.

**Empty state:**
- Centered `icon outline 24px text-muted` + `14px text-secondary` sentence, + single primary action. No illustration mascot unless purposeful.

## Data-dense: bordered rows, not grids

Applies to: datasets list, connector lists, audit log, RBAC users, schedules, reports, dashboards table.

- Container: single `12px` card with hairline outer border, inner rows `1px` `var(--border-strong)` dividers.
- Row: `height 44px`, `padding 10px 12px`, `14px` text. Hover: `var(--surface-muted)`. Selected: `2px` accent left inset (not full border).
- Header row: `12px 500 text-secondary`, `uppercase` forbidden — use sentence case `Dataset`, `rows`, `created`.
- No card grid for these views. Even on desktop, keep rows — scanability requires alignment, not floating.

**Table specifics:**
- Monospace for numbers/`dataset_id` (`JetBrains Mono 12px`) if needed, otherwise system sans.
- Pagination: muted `13px` + `prev/next` ghost buttons, not numbered pill explosion.

## Icons

- Single outline set: Heroicons outline (or Tabler outline) `stroke 1.5`, `16–20px`. Never filled, never emoji, never mixed sets.
- Icon not in colored rounded square. Icon sits directly in `16px` box or inline with text, `icon-default`.
- No emoji as feature icons.

## Feedback

- Toast: `12px` card, hairline, `8px`, `14px`, semantic left `2px` accent for success/danger, auto-dismiss 4s. No glow.

## Anti-slop in components

- No `rounded-2xl` everywhere — `8px` vs `12px` deliberate.
- No `bg-clip-text` gradient headlines.
- No left-border accent cards (except selected row 2px).
- No repeated eyebrow-headline-3cards sections.
