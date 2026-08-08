# 01 — Design Tokens

Single source of truth: `app/static/css/tokens.css` (CSS custom properties). Tailwind `tailwind.config.js` extends from tokens via `var(--token)`, never hardcodes. Changing one file rethemes the whole app.

## Thinking model

Tokens are not a palette dump — they encode neo-minimalist constraints: neutrals dominate, one accent, hairline borders, two radii, generous space, two weights.

## Color

**Neutrals — 95% of UI:**
- `--surface-page`: `#ffffff`
- `--surface-card`: `#ffffff`
- `--surface-tint`: `#f8f9f6` / `hsl(80 10% 97%)` — metric cards only, not borders
- `--surface-muted`: `#f4f4f5` (zinc-100) — hover on rows, disabled bg
- `--border-hairline`: `rgba(0,0,0,0.08)` → `0.5px` on cards, `1px` on dense rows
- `--border-strong`: `rgba(0,0,0,0.12)` — table row dividers
- `--text-primary`: `#18181b` (zinc-900)
- `--text-secondary`: `#71717a` (zinc-500) — labels, captions
- `--text-muted`: `#a1a1aa` (zinc-400) — only for disabled/placeholder, never body copy (avoids gray-400 body AI tell)
- `--icon-default`: `#52525b`

**One accent — sparingly:**
- `--accent`: `hsl(160 60% 36%)` — teal/forest, not purple/indigo. Used only for: primary button bg, active nav underline, selected row left 2px, focus ring, primary Plotly series.
- `--accent-hover`: `hsl(160 62% 32%)`
- `--accent-text`: `#ffffff` (on accent bg)
- `--accent-ring`: `hsl(160 60% 36% / 0.18)` — focus ring `0 0 0 2px`

Do not reuse accent for decoration, illustration, or card backgrounds.

**Semantic — states only:**
- `--success`: `#15803d` / `--success-bg`: `#f0fdf4`
- `--warning`: `#a16207` / `--warning-bg`: `#fefce8`
- `--danger`: `#b91c1c` / `--danger-bg`: `#fef2f2`
- Never use semantic bg as general tint. Reserve for badges/toasts/validation.

Tailwind mapping example (conceptual, not implemented here): `colors.accent: var(--accent)`, `colors.border.hairline: var(--border-hairline)`.

## Spacing (whitespace as structure)

Base unit `4px`. Scale via tokens, not arbitrary `px`:
- `--space-1`: 4px, `--space-2`: 8px, `--space-3`: 12px, `--space-4`: 16px, `--space-6`: 24px, `--space-8`: 32px, `--space-12`: 48px, `--space-16`: 64px
- Section gap: `48px` (`--space-12`). Card padding: `20–24px`. Dense table cell `10px 12px`. Page horizontal gutters `24px` mobile / `32px` desktop.

Never add a divider if `24px` of space already separates groups.

## Radius

Only two:
- `--radius-control`: `8px` — buttons, inputs, badges, selects
- `--radius-card`: `12px` — cards, panels, modals
- Exception: `999px` for pill badges only. Never `rounded-2xl` (16px) everywhere.

## Borders & elevation

- Hairline `0.5px` (`--border-hairline`) for cards/panels. `1px` for table rows. No `border-2`.
- No shadows. One exception: focus ring `box-shadow: 0 0 0 2px var(--accent-ring)` on `:focus-visible` for inputs/buttons. Never card drop shadows or aurora glows.

## Typography

System stack to avoid Inter-everywhere AI tell: `ui-sans-system, -apple-system, BlinkMacSystemFont, "SF Pro", "Segoe UI", sans-serif`. Optional web font: single neo-grotesk (e.g., General Sans) at 400/500 only — not Inter/Geist/Space Grotesk as sole identity.

- Weights: `400 regular` body, `500 medium` labels/active nav/numbers. No `600+` bold.
- Case: sentence case everywhere (`Upload dataset`, not `Upload Dataset`). No ALL CAPS kickers.
- Scale: `xs 12px / sm 13px / base 14px / lg 18px / xl 24px / 2xl 30px` (cap at 30px, not 48px empty headlines).
- Line height: `1.5` body, `1.2` headings. Letter spacing: `-0.01em` on headings only.

## Motion

No `fade-up` on scroll. Only `opacity`/`background` `150ms ease` on hover/active. Respect `prefers-reduced-motion`.

## How to verify tokens

- Single file change (`--accent: hsl(...)`) should retheme primary button, active nav, Plotly primary series, and focus ring without touching components.
- No hardcoded `#[0-9a-f]{6}` or `px` outside `tokens.css` + `tailwind.config.js` (lint via `grep`).
