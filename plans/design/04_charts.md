# 04 — Charts (Plotly.js Theme)

Streamlit `st.plotly_chart` becomes direct `Plotly.newPlot` with a token-derived theme. No default rainbow.

## Token mapping

All Plotly values reference CSS variables at generation time (Alpine injects computed tokens into layout). Single file `plotlyTheme.js` reads `getComputedStyle(document.documentElement)`.

- **Primary series:** `var(--accent)` — one series, one color. If multiple series needed, use `accent` tints `hsl(160 60% 36% / 0.9, 0.65, 0.4)` plus neutrals `zinc-300/400`, not categorical rainbow.
- **Gridlines:** `var(--border-hairline)` `0.5px` with `rgba` — subtle, not `#e5e7eb` heavy.
- **Axes/ labels:** `var(--text-secondary)` `12px 400`, ticks `11px`.
- **Background:** `rgba(0,0,0,0)` (transparent) on `var(--surface-card)`; never colored plot bg.
- **Font:** same system stack, `400` / `500` only.

## Layout defaults

```js
layout: {
  font: { family: 'var(--font-sans)', size: 12, color: 'var(--text-secondary)' },
  paper_bgcolor: 'rgba(0,0,0,0)',
  plot_bgcolor: 'rgba(0,0,0,0)',
  margin: { l: 40, r: 16, t: 24, b: 36 },
  xaxis: { gridcolor: 'var(--border-hairline)', linecolor: 'var(--border-strong)', tickcolor: 'transparent' },
  yaxis: { gridcolor: 'var(--border-hairline)', linecolor: 'var(--border-strong)' },
  hoverlabel: { bgcolor: 'white', bordercolor: 'var(--border-hairline)', font: { color: 'var(--text-primary)' } },
  colorway: ['var(--accent)', 'var(--accent-65)', 'var(--accent-40)', '#a1a1aa', '#d4d4d8']
}
```

No `template: plotly_dark`, no `viridis`.

## Chart types in InsightAgent

- **Bar/line** (chat groupby, forecast): primary `accent` bar/line `2px`, grid `0.5px`, `hover: x unified`.
- **Treemap / stacked bar** (segments): use `surface-tint` + accent tints, not 8-color set.
- **Scatter** (outliers): `is_outlier` red is semantic `danger` only here — outliers use `danger` point, not decoration; rest uses `icon-default`.
- **Heatmap / correlation:** sequential from `surface-tint` → `accent`, not `blues` rainbow.

## Interaction

All charts rendered via Alpine `x-init="Plotly.newPlot(...)"` with `responsive: true`. Resize on `window.resize` debounced `150ms`. No `hover:scale`.

## Fallback

If `Plotly` fails, table remains (same data). Never show broken rainbow fallback.

## Verification

- Screenshot: chart on white card should show only accent + grays; grid faint. Changing `--accent` in devtools recolors primary series without touching JS.
