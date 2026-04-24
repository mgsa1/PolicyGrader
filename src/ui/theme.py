"""Python-side color/font constants + minimal Gradio-internal CSS overrides.

The full design system lives in `src/ui/assets/tokens.css` and is loaded into
the Gradio app via `css_paths` on `.launch()` — every `.pg-*` utility class is
defined there.

This module only holds:

  1. Python constants (`CAL`, `INK_1`, `FONT_MONO`, …) for consumers that need
     raw hex strings — Plotly heatmap traces, PIL red-dot overlays, inline SVG
     icons. These **duplicate** the `--pg-*` values in tokens.css by design;
     keep them numerically in sync with that file (tokens.css is canonical).

  2. A small `CSS` string for Gradio-internal components (tab-nav, accordion,
     dropdown) that tokens.css doesn't target. `tokens.css` owns every `.pg-*`
     utility class; this string owns the dozen Gradio shadow-root selectors
     we need to override for the light-research look.
"""

from __future__ import annotations

# ---- Surfaces --------------------------------------------------------------------
BG = "#fafafa"
SURFACE = "#ffffff"
SURFACE_2 = "#f4f5f7"
SURFACE_INSET = "#eef0f3"

# ---- Ink -------------------------------------------------------------------------
INK_1 = "#1f1f1f"
INK_2 = "#3c4043"
INK_3 = "#5f6368"
INK_4 = "#80868b"
INK_5 = "#bdc1c6"

# ---- Lines -----------------------------------------------------------------------
LINE = "#e8eaed"
LINE_2 = "#dadce0"

# ---- Accent ----------------------------------------------------------------------
ACCENT = "#0b5fff"
ACCENT_SOFT = "#e8efff"
ACCENT_DEEP = "#0842b8"

# ---- Cohorts ---------------------------------------------------------------------
CAL = "#b06000"
CAL_SOFT = "#fef1d8"
CAL_LINE = "#f2c974"
DEP = "#1967d2"
DEP_SOFT = "#e3ecfd"
DEP_LINE = "#8ab4f8"

# ---- Status ----------------------------------------------------------------------
OK = "#137333"
OK_SOFT = "#e6f4ea"
WARN = "#b06000"
WARN_SOFT = "#fef7e0"
ERR = "#b3261e"
ERR_SOFT = "#fce8e6"

# ---- Phases ----------------------------------------------------------------------
PLANNER = "#1967d2"
ROLLOUT = "#7b1fa2"
JUDGE = "#b06000"
REPORT = "#137333"
PHASE_NEUTRAL = INK_4

# ---- Fonts -----------------------------------------------------------------------
FONT_DISPLAY = (
    '"Google Sans", "Google Sans Display", -apple-system, BlinkMacSystemFont, '
    '"Segoe UI", Roboto, sans-serif'
)
FONT_BODY = '"Google Sans Text", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif'
FONT_MONO = '"Roboto Mono", "SF Mono", "Menlo", "Consolas", ui-monospace, monospace'


# ---- Gradio-internal override CSS -----------------------------------------------
# Everything below targets Gradio's own DOM (outer shell + Tab / Accordion /
# Dropdown / Form components). `tokens.css` covers the rest.

