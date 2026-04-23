"""Design tokens + global CSS for the Gradio UI.

One source of truth for colors, spacing, and component styles. Every HTML
helper in the UI layer imports token constants from here and emits markup
that hangs off the `.pg-*` classes defined in CSS. This lets us change the
visual language in one place and keeps inline `style=""` strings out of
the helpers.

The palette tracks the PolicyGrader light-theme mock: Google Sans-ish type,
#fafafa page, hairline borders, pill chips, minimal shadows. Cohort and
phase accents below are semantic — they carry meaning, not decoration.
"""

from __future__ import annotations

# ---- Surfaces -------------------------------------------------------------------
BG = "#fafafa"  # page background
SURFACE = "#ffffff"  # cards, panels
SURFACE_2 = "#f4f5f7"  # sunken panels
SURFACE_INSET = "#eef0f3"  # progress-bar track, code-block bg

# ---- Ink (text) -----------------------------------------------------------------
INK_1 = "#1f1f1f"  # headings
INK_2 = "#3c4043"  # body
INK_3 = "#5f6368"  # secondary info
INK_4 = "#80868b"  # captions, muted
INK_5 = "#bdc1c6"  # hints

# ---- Lines ----------------------------------------------------------------------
LINE = "#e8eaed"  # hairline
LINE_2 = "#dadce0"  # stronger separator

# ---- Accent (blue) --------------------------------------------------------------
ACCENT = "#0b5fff"
ACCENT_SOFT = "#e8efff"
ACCENT_DEEP = "#0842b8"

# ---- Cohorts --------------------------------------------------------------------
# Calibration = amber (measured against ground truth).
# Deployment  = blue  (no ground truth; judge stands alone).
CAL = "#b06000"
CAL_SOFT = "#fef1d8"
CAL_LINE = "#f2c974"
DEP = "#1967d2"
DEP_SOFT = "#e3ecfd"
DEP_LINE = "#8ab4f8"

# ---- Status ---------------------------------------------------------------------
OK = "#137333"
OK_SOFT = "#e6f4ea"
WARN = "#b06000"
WARN_SOFT = "#fef7e0"
ERR = "#b3261e"
ERR_SOFT = "#fce8e6"

# ---- Phases (editorial) ---------------------------------------------------------
PLANNER = "#1967d2"  # blue — designs the test suite
ROLLOUT = "#7b1fa2"  # purple — runs the simulator
JUDGE = "#b06000"  # amber — watches the videos
REPORT = "#137333"  # green — synthesizes findings
PHASE_NEUTRAL = INK_4  # for starting / complete / unknown

# ---- Fonts ----------------------------------------------------------------------
# Order: Google Sans first so ChromeOS/Android render the mock as designed;
# system fallbacks take over on macOS/Windows (SF Pro / Segoe UI read as
# clean Material-adjacent, which is close enough for the hackathon).
FONT_DISPLAY = (
    '"Google Sans", "Google Sans Display", -apple-system, BlinkMacSystemFont, '
    '"Segoe UI", Roboto, sans-serif'
)
FONT_BODY = '"Google Sans Text", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif'
FONT_MONO = '"Roboto Mono", "SF Mono", "Menlo", "Consolas", ui-monospace, monospace'


