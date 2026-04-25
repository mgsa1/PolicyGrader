"""CSS class-name constants + small HTML-primitive helpers.

One source of truth for the class names used by `src/ui/panes/*`. Keeping them
here stops stringly-typed class names from drifting across files and means a
rename to `tokens.css` only touches this module.

Utility helpers (`num`, `chip`, `monogram`, …) return tiny HTML fragments that
hang off the classes defined in `src/ui/assets/tokens.css`. Nothing here
encodes colors or spacings — those live in `tokens.css`.
"""

from __future__ import annotations

import re
from pathlib import Path

from markdown_it import MarkdownIt

# ---- Paths ----------------------------------------------------------------------

_ASSETS_DIR = Path(__file__).resolve().parent / "assets"
TOKENS_CSS_PATH: Path = _ASSETS_DIR / "tokens.css"


def tokens_css_path() -> str:
    """Absolute path to tokens.css, as a string gradio's css_paths expects."""
    return str(TOKENS_CSS_PATH)


# ---- Root wrapper --------------------------------------------------------------
# Every pane's top-level gr.HTML content should sit under .pg so that
# tokens.css's font + color rules apply. The wrapper div is injected once by
# `app.py`; panes emit markup that is already descendant of .pg.

ROOT_CLASS = "pg"

# ---- Card / chip / table constants ---------------------------------------------

CLS_CARD = "pg-card"
CLS_KPI_GRID = "pg-kpi-grid"
CLS_KPI_CELL = "pg-kpi-cell"
CLS_CHIP = "pg-chip"
CLS_CHIP_CAL = "pg-chip cal"
CLS_CHIP_DEP = "pg-chip dep"
CLS_CHIP_OK = "pg-chip ok"
CLS_CHIP_WARN = "pg-chip warn"
CLS_CHIP_ERR = "pg-chip err"
CLS_TABLE = "pg-table"

# Phase short-codes used as class modifiers across memories tree, agent trace,
# phase strip, and the hero eyebrow. The phrase "planner/rollout/judge/report"
# matches the `--pg-phase-*` token names exactly.
PHASE_CODES: tuple[str, ...] = ("planner", "rollout", "judge", "report")


def html_escape(text: str) -> str:
    """Minimal HTML-entity escape for user / agent-provided text."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# CommonMark renderer for agent prose in the Live trace. `html=False` means
# raw HTML inside agent output is escaped (same safety posture as
# html_escape above); `linkify` turns bare URLs into links; `breaks` keeps
# soft newlines visible, matching the pre-wrap feel the feed had before.
_MD = MarkdownIt("commonmark", {"html": False, "linkify": True, "breaks": True})

_UNCLOSED_FENCE_RE = re.compile(r"^```", re.MULTILINE)


def render_markdown(text: str) -> str:
    """Render agent-produced CommonMark to HTML for the Live trace.

    Truncated `agent_thinking` blocks can slice inside a fenced code block —
    an odd number of ``` lines would then render the rest of the event (and
    arguably the feed) as one big `<pre>`. We close the dangling fence here
    so the renderer stays well-formed regardless of upstream slicing.
    """
    if len(_UNCLOSED_FENCE_RE.findall(text)) % 2:
        text = text + "\n```"
    return str(_MD.render(text))


# Full-document renderer for the final report.md — GFM tables on (reporter's
# cost-vs-baseline block is a pipe table); `breaks=False` so paragraph wraps
# don't insert <br>s between cells.
_MD_REPORT = MarkdownIt("gfm-like", {"html": False, "linkify": False, "breaks": False})


def render_report_markdown(text: str) -> str:
    """Render the agent's final report.md (GFM tables, safe HTML)."""
    return str(_MD_REPORT.render(text))


# ---- Tiny HTML primitives ------------------------------------------------------


def num(value: str) -> str:
    """Wrap a numeric rendering in `<span class="num">` — mono + tabular-nums.

    DESIGN.md §1: "Numbers are mono + tabular" — every numeric value in user-
    facing markup passes through this helper so the tabular-nums rule is
    applied uniformly (font-variant-numeric lives on `.num` in tokens.css).
    """
    return f'<span class="num">{value}</span>'


def chip(
    text: str,
    *,
    variant: str | None = None,
    sub: str | None = None,
    title: str | None = None,
) -> str:
    """Pill chip — `variant` ∈ {None, 'cal', 'dep', 'ok', 'warn', 'err', 'phase'}.

    Follows tokens.css's convention `<span class="pg-chip cal">…` (space-
    separated classes, not BEM double-dash). `sub` flows a muted sub-label
    after the main text.
    """
    classes = CLS_CHIP if variant is None else f"{CLS_CHIP} {variant}"
    title_attr = f' title="{html_escape(title)}"' if title else ""
    sub_html = "" if sub is None else f' <span class="pg-chip-sub">{html_escape(sub)}</span>'
    return f'<span class="{classes}"{title_attr}>{html_escape(text)}{sub_html}</span>'


def phase_chip(
    phase: str,
    state: str,
    *,
    counter: str | None = None,
    sub: str | None = None,
) -> str:
    """One phase tile in the progress strip.

    `phase` ∈ PHASE_CODES ("planner"/"rollout"/"judge"/"report");
    `state` ∈ {'pending','active','complete'}.
    """
    title = {
        "planner": "Phase 1: Planner",
        "rollout": "Phase 2: Rollout",
        "judge": "Phase 3: Judge",
        "report": "Phase 4: Report",
    }[phase]
    status_text = {"pending": "○ pending", "active": "● active", "complete": "✓ complete"}[state]
    counter_html = f'<div class="pg-phase-chip-counter">{counter}</div>' if counter else ""
    sub_html = f'<div class="pg-phase-chip-sub">{html_escape(sub)}</div>' if sub else ""
    return (
        f'<div class="pg-phase-chip {phase} {state}">'
        '<div class="pg-phase-chip-head">'
        f'<div class="pg-phase-chip-title">{title}</div>'
        f'<div class="pg-phase-chip-status">{status_text}</div>'
        "</div>"
        f"{counter_html}{sub_html}"
        "</div>"
    )


def phase_progress_bar(phase: str, done: int, total: int) -> str:
    """A 4px phase-colored bar — paired with `phase_chip` above."""
    pct = min(100, int(done / total * 100)) if total > 0 else 0
    return f'<div class="pg-phase-chip-bar {phase}"><span style="width:{pct}%;"></span></div>'


def monogram() -> str:
    """PG logo — 28×28 ink square with white 'PG' in Google Sans."""
    return '<div class="pg-logo">PG</div>'


def kbd(text: str) -> str:
    """Inline monospaced chip for paths / identifiers."""
    return f'<span class="pg-kbd">{html_escape(text)}</span>'


def inline_rail(value: float, *, ok_threshold: float = 0.9, accent_threshold: float = 0.7) -> str:
    """4px horizontal rail for table cells — fill = value, color by threshold.

    Matches DESIGN.md §3 "Tables": `.ok` at ≥ ok_threshold, `.accent` at ≥
    accent_threshold, `.warn` otherwise.
    """
    value = max(0.0, min(1.0, value))
    if value >= ok_threshold:
        modifier = "ok"
    elif value >= accent_threshold:
        modifier = "accent"
    else:
        modifier = "warn"
    pct = int(value * 100)
    return f'<span class="pg-inline-rail {modifier}"><span style="width:{pct}%;"></span></span>'


# ---- Empty-state blocks ---------------------------------------------------------


def empty(text: str, *, small: bool = False) -> str:
    cls = "pg-empty small" if small else "pg-empty"
    return f'<div class="{cls}">{html_escape(text)}</div>'
