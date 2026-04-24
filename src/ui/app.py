"""Gradio shell over a runs-root directory.

The app is a thin file watcher: it polls each selected run's mirror_root
every second (runtime.json / chat.jsonl / rollouts) plus every 5 seconds
for heavier pieces (metrics blocks, heatmap, cluster cards).

All layout and rendering lives under `src/ui/panes/`. This module only:
  1. discovers runs and builds the run-picker dropdown,
  2. wires the Gradio Tabs + Blocks scaffolding,
  3. routes Timer ticks and picker changes to the right pane renderers.

CSS is loaded via `src/ui/assets/tokens.css` (passed as `css_paths=[...]`
on `.launch()` by the caller); `src/ui/theme.CSS` provides small Gradio-
internal overrides (tabs / accordion / dropdown) layered on top.

Launch with `python -m src.ui.app --runs-root <dir>` or `scripts/run_ui.py`.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import gradio as gr

from src.costing import format_cost
from src.runtime_state import RunInfo, discover_runs
from src.ui import styles, theme
from src.ui.metrics_view import EMPTY_FILTER, DrillFilter
from src.ui.panes import calibration, chrome, findings, live, overview

REFRESH_SECONDS = 1.0
HEAVY_REFRESH_SECONDS = 5.0


# ---- Run-picker helpers ---------------------------------------------------------


def _run_picker_choices(runs_root: Path) -> list[tuple[str, str]]:
    runs = discover_runs(runs_root)
    return [(_run_picker_label(r), str(r.mirror_root)) for r in runs]


def _run_picker_label(r: RunInfo) -> str:
    started_str = _relative_time(r.started_at) if r.started_at > 0 else "unknown"
    cost_str = format_cost(r.cost_usd) if r.cost_usd else "$0.00"
    phase_short = chrome.phase_short(r.phase)
    return f"{r.run_id} · {r.n_rollouts} rollouts · {cost_str} · {phase_short} · {started_str}"


def _relative_time(epoch_seconds: float) -> str:
    import time as _time

    delta = _time.time() - epoch_seconds
    if delta < 60:
        return "just now"
    if delta < 3600:
        return f"{int(delta // 60)}m ago"
    if delta < 86400:
        return f"{int(delta // 3600)}h ago"
    return f"{int(delta // 86400)}d ago"


# ---- Footer ---------------------------------------------------------------------


def _footer_html() -> str:
    return (
        '<div style="margin:24px 0 12px 0;padding:14px 18px;'
        "border-top:1px solid var(--pg-line);text-align:center;"
        'font-size:12px;color:var(--pg-ink-4);">'
        '<a href="https://github.com/mgsa1" target="_blank" rel="noopener" '
        'style="color:var(--pg-ink-3);text-decoration:none;margin:0 10px;">GitHub</a>'
        '<span style="color:var(--pg-ink-5);">·</span>'
        '<a href="https://gdsa.eu" target="_blank" rel="noopener" '
        'style="color:var(--pg-ink-3);text-decoration:none;margin:0 10px;">gdsa.eu</a>'
        "</div>"
    )


# ---- Per-renderer wrappers ------------------------------------------------------
# Each takes a selected-run string (the dropdown emits str) so timer.tick can
# plumb a single input through. All IO happens against the mirror_root Path.


def _as_path(run: str) -> Path:
    return Path(run)


def _overview_for(run: str) -> str:
    return overview.overview_html(_as_path(run))


def _hero_for(run: str) -> str:
    return chrome.hero_html(_as_path(run))


def _phase_for(run: str) -> str:
    return chrome.phase_progress_html(_as_path(run))


def _topbar_meta_for(run: str) -> str:
    return chrome.topbar_meta_html(_as_path(run))


def _trace_for(run: str) -> str:
    return live.agent_trace_html(_as_path(run))


def _current_video_for(run: str) -> str | None:
    return live.current_video_path(_as_path(run))


def _current_video_path_for(run: str) -> str:
    return live.current_video_path_html(_as_path(run))


def _gallery_for(run: str) -> str:
    return live.live_gallery_html(_as_path(run))


def _memories_for(run: str) -> str:
    return live.memories_tree_html(_as_path(run))


def _cal_metrics_for(run: str) -> tuple[str, str, str]:
    return calibration.metrics_blocks(_as_path(run))


def _cal_scope_for(run: str) -> str:
    return chrome.scope_strip_html(_as_path(run), "calibration")


def _dep_scope_for(run: str) -> str:
    return chrome.scope_strip_html(_as_path(run), "deployment")


def _trust_for(run: str) -> str:
    return chrome.judge_trust_banner_html(_as_path(run))


def _findings_label_for(run: str) -> str:
    return findings.cluster_cards_html(_as_path(run), "label")


def _findings_condition_for(run: str) -> str:
    return findings.cluster_cards_html(_as_path(run), "condition")


def _findings_table_for(run: str) -> str:
    return findings.rollout_table_html(_as_path(run))


# ---- Builder --------------------------------------------------------------------


def build_app(runs_root: Path) -> gr.Blocks:
    """Construct the Gradio Blocks app over a directory of runs."""
    runs_root.mkdir(parents=True, exist_ok=True)

    initial_choices = _run_picker_choices(runs_root)
    initial_run = initial_choices[0][1] if initial_choices else str(runs_root / "_no_runs_yet")
    initial_path = Path(initial_run)

    with gr.Blocks(title="PolicyGrader") as app:
        # Open the .pg wrapper so every descendant inherits the token palette.
        gr.HTML(value=f'<div class="{styles.ROOT_CLASS}">')

        with gr.Row(elem_classes=["pg-topbar-row"]):
            gr.HTML(value=chrome.topbar_brand_html())
            with gr.Row(elem_classes=["pg-topbar-meta-row"]):
                run_picker = gr.Dropdown(
                    choices=initial_choices,
                    value=initial_run if initial_choices else None,
                    label="",
                    show_label=False,
                    interactive=True,
                    container=False,
                    allow_custom_value=False,
                    elem_classes=["pg-run-picker"],
                )
                topbar_meta = gr.HTML(value=chrome.topbar_meta_html(initial_path))

        selected_run = gr.State(value=initial_run)

        hero_html = gr.HTML(value=chrome.hero_html(initial_path))
        phase_html = gr.HTML(value=chrome.phase_progress_html(initial_path))

        with gr.Tabs():
            with gr.Tab("Overview"):
                overview_html = gr.HTML(value=overview.overview_html(initial_path))

            with gr.Tab("Live"):
                with gr.Accordion("What is this tool doing?", open=False):
                    gr.HTML(value=live.read_intro_html())
                with gr.Row():
                    with gr.Column(scale=2):
                        gr.Markdown("### Agent activity")
                        trace_html = gr.HTML(value=live.agent_trace_html(initial_path))
                    with gr.Column(scale=3):
                        gr.Markdown("### Current rollout")
                        current_video = gr.Video(
                            value=live.current_video_path(initial_path),
                            autoplay=True,
                            loop=True,
                            height=400,
                        )
                        current_video_path = gr.HTML(
                            value=live.current_video_path_html(initial_path)
                        )
                        gr.Markdown("### All rollouts")
                        gallery_html = gr.HTML(value=live.live_gallery_html(initial_path))
                        gr.Markdown("### /memories/ — host mirror")
                        memories_html = gr.HTML(value=live.memories_tree_html(initial_path))

            with gr.Tab("Judge calibration"):
                cal_scope_html = gr.HTML(value=chrome.scope_strip_html(initial_path, "calibration"))
                gr.HTML(value=calibration.calibration_header_html())
                initial_blocks = calibration.metrics_blocks(initial_path)
                cal_cohort_html = gr.HTML(value=initial_blocks[0])
                cal_caption_html = gr.HTML(value=initial_blocks[1])
                # Per-label breakdown sits ABOVE the confusion matrix so that
                # the matrix sits directly above the drill filters + table —
                # clicking a cell narrows the table immediately below it.
                cal_per_label_html = gr.HTML(value=initial_blocks[2])

                with gr.Column(elem_classes=["pg-cm"]):
                    gr.HTML(
                        value=(
                            "<div class='pg-cm-eyebrow'>"
                            "Multiclass confusion matrix (click a cell to filter)"
                            "</div>"
                        )
                    )
                    cm_html = gr.HTML(value=calibration.matrix_html(initial_path))

                # Hidden bridge: an inline-script onclick on the matrix cells
                # writes "<seq>|<expected>::<judged>" into this textbox; the
                # leading sequence number ensures repeat clicks on the same
                # cell still fire .input (the textbox sees a different value).
                cm_click = gr.Textbox(
                    value="",
                    visible=False,
                    elem_id="pg-cm-payload",
                )

                gr.HTML(value=calibration.drill_description_html())
                initial_labels = calibration.heatmap_labels(initial_path)
                with gr.Row():
                    filter_expected = gr.Dropdown(
                        label="Expected label",
                        choices=initial_labels,
                        value=None,
                        interactive=True,
                    )
                    filter_judged = gr.Dropdown(
                        label="Judged label",
                        choices=initial_labels,
                        value=None,
                        interactive=True,
                    )
                filter_status = gr.HTML(value="")
                drill_html = gr.HTML(value=calibration.drill_html(initial_path, EMPTY_FILTER))

            with gr.Tab("Deployment findings"):
                dep_scope_html = gr.HTML(value=chrome.scope_strip_html(initial_path, "deployment"))
                trust_html = gr.HTML(value=chrome.judge_trust_banner_html(initial_path))
                with gr.Tabs():
                    with gr.Tab("By label"):
                        gr.Markdown(
                            "**Each card** = one judge taxonomy label seen across "
                            "all failed rollouts. Each rollout in the card carries "
                            "its population chip (calibration vs deployment). "
                            "Click a keyframe to open the source mp4."
                        )
                        findings_label_html = gr.HTML(
                            value=findings.cluster_cards_html(initial_path, "label")
                        )
                    with gr.Tab("By condition"):
                        gr.Markdown(
                            "**Each card** = one perturbation condition (or env+policy "
                            "combination for deployment rollouts)."
                        )
                        findings_condition_html = gr.HTML(
                            value=findings.cluster_cards_html(initial_path, "condition")
                        )
                gr.Markdown("### All deployment rollouts")
                findings_table_html = gr.HTML(value=findings.rollout_table_html(initial_path))

        gr.HTML(value=_footer_html())
        gr.HTML(value="</div>")  # close .pg wrapper

        # ---- Fast-refresh timers (1 s) -----------------------------------------
        timer = gr.Timer(REFRESH_SECONDS)
        timer.tick(fn=_hero_for, inputs=[selected_run], outputs=hero_html)
        timer.tick(fn=_phase_for, inputs=[selected_run], outputs=phase_html)
        timer.tick(fn=_topbar_meta_for, inputs=[selected_run], outputs=topbar_meta)
        timer.tick(fn=_trace_for, inputs=[selected_run], outputs=trace_html)
        timer.tick(fn=_current_video_for, inputs=[selected_run], outputs=current_video)
        timer.tick(fn=_current_video_path_for, inputs=[selected_run], outputs=current_video_path)
        timer.tick(fn=_gallery_for, inputs=[selected_run], outputs=gallery_html)
        timer.tick(fn=_memories_for, inputs=[selected_run], outputs=memories_html)

        # ---- Slower timers (5 s) -----------------------------------------------
        heavy = gr.Timer(HEAVY_REFRESH_SECONDS)
        heavy.tick(fn=_overview_for, inputs=[selected_run], outputs=overview_html)
        heavy.tick(
            fn=_cal_metrics_for,
            inputs=[selected_run],
            outputs=[cal_cohort_html, cal_caption_html, cal_per_label_html],
        )
        # Confusion-matrix HTML refresh on the slow timer.
        heavy.tick(
            fn=lambda r: calibration.matrix_html(_as_path(r)),
            inputs=[selected_run],
            outputs=cm_html,
        )

        # JS bridge: cell-button onclick writes "<seq>|exp::jud" into cm_click.
        # Parse, drop the seq prefix, dispatch the drill update.
        def _on_cm_click(payload: str, run: str) -> tuple[Any, Any, str, str]:
            if not payload or "::" not in payload:
                return gr.skip(), gr.skip(), gr.skip(), gr.skip()
            after_seq = payload.split("|", 1)[-1]
            exp, jud = after_seq.split("::", 1)
            f = DrillFilter(expected=exp, judged=jud)
            return (
                gr.update(value=exp),
                gr.update(value=jud),
                calibration.filter_status_html(f),
                calibration.drill_html(_as_path(run), f),
            )

        cm_click.input(
            fn=_on_cm_click,
            inputs=[cm_click, selected_run],
            outputs=[filter_expected, filter_judged, filter_status, drill_html],
        )
        heavy.tick(fn=_cal_scope_for, inputs=[selected_run], outputs=cal_scope_html)
        heavy.tick(fn=_dep_scope_for, inputs=[selected_run], outputs=dep_scope_html)
        heavy.tick(fn=_trust_for, inputs=[selected_run], outputs=trust_html)
        heavy.tick(fn=_findings_label_for, inputs=[selected_run], outputs=findings_label_html)
        heavy.tick(
            fn=_findings_condition_for, inputs=[selected_run], outputs=findings_condition_html
        )
        heavy.tick(fn=_findings_table_for, inputs=[selected_run], outputs=findings_table_html)

        # Refresh the picker's choices AND auto-switch to the most-recent run if
        # the current selection has gone stale (placeholder, deleted, etc.). The
        # state update lets every panel pick the new run up on its next tick.
        def _refresh_picker(current: str) -> tuple[Any, str]:
            choices = _run_picker_choices(runs_root)
            current_valid = bool(current) and (Path(current) / "runtime.json").exists()
            if current_valid or not choices:
                return gr.update(choices=choices), current
            new_value = choices[0][1]
            return gr.update(choices=choices, value=new_value), new_value

        heavy.tick(
            fn=_refresh_picker,
            inputs=[selected_run],
            outputs=[run_picker, selected_run],
        )

        # ---- Drill-filter handlers ---------------------------------------------
        def _on_filter_change(
            run: str, expected: str | None, judged: str | None
        ) -> tuple[str, str]:
            f = DrillFilter(expected=expected or None, judged=judged or None)
            return calibration.filter_status_html(f), calibration.drill_html(_as_path(run), f)

        filter_expected.change(
            fn=_on_filter_change,
            inputs=[selected_run, filter_expected, filter_judged],
            outputs=[filter_status, drill_html],
        )
        filter_judged.change(
            fn=_on_filter_change,
            inputs=[selected_run, filter_expected, filter_judged],
            outputs=[filter_status, drill_html],
        )

        def _refresh_dropdowns(run: str) -> tuple[Any, Any]:
            labels = calibration.heatmap_labels(_as_path(run))
            return gr.update(choices=labels), gr.update(choices=labels)

        heavy.tick(
            fn=_refresh_dropdowns,
            inputs=[selected_run],
            outputs=[filter_expected, filter_judged],
        )

        def _refresh_drill(run: str, expected: str | None, judged: str | None) -> str:
            f = DrillFilter(expected=expected or None, judged=judged or None)
            return calibration.drill_html(_as_path(run), f)

        heavy.tick(
            fn=_refresh_drill,
            inputs=[selected_run, filter_expected, filter_judged],
            outputs=drill_html,
        )

        # ---- Run picker → state + full re-render -------------------------------
        def _on_run_change(new_run: str) -> tuple[Any, ...]:
            p = Path(new_run)
            blocks = calibration.metrics_blocks(p)
            return (
                new_run,
                chrome.topbar_meta_html(p),
                chrome.hero_html(p),
                chrome.phase_progress_html(p),
                overview.overview_html(p),
                live.agent_trace_html(p),
                live.current_video_path(p),
                live.current_video_path_html(p),
                live.live_gallery_html(p),
                live.memories_tree_html(p),
                chrome.scope_strip_html(p, "calibration"),
                blocks[0],
                blocks[1],
                blocks[2],
                chrome.scope_strip_html(p, "deployment"),
                chrome.judge_trust_banner_html(p),
                findings.cluster_cards_html(p, "label"),
                findings.cluster_cards_html(p, "condition"),
                findings.rollout_table_html(p),
                calibration.drill_html(p, EMPTY_FILTER),
                calibration.matrix_html(p),
            )

        run_picker.change(
            fn=_on_run_change,
            inputs=[run_picker],
            outputs=[
                selected_run,
                topbar_meta,
                hero_html,
                phase_html,
                overview_html,
                trace_html,
                current_video,
                current_video_path,
                gallery_html,
                memories_html,
                cal_scope_html,
                cal_cohort_html,
                cal_caption_html,
                cal_per_label_html,
                dep_scope_html,
                trust_html,
                findings_label_html,
                findings_condition_html,
                findings_table_html,
                drill_html,
                cm_html,
            ],
        )

    assert isinstance(app, gr.Blocks)
    return app


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs-root", type=Path, required=True)
    parser.add_argument("--port", type=int, default=7860)
    args = parser.parse_args()

    runs_root = args.runs_root.resolve()
    app = build_app(runs_root)
    app.launch(
        server_port=args.port,
        inbrowser=True,
        theme=gr.themes.Soft(primary_hue="blue", neutral_hue="gray"),
        css=theme.CSS,
        css_paths=[styles.tokens_css_path()],
        allowed_paths=[str(runs_root)],
    )


if __name__ == "__main__":
    main()
