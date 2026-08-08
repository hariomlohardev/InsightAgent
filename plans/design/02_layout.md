# 02 — Layout & Shell

Streamlit's sidebar + main column becomes a restrained app shell. Whitespace, not chrome, separates concerns.

## Shell

**Structure (from FastAPI Jinja2 `base.html`):**
- Top bar `56px` (`--space-14`) — left: wordmark + dataset count, center: primary nav, right: LLM badge + auth. Hairline bottom border `0.5px`, no shadow.
- Page max-width `1280px`, centered, gutters `24px` / `32px`. Never full-bleed dense tables beyond `1280px`.
- Main: generous vertical rhythm `48px` between sections, `24px` between card groups. No section dividers if spacing suffices.
- Footer: minimal, `12px` muted text, no heavy chrome.

**Background:** `--surface-page: #ffffff` everywhere. No cream `#faf8f4`, no gray page, no gradient.

## Navigation

Horizontal, not Streamlit sidebar. Sentence case.

- Items: `datasets`, `dashboards`, `connectors`, `schedules`, `cloud` (when enabled), `audit` (admin only). Order matches user flow: upload → explore → connect → automate.
- Active state: `500 medium`, accent `2px` underline inset, not pill background or left-border accent card.
- No icon in nav label; icons reserved for page actions, not navigation duplication.

Mobile: top bar collapses to `menu` outline icon drawer, not a second sidebar. Drawer uses same hairline border, no overlay blur.

## Page scaffolding

Each page inherits `base.html` and defines `title` (sentence case), `description` (one line, `text-secondary`, `14px`), and `content`.

- Header block: title `24px 500` + description `14px` + primary action button (single accent) aligned right on desktop, stacked on mobile. No eyebrow pill, no centered hero.
- Content follows `24px` below header. No hero gradient, no aurora blobs.

## Whitespace rules

- Between page header and first card: `32px`
- Between cards: `16px`
- Inside card: `20px` padding
- Dense rows: `1px` row border, `0` gap — density comes from borders, not card spacing.

If hierarchy is unclear, add space, not a divider or shadow.

## Auth shell

- When `AUTH_REQUIRED=false`: top bar shows `signed in as viewer` muted, no login modal.
- When `true`: same shell, but primary nav is disabled until auth store has token. Login form is a centered card `400px` max, `12px` radius, hairline border, not a full-page takeover.

## Demo banner

`?demo=1` renders a thin `32px` banner above top bar: `read-only demo — sample data` with `accent` dot, hairline bottom, no colored background.

## Responsive

- Breakpoints from tokens: `--bp-sm: 640px`, `--bp-lg: 1024px`.
- Tables never become card grids on mobile; they stay bordered rows with horizontal scroll and sticky first column. preserves scanability.

## Anti-patterns avoided

- No bento grid for everything, no identical 3-card feature grid.
- No glassmorphism `backdrop-blur` on shell.
- No `hover:scale-105` on panels.
