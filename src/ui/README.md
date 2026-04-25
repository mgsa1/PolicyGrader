# `src/ui/` — Gradio front end

The dashboard is a thin file-watcher over a run's `mirror_root` directory.
Everything here is UI-only; the orchestrator, sim, vision, metrics, and memory
layers are untouched.

## File map

| File                       | What lives here |
| --                         | -- |
| `app.py`                   | Blocks scaffolding, Tabs, Timer wiring, run-picker + drill-filter handlers. Delegates rendering to `panes/`. |
| `theme.py`                 | Python color/font constants (for Plotly/PIL/inline SVG) **plus** a small CSS string that overrides Gradio's internal tab/accordion/dropdown DOM. All `.pg-*` utility classes live in `assets/tokens.css`, not here. |
| `styles.py`                | CSS class-name constants + tiny HTML primitive helpers (`num`, `chip`, `phase_chip`, `monogram`, `empty`, …). One source of truth for the class names used across `panes/`. |
| `synthesis.py`             | Pure-data: `ScoredRollout`, `Cluster`, cohort split, keyframe rendering, `copy_button`. Tests in `tests/test_synthesis.py`. Untouched by the redesign. |
| `metrics_view.py`          | Pure-data + HTML helpers for the Judge calibration tab (binary 2×2, Plotly heatmap, per-label table, drill-down, judge-trust banner). Tests in `tests/test_metrics_view.py`. Untouched by the redesign. |
| `assets/tokens.css`        | The design system — tokens + `.pg-*` utility classes. Loaded via `css_paths=[...]` on `.launch()`. |
| `panes/chrome.py`          | Shared chrome: topbar brand + meta, hero banner, phase-progress strip, scope strip, judge-trust banner. Also the phase-marker → short-code map used by Live's trace and memories tree. |
| `panes/overview.py`        | **Overview** tab — landing: headline, KPI strip, 4-phase pipeline cards, 3-card view index pointing at the other tabs. |
| `panes/live.py`            | **Live** tab — agent activity stream, current rollout player + path, metadata-rich rollout gallery, `/memories/` host mirror tree. |
| `panes/calibration.py`     | **Judge calibration** tab — thin facade over `metrics_view.py` (cohort + caption + 2×2 binary + heatmap + per-label + drill-down). |
| `panes/findings.py`        | **Deployment findings** tab — cluster cards (one per judge taxonomy label) decorated with per-label calibration precision, plus the bottom-of-tab rollout table. |
| `panes/_io.py`             | Shared readers for `runtime.json` and `chat.jsonl`. Used by `chrome.py` and `live.py`. |

## CSS plumbing

`assets/tokens.css` is the single source of truth for colors, spacing, typography, and every `.pg-*` utility class the panes use. It is referenced via `css_paths=[styles.tokens_css_path()]` on `.launch()` — never inlined into Python strings.

`theme.CSS` only targets Gradio's own DOM (`[role="tab"]`, `.accordion`, `.pg-run-picker` inputs, `.gradio-container`…) — the bits tokens.css can't reach because they live inside Gradio components. Keep new utility styles in `tokens.css`; only put *Gradio-internal overrides* in `theme.CSS`.

The repo-root `tokens.css` and `DESIGN.md` are the unmodified hand-off documents from design; `src/ui/assets/tokens.css` is the operational copy and is allowed to grow app-specific utility classes (all referencing tokens, no hard-coded hex).

## Where the data comes from

Every renderer takes a `Path` (the selected run's `mirror_root`) and reads from disk — no direct orchestrator coupling. The `Timer(1s)` ticks re-render fast-moving pieces (hero banner, phase strip, trace, gallery, memories, current video); the `Timer(5s)` ticks re-render heavier pieces (heatmap, cluster cards, metrics tables, rollout table).