# ---- Global CSS -----------------------------------------------------------------
# Every class below is used somewhere in src/ui/*. Keep this block the only
# place raw colors/paddings live for chrome — component helpers stay markup-
# only aside from data-driven inline colors (phase tint, population accent).
CSS = f"""
/* --- force light color-scheme everywhere --------------------------------- */
/* Gradio 6 ships a dark-mode stylesheet keyed off @media (prefers-color-scheme:
   dark) AND/OR a .dark class. Three lines of defense:
     1. color-scheme: light disables the browser's auto dark-mode form styling.
     2. html.dark / body.dark / .gradio-container.dark selectors revert to
        light if Gradio auto-applied the class.
     3. Every theme variable below is pinned to a light palette value so
        Gradio's own components (Accordion, Block, Panel, Markdown body) can't
        drift back to dark via var() fallbacks. */
html, body, .gradio-container {{
  color-scheme: light !important;
  background: {BG} !important;
}}
html.dark, body.dark, .gradio-container.dark,
.gradio-container .dark {{
  color-scheme: light !important;
}}

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
.gradio-container * {{
  font-family: inherit;
}}
.gradio-container :where(h1, h2, h3, h4, h5, h6) {{
  font-family: {FONT_DISPLAY} !important;
  color: {INK_1} !important;
  font-weight: 500;
}}
/* Gradio's Markdown component scopes its own prose styles — beat them. */
.gradio-container .prose :where(h1, h2, h3, h4, h5, h6),
.gradio-container .markdown :where(h1, h2, h3, h4, h5, h6) {{
  color: {INK_1} !important;
}}
/* Force body text to ink color on all text-bearing elements, including any
   Gradio-added `.dark` descendants. The !important here beats the theme's
   own !important in its dark stylesheet. */
.gradio-container .prose,
.gradio-container .prose *,
.gradio-container .markdown,
.gradio-container .markdown *,
.gradio-container p,
.gradio-container span,
.gradio-container label,
.gradio-container div {{
  color: {INK_2};
}}
.gradio-container .prose p,
.gradio-container .markdown p,
.gradio-container .prose li,
.gradio-container .markdown li {{
  color: {INK_2} !important;
}}
.gradio-container .prose strong,
.gradio-container .markdown strong,
.gradio-container .prose b,
.gradio-container .markdown b {{
  color: {INK_1} !important;
}}
.gradio-container code, .gradio-container pre {{
  font-family: {FONT_MONO};
  color: {INK_1};
  background: {SURFACE_INSET};
}}

/* Kill any lingering dark backgrounds on block wrappers. */
.gradio-container .block,
.gradio-container .gradio-container .block,
.gradio-container .form,
.gradio-container .gap {{
  background: transparent !important;
  border-color: {LINE} !important;
}}

/* --- topbar -------------------------------------------------------------- */
.pg-topbar {{
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 20px;
  background: {SURFACE};
  border-bottom: 1px solid {LINE};
  border-radius: 10px 10px 0 0;
  margin-bottom: 0;
}}
.pg-topbar__brand {{
  display: flex; align-items: center; gap: 12px;
}}
.pg-topbar__logo {{
  width: 28px; height: 28px;
  background: {INK_1};
  color: {SURFACE};
  border-radius: 6px;
  display: flex; align-items: center; justify-content: center;
  font-family: {FONT_DISPLAY};
  font-size: 14px; font-weight: 700;
  letter-spacing: -0.5px;
}}
.pg-topbar__wordmark {{
  font-family: {FONT_DISPLAY};
  font-size: 16px; font-weight: 500;
  color: {INK_1};
  line-height: 1.2;
}}
.pg-topbar__tagline {{
  font-size: 12px; color: {INK_3};
  line-height: 1.2; margin-top: 2px;
}}
.pg-topbar__meta {{
  display: inline-flex; align-items: center; gap: 14px;
}}
.pg-topbar__run-chip {{
  display: inline-flex; align-items: center; gap: 6px;
  padding: 4px 12px;
  background: {SURFACE};
  color: {INK_1};
  border: 1px solid {LINE_2};
  border-radius: 999px;
  font-size: 12px; font-weight: 500;
  font-family: {FONT_MONO};
}}
.pg-topbar__run-chip::before {{
  content: "●"; font-size: 8px; color: {OK};
}}
.pg-topbar__elapsed {{
  font-family: {FONT_MONO};
  font-size: 12px;
  color: {INK_3};
  font-variant-numeric: tabular-nums;
}}

/* --- cards --------------------------------------------------------------- */
.pg-card {{
  background: {SURFACE};
  border: 1px solid {LINE};
  border-radius: 10px;
  padding: 24px;
}}
.pg-card--accent-cal {{ border-left: 3px solid {CAL}; }}
.pg-card--accent-dep {{ border-left: 3px solid {DEP}; }}
.pg-card--accent-judge {{ border-left: 3px solid {JUDGE}; }}

/* --- hero ---------------------------------------------------------------- */
.pg-hero {{
  background: {SURFACE};
  border: 1px solid {LINE};
  border-radius: 0 0 10px 10px;
  padding: 24px 28px 20px 28px;
}}
.pg-hero__eyebrow {{
  font-size: 11px; color: {INK_4};
  text-transform: uppercase; letter-spacing: 1.2px;
  font-weight: 500;
  margin-bottom: 6px;
}}
.pg-hero__headline {{
  font-family: {FONT_DISPLAY};
  font-size: 28px; font-weight: 500;
  color: {INK_1};
  letter-spacing: -0.3px;
  margin: 0;
}}
.pg-hero__subhead {{
  font-size: 13px; color: {INK_3};
  margin-top: 4px;
}}

/* --- metric grid --------------------------------------------------------- */
.pg-metric-grid {{
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 16px 20px;
  margin-top: 20px;
}}
.pg-metric {{
  background: {SURFACE_2};
  border-radius: 10px;
  padding: 14px 16px;
}}
.pg-metric__label {{
  font-family: {FONT_MONO};
  font-size: 11px;
  color: {INK_4};
  text-transform: uppercase;
  letter-spacing: 0.06em;
  font-weight: 500;
}}
.pg-metric__value {{
  font-family: {FONT_DISPLAY};
  font-size: 26px;
  font-weight: 500;
  color: {INK_1};
  font-variant-numeric: tabular-nums;
  line-height: 1.1;
  margin-top: 4px;
}}
.pg-metric__base {{
  font-size: 12px;
  color: {INK_4};
  font-variant-numeric: tabular-nums;
  margin-top: 2px;
}}
.pg-metric__delta {{
  font-size: 12px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  margin-top: 4px;
}}
.pg-metric__delta--ok {{ color: {OK}; }}

/* --- savings banner ------------------------------------------------------ */
.pg-savings {{
  margin-top: 16px;
  padding: 12px 16px;
  background: {OK_SOFT};
  border: 1px solid {OK}33;
  border-radius: 8px;
  display: flex;
  justify-content: space-around;
  font-size: 13px;
  color: {INK_2};
}}
.pg-savings b {{
  color: {OK};
  font-size: 18px;
  font-variant-numeric: tabular-nums;
  font-family: {FONT_DISPLAY};
  font-weight: 500;
}}
.pg-savings__muted {{ color: {INK_4}; font-size: 12px; }}

.pg-hero__footnote {{
  margin-top: 10px;
  font-size: 11px;
  color: {INK_4};
  text-align: center;
}}

/* --- section headers ----------------------------------------------------- */
.pg-section-hd {{
  display: flex; align-items: baseline; justify-content: space-between;
  padding: 32px 0 10px 0;
  border-bottom: 1px solid {LINE};
  margin-bottom: 16px;
}}
.pg-section-hd__title {{
  font-family: {FONT_DISPLAY};
  font-size: 22px; font-weight: 500;
  color: {INK_1};
  margin: 0;
}}
.pg-section-hd__sub {{
  font-size: 12px; color: {INK_3};
}}

/* --- chips (pills) ------------------------------------------------------- */
.pg-chip {{
  display: inline-flex; align-items: center; gap: 4px;
  padding: 3px 10px;
  background: {SURFACE_2};
  color: {INK_2};
  border: 1px solid {LINE_2};
  border-radius: 999px;
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.3px;
}}
.pg-chip--cal  {{ background: {CAL_SOFT}; color: {CAL}; border-color: {CAL_LINE}; }}
.pg-chip--dep  {{ background: {DEP_SOFT}; color: {DEP}; border-color: {DEP_LINE}; }}
.pg-chip--ok   {{ background: {OK_SOFT};  color: {OK};  border-color: {OK}55; }}
.pg-chip--warn {{ background: {WARN_SOFT}; color: {WARN}; border-color: {WARN}55; }}
.pg-chip--err  {{ background: {ERR_SOFT}; color: {ERR}; border-color: {ERR}55; }}
.pg-chip__dot {{ font-size: 8px; line-height: 1; }}
.pg-chip__sub {{
  color: {INK_4}; font-size: 10px; margin-left: 6px; font-weight: 400;
  letter-spacing: 0;
}}
.pg-chip__small {{
  margin-left: 8px;
  padding: 1px 6px;
  background: {SURFACE_INSET};
  color: {INK_4};
  border-radius: 8px;
  font-size: 10px;
  text-transform: none;
  letter-spacing: 0;
  font-weight: 400;
}}

/* --- icon copy button ---------------------------------------------------- */
.pg-icon-btn {{
  width: 28px; height: 28px;
  display: inline-flex; align-items: center; justify-content: center;
  background: {SURFACE};
  color: {INK_3};
  border: 1px solid {LINE_2};
  border-radius: 50%;
  cursor: pointer;
  padding: 0;
  line-height: 0;
  transition: all 120ms cubic-bezier(0.2, 0, 0, 1);
}}
.pg-icon-btn:hover {{
  color: {INK_1};
  border-color: {INK_3};
  background: {SURFACE_2};
}}
.pg-icon-btn--anchored {{ position: absolute; }}
.pg-icon-btn--top-right    {{ top: 8px; right: 8px; }}
.pg-icon-btn--top-left     {{ top: 8px; left: 8px; }}
.pg-icon-btn--bottom-right {{ bottom: 8px; right: 8px; }}
.pg-icon-btn--bottom-left  {{ bottom: 8px; left: 8px; }}
.pg-icon-btn--inline {{
  display: inline-flex;
  vertical-align: middle;
  margin-left: 6px;
  width: 22px; height: 22px;
}}

/* --- mono path chip ------------------------------------------------------ */
.pg-kbd {{
  display: inline-flex; align-items: center;
  padding: 2px 8px;
  background: {SURFACE_INSET};
  color: {INK_2};
  border-radius: 4px;
  font-family: {FONT_MONO};
  font-size: 12px;
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}}

/* --- phase strip --------------------------------------------------------- */
.pg-phase-grid {{
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  padding: 14px 0 6px 0;
}}
.pg-phase-chip {{
  background: {SURFACE};
  border: 1px solid {LINE};
  border-left-width: 3px;
  border-left-style: solid;
  border-radius: 10px;
  padding: 12px 14px;
  transition: background 180ms cubic-bezier(0.2, 0, 0, 1);
}}
.pg-phase-chip__head {{
  display: flex; align-items: baseline; justify-content: space-between;
}}
.pg-phase-chip__title {{
  font-family: {FONT_DISPLAY};
  font-size: 13px; font-weight: 500;
  color: {INK_1};
}}
.pg-phase-chip__status {{
  font-size: 10px; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.08em;
}}
.pg-phase-chip__counter {{
  margin-top: 6px;
  font-family: {FONT_MONO};
  font-size: 12px;
  color: {INK_3};
  font-variant-numeric: tabular-nums;
}}
.pg-phase-chip__sub {{
  margin-top: 3px;
  font-family: {FONT_MONO};
  font-size: 11px;
  color: {INK_4};
}}

.pg-progress {{
  margin-top: 8px;
  height: 6px;
  background: {SURFACE_INSET};
  border-radius: 3px;
  overflow: hidden;
}}
.pg-progress__fill {{
  height: 100%;
  border-radius: 3px;
  transition: width 180ms cubic-bezier(0.2, 0, 0, 1);
}}

/* --- tabs ---------------------------------------------------------------- */
/* Gradio 6 renders inactive tab labels near-white via a combination of low
   opacity + a span inside the button with its own color. We target both the
   button AND its descendants, and use -webkit-text-fill-color so Safari/WebKit
   can't re-apply its own color either. [role="tab"] is an ARIA stable hook
   and survives class renames between Gradio versions. */
.gradio-container .tab-nav,
.gradio-container [role="tablist"] {{
  border-bottom: 1px solid {LINE} !important;
  background: transparent !important;
  padding: 0 4px !important;
}}
.gradio-container .tab-nav button,
.gradio-container button[role="tab"] {{
  color: {INK_2} !important;
  -webkit-text-fill-color: {INK_2} !important;
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
  color: {ACCENT} !important;
  -webkit-text-fill-color: {ACCENT} !important;
  border-bottom-color: {ACCENT} !important;
  font-weight: 600 !important;
}}
.gradio-container .tab-nav button:hover,
.gradio-container button[role="tab"]:hover {{
  color: {INK_1} !important;
  -webkit-text-fill-color: {INK_1} !important;
}}

/* --- accordion ----------------------------------------------------------- */
/* Cover every DOM shape Gradio 6 has shipped for Accordion: the <details>
   element, the .accordion wrapper div, the .label-wrap header button, the
   class-less header button, and any <summary>. Also force the inner content
   region light so text inside (rendered via gr.HTML) sits on white. */
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
.gradio-container .label-wrap * {{
  color: {INK_1} !important;
}}
/* The body region that holds child components when the accordion is open. */
.gradio-container .accordion > div:not(.label-wrap),
.gradio-container details > div {{
  background: {SURFACE} !important;
  padding: 0 16px 16px 16px !important;
}}

/* --- chat blocks --------------------------------------------------------- */
.pg-chat {{
  max-height: 600px; overflow-y: auto; padding: 4px;
}}
.pg-chat__block {{
  margin: 6px 0;
  padding: 10px 12px;
  background: {SURFACE};
  border: 1px solid {LINE};
  border-radius: 8px;
  font-size: 13px;
  line-height: 1.5;
  color: {INK_2};
}}
.pg-chat__block--tool {{
  font-family: {FONT_MONO};
  font-size: 12px;
  color: {INK_2};
  background: {SURFACE_2};
}}
.pg-chat__block--result {{
  font-family: {FONT_MONO};
  font-size: 11px;
  color: {INK_3};
  background: {SURFACE_2};
  padding: 6px 12px;
}}
.pg-chat__block--thinking {{
  background: {SURFACE_INSET};
  color: {INK_3};
  font-style: italic;
  font-size: 12px;
  padding: 8px 12px;
  border-style: dashed;
}}
.pg-chat__block--error {{
  background: {ERR_SOFT};
  color: {ERR};
  border-color: {ERR}55;
  font-family: {FONT_MONO};
  font-size: 12px;
}}
.pg-chat__empty {{
  padding: 40px; text-align: center;
  color: {INK_4}; font-style: italic;
}}

.pg-chat__phase-hd {{
  margin: 28px 0 12px 0;
}}
.pg-chat__phase-eyebrow {{
  display: flex; align-items: center; gap: 14px; margin-bottom: 6px;
}}
.pg-chat__phase-label {{
  font-family: {FONT_MONO};
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.18em;
  white-space: nowrap;
}}
.pg-chat__phase-rule {{
  flex: 1; height: 1px;
}}
.pg-chat__phase-title {{
  font-family: {FONT_DISPLAY};
  font-size: 16px; font-weight: 500;
  color: {INK_1};
  margin-bottom: 3px;
}}
.pg-chat__phase-sub {{
  color: {INK_3};
  font-size: 13px;
  line-height: 1.5;
}}
.pg-chat__phase-writes {{
  margin-top: 8px;
  font-size: 11px;
  color: {INK_4};
  font-family: {FONT_MONO};
}}
.pg-chat__phase-writes strong {{
  text-transform: uppercase; letter-spacing: 0.1em; font-weight: 600;
  margin-right: 6px;
}}

/* --- live gallery -------------------------------------------------------- */
.pg-gallery-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 14px;
  margin-top: 8px;
}}
.pg-gallery-card {{
  background: {SURFACE};
  border: 1px solid {LINE};
  border-radius: 10px;
  overflow: hidden;
}}
.pg-gallery-card__media {{
  position: relative;
  background: {SURFACE_INSET};
}}
.pg-gallery-card__media video,
.pg-gallery-card__media img {{
  width: 100%;
  height: auto;
  display: block;
}}
.pg-gallery-card__pop {{
  position: absolute; bottom: 8px; left: 8px;
}}
.pg-gallery-card__body {{
  padding: 10px 12px 12px 12px;
}}
.pg-gallery-card__id {{
  font-family: {FONT_MONO};
  font-size: 12px;
  color: {INK_1};
  font-weight: 500;
  text-decoration: none;
}}
.pg-gallery-card__meta {{
  display: flex; justify-content: space-between; align-items: baseline;
  margin-top: 6px;
  font-size: 11px;
}}
.pg-gallery-card__env {{
  color: {INK_3};
  font-family: {FONT_MONO};
}}
.pg-gallery-card__success-ok {{ color: {OK}; font-weight: 600; }}
.pg-gallery-card__success-fail {{ color: {ERR}; font-weight: 600; }}

.pg-gallery-empty {{
  padding: 28px;
  text-align: center;
  color: {INK_4};
  font-style: italic;
  border: 1px dashed {LINE_2};
  border-radius: 10px;
  margin-top: 8px;
}}
.pg-gallery-more {{
  font-size: 11px; color: {INK_4};
  margin-top: 10px; text-align: center;
}}

/* --- cluster card (synthesis) -------------------------------------------- */
.pg-cluster-card {{
  margin: 16px 0;
  padding: 20px;
  background: {SURFACE};
  border: 1px solid {LINE};
  border-radius: 10px;
}}
.pg-cluster-card__head {{
  display: flex; align-items: baseline; justify-content: space-between;
  border-bottom: 1px solid {LINE};
  padding-bottom: 10px;
  margin-bottom: 14px;
}}
.pg-cluster-card__title {{
  margin: 0;
  font-family: {FONT_MONO};
  font-size: 16px;
  color: {INK_1};
  font-weight: 500;
}}
.pg-cluster-card__count {{
  font-size: 13px;
  color: {INK_3};
}}
.pg-cluster-card__count b {{
  color: {INK_1};
  font-variant-numeric: tabular-nums;
}}
.pg-cluster-card__breakdown {{
  margin-bottom: 14px;
}}
.pg-cluster-card__breakdown-chip {{
  display: inline-block;
  padding: 3px 10px;
  margin: 2px 4px 2px 0;
  background: {ACCENT_SOFT};
  color: {ACCENT_DEEP};
  border-radius: 999px;
  font-size: 12px;
}}
.pg-cluster-card__thumbs {{
  display: flex; flex-wrap: wrap;
}}
.pg-thumb {{
  display: inline-block;
  margin: 6px;
  vertical-align: top;
  width: 180px;
}}
.pg-thumb a {{ display: block; text-decoration: none; color: inherit; }}
.pg-thumb__media {{ position: relative; }}
.pg-thumb__media img {{
  width: 180px; height: auto; display: block;
  border-radius: 6px;
  border: 1px solid {LINE};
}}
.pg-thumb__pop {{ position: absolute; bottom: 8px; left: 8px; }}
.pg-thumb__id {{
  font-family: {FONT_MONO};
  font-size: 11px;
  text-align: center;
  margin-top: 4px;
  color: {INK_3};
}}
.pg-thumb__empty {{
  color: {INK_4}; font-style: italic; font-size: 12px;
}}

/* --- tables (per-label, drill-down) ------------------------------------- */
.pg-table {{
  background: {SURFACE};
  border: 1px solid {LINE};
  border-radius: 10px;
  padding: 14px;
  margin-bottom: 18px;
}}
.pg-table__eyebrow {{
  font-family: {FONT_MONO};
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.16em;
  margin-bottom: 10px;
}}
.pg-table__row {{
  display: grid;
  gap: 8px;
  padding: 8px 10px;
  align-items: baseline;
  border-bottom: 1px solid {LINE};
}}
.pg-table__row:last-child {{ border-bottom: none; }}
.pg-table__row--head {{
  color: {INK_4};
  font-family: {FONT_MONO};
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  border-bottom-color: {LINE_2};
}}
.pg-table__cell-mono {{
  font-family: {FONT_MONO};
  font-variant-numeric: tabular-nums;
  font-size: 12px;
  color: {INK_2};
}}
.pg-table__cell-muted {{ color: {INK_4}; }}

/* --- cohort strip -------------------------------------------------------- */
.pg-cohort-strip {{
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}}
.pg-cohort-pill {{
  padding: 10px 16px;
  background: {SURFACE};
  border: 1px solid {LINE};
  border-left-width: 3px;
  border-radius: 999px;
  display: flex;
  align-items: baseline;
  gap: 10px;
}}
.pg-cohort-pill__label {{
  font-family: {FONT_MONO};
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  font-weight: 600;
}}
.pg-cohort-pill__value {{
  font-family: {FONT_DISPLAY};
  font-size: 20px;
  font-weight: 500;
  color: {INK_1};
  font-variant-numeric: tabular-nums;
}}

/* --- calibration trust / judge header ----------------------------------- */
.pg-callout {{
  padding: 14px 18px;
  background: {SURFACE};
  border: 1px solid {LINE};
  border-left: 4px solid {JUDGE};
  border-radius: 8px;
  margin-bottom: 14px;
}}
.pg-callout--dep {{ border-left-color: {DEP}; }}
.pg-callout__eyebrow {{
  font-family: {FONT_MONO};
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  margin-bottom: 8px;
}}
.pg-callout__body {{
  color: {INK_2};
  font-size: 14px;
  line-height: 1.55;
}}
.pg-callout__grid {{
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 6px 18px;
  font-family: {FONT_MONO};
  font-size: 13px;
  color: {INK_2};
  line-height: 1.5;
}}
.pg-callout__grid-label {{ color: {INK_4}; }}
.pg-callout__note {{
  margin-top: 10px;
  font-size: 12px;
  color: {INK_3};
  font-style: italic;
}}

/* --- binary panel -------------------------------------------------------- */
.pg-binary {{
  padding: 18px;
  background: {SURFACE};
  border: 1px solid {LINE};
  border-radius: 10px;
  margin-bottom: 18px;
}}
.pg-binary__eyebrow {{
  font-family: {FONT_MONO};
  font-size: 11px;
  font-weight: 700;
  color: {ROLLOUT};
  text-transform: uppercase;
  letter-spacing: 0.16em;
  margin-bottom: 12px;
}}
.pg-binary__row {{
  display: flex; gap: 32px; align-items: flex-start;
}}
.pg-binary__matrix {{
  display: grid;
  grid-template-columns: auto 1fr 1fr;
  gap: 6px;
  width: 280px;
}}
.pg-binary__axis-label {{
  color: {INK_4};
  font-family: {FONT_MONO};
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  text-align: center;
  padding: 6px;
}}
.pg-binary__cell {{
  padding: 18px;
  text-align: center;
  font-size: 22px;
  font-weight: 600;
  border-radius: 6px;
  font-variant-numeric: tabular-nums;
  border: 1px solid {LINE};
  color: {INK_1};
  background: {SURFACE_2};
  font-family: {FONT_DISPLAY};
}}
.pg-binary__cell--ok  {{ background: {OK_SOFT}; color: {OK}; }}
.pg-binary__cell--err {{ background: {ERR_SOFT}; color: {ERR}; }}
.pg-binary__cell--empty {{ color: {INK_5}; }}

.pg-binary__stats {{ flex: 1; }}
.pg-binary__stat {{
  display: flex; align-items: baseline; gap: 10px;
  padding: 8px 0;
  border-bottom: 1px solid {LINE};
}}
.pg-binary__stat:last-child {{ border-bottom: none; }}
.pg-binary__stat-label {{
  width: 88px;
  font-family: {FONT_MONO};
  font-size: 11px;
  color: {INK_4};
  text-transform: uppercase;
  letter-spacing: 0.1em;
  font-weight: 600;
}}
.pg-binary__stat-frac {{
  font-family: {FONT_MONO};
  font-size: 13px;
  color: {INK_3};
  font-variant-numeric: tabular-nums;
}}
.pg-binary__stat-pct {{
  font-family: {FONT_DISPLAY};
  font-size: 18px;
  font-weight: 500;
  color: {INK_1};
  font-variant-numeric: tabular-nums;
}}
.pg-binary__stat-ci {{
  color: {INK_4};
  font-size: 11px;
  margin-left: 6px;
  font-family: {FONT_MONO};
}}
.pg-binary__caption {{
  font-size: 11px; color: {INK_4};
  margin-top: 12px;
}}
.pg-binary__caption code {{
  background: {SURFACE_INSET};
  padding: 1px 5px; border-radius: 3px;
  font-size: 11px;
}}

/* --- filter pill --------------------------------------------------------- */
.pg-filter-pill {{
  display: flex; gap: 10px; align-items: center;
  padding: 8px 14px;
  background: {WARN_SOFT};
  border: 1px solid {WARN_SOFT};
  border-left: 3px solid {WARN};
  border-radius: 8px;
}}
.pg-filter-pill__label {{
  font-family: {FONT_MONO};
  font-size: 10px;
  color: {INK_4};
  text-transform: uppercase;
  letter-spacing: 0.1em;
  font-weight: 600;
}}
.pg-filter-pill__value {{
  font-family: {FONT_MONO};
  font-size: 12px;
  color: {WARN};
  font-weight: 600;
}}

/* --- empty / placeholder ------------------------------------------------- */
.pg-empty {{
  padding: 40px; text-align: center;
  color: {INK_4}; font-style: italic;
}}
.pg-empty--small {{ padding: 18px; }}

/* --- file list ----------------------------------------------------------- */
.pg-filelist {{
  max-height: 600px; overflow-y: auto;
  font-family: {FONT_MONO};
  font-size: 12px;
}}
.pg-filelist__row {{ padding: 3px 0; color: {INK_2}; }}
.pg-filelist__size {{ color: {INK_4}; }}

/* --- drill-down rows ----------------------------------------------------- */
.pg-drill-thumb {{
  position: relative;
  width: 140px;
}}
.pg-drill-thumb img {{
  width: 140px; height: auto; display: block;
  border-radius: 4px;
  border: 1px solid {LINE};
}}
.pg-drill-thumb--empty {{
  width: 140px; height: 80px;
  background: {SURFACE_INSET};
  border-radius: 4px;
  color: {INK_4};
  font-size: 10px;
  display: flex; align-items: center; justify-content: center;
}}
.pg-drill-link {{
  color: {ACCENT};
  text-decoration: none;
  font-family: {FONT_MONO};
  font-size: 12px;
}}
.pg-drill-link:hover {{ text-decoration: underline; }}

.pg-match-badge {{
  display: inline-block;
  padding: 2px 10px;
  border-radius: 999px;
  font-family: {FONT_MONO};
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}}
.pg-match-badge--ok  {{ background: {OK_SOFT};  color: {OK}; }}
.pg-match-badge--err {{ background: {ERR_SOFT}; color: {ERR}; }}
"""
