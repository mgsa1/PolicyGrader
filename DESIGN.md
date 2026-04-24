# PolicyGrader — Design Spec

> Hand-off doc for Claude Code. Pair this with `tokens.css` (drop as-is into Gradio) and `design-reference.html` (a single static page showing every component rendered once, for visual truth).

---

## 1. Direction

**Google Research / DeepMind editorial.** Airy, restrained, typographic. Google Sans + Roboto Mono. Light only. Primary accent `#0b5fff`. Cohort colors are load-bearing — **amber = calibration (known ground truth)**, **blue = deployment (unknown)**. These thread through every chip, rail, and accent.

Hierarchy rule, top to bottom on every run-level page:
1. Hero — cost/time savings + headline ("hours to minutes")
2. Precision/recall against injected ground truth
3. Live cost · time · scenarios
4. Cluster counts

---

## 2. Tokens (source of truth)

All styling lives in CSS custom properties in `tokens.css`. Don't hand-pick colors — reference tokens. The ones you'll touch most:

| Token | Value | Use |
|---|---|---|
| `--pg-bg` | `#fafafa` | Page background |
| `--pg-surface` | `#ffffff` | Cards |
| `--pg-ink` / `--pg-ink-2/3/4` | `#1f1f1f` → `#80868b` | Text (primary → tertiary) |
| `--pg-line` / `--pg-line-2` | `#e8eaed` / `#dadce0` | Hairlines |
| `--pg-accent` | `#0b5fff` | Links, active states |
| `--pg-cal` / `--pg-cal-soft` | `#b06000` / `#fef1d8` | Calibration chips |
| `--pg-dep` / `--pg-dep-soft` | `#1967d2` / `#e3ecfd` | Deployment chips |
| `--pg-ok` / `--pg-err` | `#137333` / `#b3261e` | Pass / fail |
| `--pg-phase-{planner,rollout,judge,report}` | blue / purple / amber / green | Phase strips in trace + `/memories/` |
| `--pg-s-1..10` | 4 → 72px | Spacing scale |
| `--pg-radius` / `--pg-radius-pill` | 10px / 999px | |
| `--pg-font-sans` / `--pg-font-mono` | Google Sans / Roboto Mono | |

Full list + dark-mode overrides in `tokens.css`.

---

## 3. Component contract

The spec is **structural**, not prescriptive about markup. Gradio can assemble these with its own components — what matters is the visual contract.

### Topbar
- Left: PG monogram (28×28, `--pg-ink` bg, white "PG" in Google Sans 12px 600) + "PolicyGrader" / "Embodied eval orchestrator" subline.
- Right: session chip (mono, pill, green dot), elapsed time (mono), phase chip.
- 1px bottom border (`--pg-line`).

### Tabs
- Hairline underline style. Inactive = `--pg-ink-3`, active = `--pg-ink` with 2px `--pg-ink` underline. **No** filled tab backgrounds. Gap between tabs: `--pg-s-7` (32px).

### Hero (every run-level page)
Two-column, 1.4fr / 1fr.
- Left: eyebrow (mono uppercase 11px, pulsing amber dot) → 48px display headline with one accent-colored emphasis word → 15px sub (max 48ch) → cohort chip row.
- Right: `--pg-surface` card, 3×2 metric grid. Each cell: 11px mono label → 26px display number with small unit → 11px "vs" line with strikethrough baseline + green delta.

### KPI row (calibration + overview)
Four equal columns, 1px vertical dividers between, 1px top+bottom borders. Each: 10px mono label → 32px display number → 12px sub. No shadow.

### Cards (`.pg-card`)
`--pg-surface` + 1px `--pg-line` + `--pg-radius`. **No shadow.** Header: h3 (15px 500) left, mono meta right. Padding `--pg-s-6` (24px).

### Chips (`.pg-chip`)
Pill, 3×10 padding, 12px. Variants: default / cal / dep / ok / warn / err / phase (uppercase mono). Background = `-soft` token, border = `-line` token, text = full color token.

### Tables
Column headers = mono uppercase 11px `--pg-ink-4`. Rows separated by 1px `--pg-line`. Numbers always `font-variant-numeric: tabular-nums` + mono. Percentages visualize as inline horizontal bars: 4px rail, filled width = value, color = ok/accent/warn by threshold (≥.9 / ≥.7 / else).

### Confusion matrices
- **Binary 2×2:** TP/TN green-tinted (`rgba(19,115,51, 0.08→0.18)`), FP/FN red-tinted. Display number centered, small mono label below (TP/TN/FP/FN).
- **Multiclass heatmap:** diagonal = green alpha scaled by value, off-diagonal = red alpha scaled by value, zeros = `--pg-surface-2` with middle dot. 1:1 aspect. Row labels right-aligned mono, col labels vertical-rl mono.

### Agent trace (Live screen)
Each phase gets a divider: top-bordered, two-line block — `01` mono + phase name + status chip (color = phase color, transparent bg, colored border). Below: 12px color-strip-bordered event cards:
- **say** = sans serif, italic for thinking
- **tool** = mono, `▸` prefix
- **result** = mono, `◂` prefix, green check coloring

### Memories tree
Mono rows. 3px colored indicator strip on the left of each file = owner phase color. Directories are `--pg-ink-3` bold with `▸` prefix. Indent via `padding-left`. Highlight (currently-writing file) = `--pg-warn-soft` row.

### Cluster cards (Deployment)
Horizontal card: square thumbnail (140×140) + body. Body top row: `#N` mono + label code + big count ("4 / 9"). Then 4px accent rail with share fill. Then 13px summary (max 80ch). Then mono condition footnote.

### Tweaks (if you port them)
Floating bottom-right panel, 4 radio groups: theme (light/dark), density (comfortable/compact), accent hue (blue/slate/indigo/teal). Density toggle maps to `[data-density="compact"]` on `<html>` and is already defined in tokens.css.

---

## 4. Gradio integration checklist

1. **Drop `tokens.css` into a `<style>` block or `css_paths=["tokens.css"]` on `gr.Blocks`.** You now have the full design system as CSS variables.
2. Wrap your root in `<div class="pg">` — this activates the font stack + colors on all children.
3. Build each pane with Gradio primitives (`gr.Row`, `gr.Column`, `gr.HTML`, `gr.DataFrame`) but give them `elem_classes=["pg-card"]`, `"pg-kpi"`, `"pg-chip cal"`, etc.
4. For anything that doesn't map to a Gradio primitive (hero, confusion matrix, trace stream), use `gr.HTML` and author the markup directly against the utility classes.
5. **The banner + tabs are the only pieces that really need to be pixel-faithful.** Everything else can degrade to stock Gradio DataFrames with `pg-table` styling — still looks Google.

---

## 5. What to show Claude Code

When asking Claude Code to implement a screen, paste:
1. This file (`DESIGN.md`)
2. `tokens.css`
3. The **specific section** of this spec for the screen you want
4. Optionally: a screenshot of `design-reference.html` rendered at that screen

Do **not** paste the React source. It's 4 MB of rendering scaffolding that tells Claude Code nothing about the *system* — only one instance of it. The spec above is ~3 KB and fully generative.

---

## 6. Screens in the current mock

- **Overview** — landing: large headline, KPI strip, 4-card pipeline, 3-card view index.
- **Live** — hero + 3-column grid: trace / current rollout / `/memories/` tree.
- **Judge calibration** — hero + KPI row + (2×2 binary | multiclass heatmap) + per-label table + drill-down table.
- **Deployment findings** — hero + judge-trust quote card + 2×2 cluster cards + rollout table.