CSS = f"""
/* Force light color-scheme on Gradio's outer host + any .dark descendants. */
html, body, gradio-app, .main, #root, main, .gradio-container, body > div {{
  color-scheme: light !important;
  background: {BG} !important;
}}
html, body {{ margin: 0 !important; min-height: 100vh !important; }}
html.dark, body.dark, .gradio-container.dark, .gradio-container .dark {{
  color-scheme: light !important;
  background: {BG} !important;
}}

/* Map Gradio's theme vars to our token palette so its own widgets render light. */
.gradio-container {{
  --body-text-color: {INK_2};
  --body-text-color-subdued: {INK_3};
  --body-background-fill: {BG};
  --background-fill-primary: {SURFACE};
  --background-fill-secondary: {SURFACE_2};
  --block-background-fill: {SURFACE};
  --block-border-color: {LINE};
  --block-label-background-fill: {SURFACE};
  --block-label-text-color: {INK_1};
  --block-title-text-color: {INK_1};
  --block-info-text-color: {INK_3};
  --panel-background-fill: {SURFACE};
  --panel-border-color: {LINE};
  --border-color-primary: {LINE};
  --border-color-accent: {ACCENT};
  --color-accent: {ACCENT};
  --color-accent-soft: {ACCENT_SOFT};
  --input-background-fill: {SURFACE};
  --input-border-color: {LINE_2};
  --input-text-color: {INK_1};
  --link-text-color: {ACCENT};
  --neutral-50: #fafafa;
  --neutral-100: {SURFACE_2};
  --neutral-200: {SURFACE_INSET};
  --neutral-300: {LINE_2};
  --neutral-400: {INK_5};
  --neutral-500: {INK_4};
  --neutral-600: {INK_3};
  --neutral-700: {INK_2};
  --neutral-800: {INK_1};
  --neutral-900: #0f0f0f;
  max-width: 1400px !important;
  font-family: {FONT_BODY};
  color: {INK_2} !important;
}}
.gradio-container * {{ font-family: inherit; }}
.gradio-container :where(h1, h2, h3, h4, h5, h6) {{
  font-family: {FONT_DISPLAY} !important;
  color: {INK_1} !important;
  font-weight: 500;
}}
.gradio-container .prose :where(h1, h2, h3, h4, h5, h6),
.gradio-container .markdown :where(h1, h2, h3, h4, h5, h6) {{ color: {INK_1} !important; }}
.gradio-container .prose p,
.gradio-container .markdown p,
.gradio-container .prose li,
.gradio-container .markdown li {{ color: {INK_2} !important; }}
.gradio-container .prose strong,
.gradio-container .markdown strong,
.gradio-container .prose b,
.gradio-container .markdown b {{ color: {INK_1} !important; }}
.gradio-container code, .gradio-container pre {{
  font-family: {FONT_MONO};
  color: {INK_1};
  background: {SURFACE_INSET};
}}
.gradio-container .block, .gradio-container .form, .gradio-container .gap {{
  background: transparent !important;
  border-color: {LINE} !important;
}}

/* Tabs — hairline underline, DeepMind-editorial feel. */
.gradio-container .tab-nav,
.gradio-container [role="tablist"] {{
  border-bottom: 1px solid {LINE} !important;
  background: transparent !important;
  padding: 0 4px !important;
}}
.gradio-container .tab-nav button,
.gradio-container button[role="tab"] {{
  color: {INK_3} !important;
  -webkit-text-fill-color: {INK_3} !important;
  opacity: 1 !important;
  font-family: {FONT_DISPLAY} !important;
  font-size: 14px !important;
  font-weight: 500 !important;
  padding: 12px 18px !important;
  border: none !important;
  border-bottom: 2px solid transparent !important;
  background: transparent !important;
}}
.gradio-container .tab-nav button *,
.gradio-container button[role="tab"] * {{
  color: inherit !important;
  -webkit-text-fill-color: inherit !important;
  opacity: 1 !important;
}}
.gradio-container .tab-nav button.selected,
.gradio-container button[role="tab"][aria-selected="true"],
.gradio-container button[role="tab"].selected {{
  color: {INK_1} !important;
  -webkit-text-fill-color: {INK_1} !important;
  border-bottom-color: {INK_1} !important;
  font-weight: 500 !important;
}}
.gradio-container .tab-nav button:hover,
.gradio-container button[role="tab"]:hover {{
  color: {INK_1} !important;
  -webkit-text-fill-color: {INK_1} !important;
}}

/* Accordion — white card with ink label. */
.gradio-container .accordion,
.gradio-container details,
.gradio-container details[open] {{
  background: {SURFACE} !important;
  border: 1px solid {LINE} !important;
  border-radius: 10px !important;
}}
.gradio-container .accordion > .label-wrap,
.gradio-container .accordion > button,
.gradio-container details > summary,
.gradio-container .label-wrap {{
  background: {SURFACE} !important;
  color: {INK_1} !important;
  border: none !important;
  border-radius: 10px 10px 0 0 !important;
  padding: 12px 16px !important;
  font-family: {FONT_DISPLAY} !important;
  font-size: 14px !important;
  font-weight: 500 !important;
}}
.gradio-container .accordion > .label-wrap *,
.gradio-container .accordion > button *,
.gradio-container details > summary *,
.gradio-container .label-wrap * {{ color: {INK_1} !important; }}
.gradio-container .accordion > div:not(.label-wrap),
.gradio-container details > div {{
  background: {SURFACE} !important;
  padding: 0 16px 16px 16px !important;
}}

/* Topbar row flex rules — arrange the Gradio Row that hosts the topbar. */
.pg-topbar-row {{ align-items: center; margin-bottom: 0; }}
.pg-topbar-meta-row {{
  align-items: center;
  justify-content: flex-end;
  gap: 14px !important;
  flex-wrap: nowrap;
}}

/* Run-picker pill — restyle Gradio Dropdown as a mono session pill. */
.pg-run-picker {{
  flex: 0 0 auto !important;
  min-width: 0 !important;
  width: auto !important;
}}
.pg-run-picker .wrap,
.pg-run-picker .wrap-inner {{
  background: {SURFACE} !important;
  border: 1px solid {LINE_2} !important;
  border-radius: 999px !important;
  padding: 3px 12px 3px 22px !important;
  min-height: unset !important;
  height: 28px !important;
  position: relative;
}}
.pg-run-picker .wrap::before {{
  content: "●";
  position: absolute;
  left: 10px; top: 50%;
  transform: translateY(-50%);
  color: {OK};
  font-size: 8px;
}}
.pg-run-picker input,
.pg-run-picker .secondary-wrap input {{
  font-family: {FONT_MONO} !important;
  font-size: 12px !important;
  color: {INK_1} !important;
  background: none !important;
  border: none !important;
  padding: 0 !important;
  height: 22px !important;
  min-width: 110px !important;
}}
.pg-run-picker .icon-wrap,
.pg-run-picker .secondary-wrap .icon-wrap {{ color: {INK_4} !important; }}
"""
