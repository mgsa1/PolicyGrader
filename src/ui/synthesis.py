"""Failure-synthesis layer for the Gradio UI (and Remotion later).

Reads `mirror_root/dispatch_log.jsonl` (which the orchestrator-side dispatch
appends to on every rollout/judge call) and turns it into clusters of
related failures with keyframe evidence. Two grouping modes:

  1. by_label   — one cluster per judge taxonomy_label that appears.
                  "8 failures judged approach_miss" + 8 keyframes.
  2. by_condition — one cluster per scripted-knob condition that's perturbed
                    plus one per (env, policy) combination for pretrained
                    rollouts. "3 failures with angle_offset>0" + 3 keyframes.

Each cluster card shows: name + count + % of total failures + breakdown by
the OTHER axis (e.g., a by_condition cluster shows label distribution
within it) + grid of keyframes. Keyframes are the frame the judge named
(`frame_index`) from the original mp4, with a red dot drawn at the judge's
`point` coordinate — OR no dot at all when the judge returned `point=None`
(abstention on no-contact failures like approach_miss).

Pure module — no Gradio imports — so it's testable in isolation and reusable
by Remotion or any other consumer.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from src.agents.tools import DISPATCH_LOG
from src.ui import theme
from src.vision.frames import read_frames, resize_long_edge
from src.vision.judge import JUDGE_LONG_EDGE_PX

KEYFRAMES_DIR_NAME = "keyframes"
THUMBNAIL_LONG_EDGE_PX = 384
POINT_DOT_RADIUS_PX = 16
POINT_DOT_OUTLINE_WIDTH = 4

# ---- Population palette ---------------------------------------------------------
# The dashboard distinguishes two populations of rollouts everywhere:
#   - Calibration: scripted policy + injected failure (ground truth known)
#   - Deployment: pretrained / real policy (no ground truth label)
# Re-exported from theme so callers that want the raw hex (e.g. Plotly) can
# still reach for them; the CSS-class path (`pg-chip--cal/--dep`) is preferred.
CALIBRATION_COLOR = theme.CAL
DEPLOYMENT_COLOR = theme.DEP
CALIBRATION_LABEL = "Calibration"
DEPLOYMENT_LABEL = "Deployment"


# ---- Tiny shared HTML helpers -----------------------------------------------------
# Both src/ui/app.py and src/ui/metrics_view.py render keyframe + mp4 paths and
# want a consistent "copyable path" treatment. Defined here so they can share.


def html_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# Inline SVG icons used by copy_button. Both share the "two overlapping
# rectangles" copy semantic (so the user knows clicking copies to clipboard);
# the inner content of the back rectangle differentiates format:
#   mp4 → small play triangle
#   png → small landscape silhouette (mountain + sun)
_SVG_COPY_MP4 = (
    "<svg width='14' height='14' viewBox='0 0 24 24' fill='none' "
    "stroke='currentColor' stroke-width='1.6' stroke-linecap='round' "
    "stroke-linejoin='round'>"
    "<rect x='9' y='9' width='13' height='13' rx='2'/>"
    "<path d='M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1'/>"
    "<polygon points='14,13 14,18 18,15.5' fill='currentColor' stroke='none'/>"
    "</svg>"
)
_SVG_COPY_PNG = (
    "<svg width='14' height='14' viewBox='0 0 24 24' fill='none' "
    "stroke='currentColor' stroke-width='1.6' stroke-linecap='round' "
    "stroke-linejoin='round'>"
    "<rect x='9' y='9' width='13' height='13' rx='2'/>"
    "<path d='M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1'/>"
    "<circle cx='13' cy='13' r='1' fill='currentColor' stroke='none'/>"
    "<polyline points='10,19 13.5,15 16.5,17 20,14'/>"
    "</svg>"
)
_SVG_COPY_GENERIC = (
    "<svg width='14' height='14' viewBox='0 0 24 24' fill='none' "
    "stroke='currentColor' stroke-width='1.6' stroke-linecap='round' "
    "stroke-linejoin='round'>"
    "<rect x='9' y='9' width='13' height='13' rx='2'/>"
    "<path d='M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1'/>"
    "</svg>"
)
_SVG_CHECK = (
    "<svg width='14' height='14' viewBox='0 0 24 24' fill='none' "
    "stroke='currentColor' stroke-width='2.4' stroke-linecap='round' "
    "stroke-linejoin='round'><polyline points='20 6 9 17 4 12'/></svg>"
)


def copy_button(
    path: object,
    *,
    kind: str = "generic",  # "mp4" | "png" | "generic"
    tooltip: str | None = None,
    anchor: str | None = None,
    inline: bool = False,
) -> str:
    """Small clipboard-copy button. Format-aware SVG (mp4 = play, png = image).

    `anchor` (top-right / top-left / bottom-right / bottom-left) absolutely
    positions the button to overlay a thumbnail — the immediate parent must
    be position:relative. `inline=True` flows in normal layout (for cases
    where overlay isn't possible, like next to gr.Video).
    """
    p_str = str(path)
    js_safe = p_str.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")
    icon = {"mp4": _SVG_COPY_MP4, "png": _SVG_COPY_PNG}.get(kind, _SVG_COPY_GENERIC)
    js_check = _SVG_CHECK.replace("'", "\\'")
    js_icon = icon.replace("'", "\\'")
    if tooltip is None:
        tooltip = {
            "mp4": "Copy mp4 path",
            "png": "Copy keyframe PNG path",
        }.get(kind, "Copy path")
    title = html_escape(f"{tooltip}: {p_str}")

    classes = ["pg-icon-btn"]
    if anchor and not inline:
        classes.append("pg-icon-btn--anchored")
        classes.append(f"pg-icon-btn--{anchor}")
    else:
        classes.append("pg-icon-btn--inline")

    return (
        f'<button onclick="event.preventDefault();event.stopPropagation();'
        f"navigator.clipboard.writeText('{js_safe}');"
        f"this.innerHTML='{js_check}';"
        f"setTimeout(()=>this.innerHTML='{js_icon}',900)\" "
        f"title='{title}' "
        f"class='{' '.join(classes)}'>{icon}</button>"
    )


# Threshold below which we consider an injection knob "default" (not perturbed).
# Mirrors the knob-to-label mapping in src.agents.system_prompts:
#   action_noise >= 0.10 => knock_object_off_table
#   angle_deg > 0        => approach_miss
#   premature_close=True => approach_miss
#   grip_scale < 0.7     => slip_during_lift
_NOISE_PERTURBED_THRESHOLD = 0.10
_GRIP_SCALE_PERTURBED_THRESHOLD = 0.7


@dataclass(frozen=True)
class ScoredRollout:
    """One rollout's full record: config + sim outcome + judge annotation.

    Binary success comes from the simulator (`RolloutResult.success`), not
    from vision — that's what `success` and `is_failure` track. The judge
    only runs on sim-confirmed failures, so `judge_label` is non-None
    exactly when sim said fail AND the judge has finished; on successful
    rollouts (and failed rollouts where the judge hasn't run yet) the
    judge-* fields are all None.
    """

    rollout_id: str
    env_name: str
    policy_kind: str
    seed: int
    success: bool  # authoritative from sim._check_success()
    steps_taken: int
    ground_truth_label: str | None
    injection_knobs: dict[str, Any]
    judge_label: str | None  # None if sim_success or judge pending
    judge_frame_index: int | None  # original-mp4 frame index the judge named
    judge_point: tuple[int, int] | None  # 2576-px grid; None on abstention
    judge_description: str | None
    video_path_host: Path | None  # local mp4 path on host

    @property
    def is_failure(self) -> bool:
        """True if the rollout did not succeed (env's ground truth)."""
        return not self.success

    @property
    def judged_failure(self) -> bool:
        """True on rollouts sim flagged as failure AND the judge has labeled.

        Equivalent to `is_failure and judge_label is not None` — the judge
        only runs on sim failures, so this is "has the judge weighed in yet?"
        for the set of failures.
        """
        return (not self.success) and self.judge_label is not None

    @property
    def population(self) -> str:
        """'calibration' if injected ground truth exists, else 'deployment'."""
        return "calibration" if self.ground_truth_label else "deployment"


def population_chip(rollout: ScoredRollout, *, compact: bool = False) -> str:
    """Render the calibration/deployment chip for a rollout.

    Calibration chip shows the injected ground-truth label.
    Deployment chip shows the policy + 'no GT' so it's clear there's no
    label to compare against.
    """
    if rollout.population == "calibration":
        modifier = "cal"
        kind_label = CALIBRATION_LABEL
        sub = f"expected: {rollout.ground_truth_label}"
    else:
        modifier = "dep"
        kind_label = DEPLOYMENT_LABEL
        policy = "BC-RNN" if rollout.policy_kind == "pretrained" else rollout.policy_kind
        sub = f"{policy} · no GT"
    sub_html = "" if compact else f"<span class='pg-chip__sub'>{html_escape(sub)}</span>"
    return (
        f"<span class='pg-chip pg-chip--{modifier}'>"
        f"<span class='pg-chip__dot'>●</span>{kind_label}{sub_html}"
        "</span>"
    )


def cohort_split(rollouts: list[ScoredRollout]) -> tuple[int, int]:
    """Return (n_calibration, n_deployment)."""
    n_cal = sum(1 for r in rollouts if r.population == "calibration")
    return n_cal, len(rollouts) - n_cal


@dataclass(frozen=True)
class JudgeMetrics:
    """Multiclass judge calibration numbers, computed from dispatch_log.jsonl.

    Binary success is authoritative from sim so there is no vision-vs-sim
    binary panel — the only thing worth measuring is how often the judge's
    taxonomy label matches the injected ground-truth label on the
    calibration cohort. Successful rollouts with ground_truth_label="none"
    count as a correct "none" label (the judge doesn't run on them; we
    treat the no-judge-annotation-on-success case as an implicit "none").
    """

    n_total: int
    n_with_ground_truth: int  # calibration rollouts (injected label known)
    n_labeled: int  # of those, ones where the judge's verdict is determined
    label_correct: int  # of n_labeled, where judge_label == ground_truth

    @property
    def label_accuracy(self) -> float | None:
        if self.n_labeled == 0:
            return None
        return self.label_correct / self.n_labeled


def compute_metrics(rollouts: list[ScoredRollout]) -> JudgeMetrics:
    """Compute multiclass label accuracy on the calibration subset.

    For each calibration rollout:
      - sim_success=True: treat judge label as "none" (judge doesn't run on
        successes). Correct iff ground_truth_label == "none".
      - sim_success=False and judge_label set: correct iff labels match.
      - sim_success=False and judge_label None: judge pending; excluded
        from n_labeled.
    """
    n_with_gt = 0
    n_labeled = 0
    label_correct = 0

    for r in rollouts:
        if not r.ground_truth_label:
            continue  # deployment cohort; no ground truth to score against
        n_with_gt += 1

        if r.success:
            judge_verdict: str | None = "none"
        elif r.judge_label is not None:
            judge_verdict = r.judge_label
        else:
            judge_verdict = None  # judge pending

        if judge_verdict is None:
            continue
        n_labeled += 1
        if judge_verdict == r.ground_truth_label:
            label_correct += 1

    return JudgeMetrics(
        n_total=len(rollouts),
        n_with_ground_truth=n_with_gt,
        n_labeled=n_labeled,
        label_correct=label_correct,
    )


@dataclass(frozen=True)
class Cluster:
    """One cluster card in the synthesis view."""

    name: str
    rollouts: list[ScoredRollout]
    breakdown: dict[str, int] = field(default_factory=dict)


def load_scored_rollouts(mirror_root: Path) -> list[ScoredRollout]:
    """Read dispatch_log.jsonl and reconstruct one ScoredRollout per rollout_id."""
    log_path = mirror_root / DISPATCH_LOG
    if not log_path.exists():
        return []

    rollout_records: dict[str, dict[str, Any]] = {}
    judge_records: dict[str, dict[str, Any]] = {}

    for line in log_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        tool = rec.get("tool")
        args = rec.get("args", {})
        result = rec.get("result", {})
        rid = result.get("rollout_id") or args.get("rollout_id")
        if not rid:
            continue
        if tool == "rollout":
            rollout_records[rid] = {"args": args, "result": result}
        elif tool == "judge":
            judge_records[rid] = result

    rollouts_dir = mirror_root / "rollouts"
    out: list[ScoredRollout] = []
    for rid, rr in rollout_records.items():
        args = rr["args"]
        result = rr["result"]
        judge = judge_records.get(rid, {})

        judge_point = judge.get("point")
        knobs = {
            "injected_action_noise": float(args.get("injected_action_noise", 0.0)),
            "injected_premature_close": bool(args.get("injected_premature_close", False)),
            "injected_angle_deg": float(args.get("injected_angle_deg", 0.0)),
            "injected_grip_scale": float(args.get("injected_grip_scale", 1.0)),
        }
        host_video = rollouts_dir / f"{rid}.mp4"
        judge_frame_raw = judge.get("frame_index")
        out.append(
            ScoredRollout(
                rollout_id=rid,
                env_name=str(args.get("env_name", "")),
                policy_kind=str(args.get("policy_kind", "")),
                seed=int(args.get("seed", 0)),
                success=bool(result.get("success", False)),
                steps_taken=int(result.get("steps_taken", 0)),
                ground_truth_label=result.get("ground_truth_label"),
                injection_knobs=knobs,
                judge_label=judge.get("taxonomy_label"),
                judge_frame_index=int(judge_frame_raw) if judge_frame_raw is not None else None,
                judge_point=(
                    (int(judge_point[0]), int(judge_point[1])) if judge_point is not None else None
                ),
                judge_description=judge.get("description"),
                video_path_host=host_video if host_video.exists() else None,
            )
        )
    return out


def _condition_buckets(r: ScoredRollout) -> list[str]:
    """Return the condition labels this rollout falls into.

    A rollout can be in multiple buckets (e.g. high noise AND low grip).
    For pretrained, the only condition is the (env, policy) pair since we
    don't know what was unusual about that seed.
    """
    if r.policy_kind == "pretrained":
        return [f"pretrained · {r.env_name}"]
    buckets: list[str] = []
    knobs = r.injection_knobs
    if knobs["injected_action_noise"] >= _NOISE_PERTURBED_THRESHOLD:
        buckets.append(f"high action noise (≥{_NOISE_PERTURBED_THRESHOLD})")
    if knobs["injected_angle_deg"] > 0:
        buckets.append("angle perturbation (≠0°)")
    if knobs["injected_premature_close"]:
        buckets.append("premature gripper close")
    if knobs["injected_grip_scale"] < _GRIP_SCALE_PERTURBED_THRESHOLD:
        buckets.append(f"low grip scale (<{_GRIP_SCALE_PERTURBED_THRESHOLD})")
    if not buckets:
        buckets.append("clean (no perturbation)")
    return buckets


def cluster_by_label(rollouts: list[ScoredRollout]) -> list[Cluster]:
    """One cluster per judge taxonomy label that appears among failures.

    Within each cluster, the breakdown counts which condition bucket each
    rollout falls into — gives the diagnostic 'this label fires under these
    conditions' read.
    """
    failed = [r for r in rollouts if r.judged_failure and r.judge_label]
    by_label: dict[str, list[ScoredRollout]] = {}
    for r in failed:
        assert r.judge_label is not None
        by_label.setdefault(r.judge_label, []).append(r)

    clusters: list[Cluster] = []
    for label, members in sorted(by_label.items(), key=lambda kv: -len(kv[1])):
        breakdown: dict[str, int] = {}
        for r in members:
            for bucket in _condition_buckets(r):
                breakdown[bucket] = breakdown.get(bucket, 0) + 1
        clusters.append(Cluster(name=label, rollouts=members, breakdown=breakdown))
    return clusters


def cluster_by_condition(rollouts: list[ScoredRollout]) -> list[Cluster]:
    """One cluster per condition bucket that has any judged-failed members.

    Within each cluster, the breakdown counts judge labels — gives the
    'these conditions produce these failure modes' read.
    """
    failed = [r for r in rollouts if r.judged_failure]
    by_condition: dict[str, list[ScoredRollout]] = {}
    for r in failed:
        for bucket in _condition_buckets(r):
            by_condition.setdefault(bucket, []).append(r)

    clusters: list[Cluster] = []
    for condition, members in sorted(by_condition.items(), key=lambda kv: -len(kv[1])):
        breakdown: dict[str, int] = {}
        for r in members:
            label = r.judge_label or "(judge pending)"
            breakdown[label] = breakdown.get(label, 0) + 1
        clusters.append(Cluster(name=condition, rollouts=members, breakdown=breakdown))
    return clusters


def _scale_point_to_original(
    point_in_judge: tuple[int, int], original_w: int, original_h: int
) -> tuple[int, int]:
    """Scale (x, y) from the 2576-px judge grid back to the original mp4 frame."""
    long_orig = max(original_w, original_h)
    scale = long_orig / JUDGE_LONG_EDGE_PX
    return int(point_in_judge[0] * scale), int(point_in_judge[1] * scale)


def render_keyframe(rollout: ScoredRollout, out_path: Path) -> Path | None:
    """Render the keyframe the judge named, with a red dot at the judge's point.

    The keyframe is ALWAYS the frame at `judge_frame_index`. The red dot
    appears iff `judge_point` is non-None — on no-contact failures the
    judge abstains on pointing, and we honor that by leaving the frame
    un-annotated.

    For successful rollouts and for failures where the judge hasn't run
    yet, fall back to the middle of the video (for gallery display). No
    dot in those cases either — there's nothing to point at.

    Returns the written path, or None if the rollout has no usable video.
    """
    if rollout.video_path_host is None:
        return None
    frames = read_frames(rollout.video_path_host)
    if not frames:
        return None
    n = len(frames)

    if rollout.judge_frame_index is not None:
        idx = max(0, min(rollout.judge_frame_index, n - 1))
    else:
        idx = n // 2

    frame = frames[idx]
    img = Image.fromarray(frame)

    if rollout.judge_point is not None and rollout.judge_frame_index is not None:
        x, y = _scale_point_to_original(rollout.judge_point, img.width, img.height)
        draw = ImageDraw.Draw(img)
        r = POINT_DOT_RADIUS_PX
        draw.ellipse(
            (x - r, y - r, x + r, y + r),
            outline=(255, 40, 40),
            width=POINT_DOT_OUTLINE_WIDTH,
        )

    img = Image.fromarray(resize_long_edge(np_array_from(img), THUMBNAIL_LONG_EDGE_PX))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, format="PNG")
    return out_path


def np_array_from(img: Image.Image) -> Any:
    """Convert PIL.Image -> numpy ndarray (RGB uint8). Tiny helper, kept local."""
    import numpy as np

    return np.array(img)


def render_all_keyframes(rollouts: list[ScoredRollout], mirror_root: Path) -> dict[str, Path]:
    """Render keyframes for all rollouts that have a video. Returns rollout_id -> png path."""
    out_dir = mirror_root / KEYFRAMES_DIR_NAME
    paths: dict[str, Path] = {}
    for r in rollouts:
        out_path = out_dir / f"{r.rollout_id}.png"
        result = render_keyframe(r, out_path)
        if result is not None:
            paths[r.rollout_id] = result
    return paths
