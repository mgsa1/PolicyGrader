"""Failure-synthesis layer for the Gradio UI (and Remotion later).

Reads `mirror_root/dispatch_log.jsonl` (which the orchestrator-side dispatch
appends to on every rollout/coarse/fine call) and turns it into clusters of
related failures with keyframe evidence. Two grouping modes:

  1. by_label   — one cluster per Pass-2 taxonomy_label that appears.
                  "8 failures judged approach_miss" + 8 keyframes.
  2. by_condition — one cluster per scripted-knob condition that's perturbed
                    plus one per (env, policy) combination for pretrained
                    rollouts. "3 failures with angle_offset>0" + 3 keyframes.

Each cluster card shows: name + count + % of total failures + breakdown by
the OTHER axis (e.g., a by_condition cluster shows label distribution
within it) + grid of keyframes. Keyframes are the failure-range midpoint
frame from the original mp4, with a red dot drawn at the Pass-2 `point`
coordinate (mapped back from the 2576-px frame the judge saw).

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
from src.vision.fine_pass import FINE_LONG_EDGE_PX
from src.vision.frames import read_frames, resize_long_edge, sample_indices

KEYFRAMES_DIR_NAME = "keyframes"
THUMBNAIL_LONG_EDGE_PX = 384
POINT_DOT_RADIUS_PX = 16
POINT_DOT_OUTLINE_WIDTH = 4

# ---- Population palette ---------------------------------------------------------
# The dashboard distinguishes two populations of rollouts everywhere:
#   - Calibration: scripted policy + injected failure (ground truth known)
#   - Deployment: pretrained / real policy (no ground truth label)
# These two colors thread through every chip, banner, and accent so a viewer
# can tell at a glance which population something belongs to. NOT the phase
# colors (those mean planner/rollout/judge/report) — different axis.
CALIBRATION_COLOR = "#f59e0b"  # amber
DEPLOYMENT_COLOR = "#38bdf8"  # steel blue
CALIBRATION_LABEL = "Calibration"
DEPLOYMENT_LABEL = "Deployment"


# ---- Tiny shared HTML helpers -----------------------------------------------------
# Both src/ui/app.py and src/ui/metrics_view.py render keyframe + mp4 paths and
# want a consistent "copyable path" treatment. Defined here so they can share.


def html_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def paperclip_button(
    path: object,
    *,
    tooltip: str = "Copy path",
    anchor: str | None = None,
    inline: bool = False,
) -> str:
    """Small clipboard button (📎). Briefly shows ✓ on click.

    `anchor` is a position keyword (top-right, top-left, bottom-right,
    bottom-left). If set, the button is absolutely positioned for overlaying
    on a thumbnail — the immediate parent must be position:relative.
    `inline=True` produces a non-overlay version that flows in normal layout
    (used next to gr.Video / gr.Gallery headers where we can't overlay).
    """
    p_str = str(path)
    js_safe = p_str.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")
    title = html_escape(f"{tooltip}: {p_str}")
    if anchor and not inline:
        anchor_css = {
            "top-right": "position:absolute;top:6px;right:6px;",
            "top-left": "position:absolute;top:6px;left:6px;",
            "bottom-right": "position:absolute;bottom:6px;right:6px;",
            "bottom-left": "position:absolute;bottom:6px;left:6px;",
        }.get(anchor, "position:absolute;top:6px;right:6px;")
    else:
        anchor_css = "display:inline-block;vertical-align:middle;margin-left:6px;"
    return (
        f'<button onclick="event.preventDefault();event.stopPropagation();'
        f"navigator.clipboard.writeText('{js_safe}');"
        f"this.textContent='✓';"
        f"setTimeout(()=>this.textContent='📎',900)\" "
        f"title='{title}' "
        f"style='{anchor_css}"
        f"background:rgba(15,23,42,0.85);color:#f1f5f9;"
        f"border:1px solid rgba(255,255,255,0.22);border-radius:4px;"
        f"padding:2px 7px;cursor:pointer;font-size:13px;line-height:1;"
        f"font-family:-apple-system,system-ui,sans-serif;"
        f"backdrop-filter:blur(4px);'>📎</button>"
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
    """One rollout's full record: config + outcome + judge verdict."""

    rollout_id: str
    env_name: str
    policy_kind: str
    seed: int
    success: bool
    steps_taken: int
    ground_truth_label: str | None
    injection_knobs: dict[str, Any]
    pass1_verdict: str | None  # "pass" / "fail" / None if no coarse run
    pass1_failure_frame_range: tuple[int, int] | None
    pass1_coarse_total_frames: int | None
    pass2_label: str | None
    pass2_point: tuple[int, int] | None
    pass2_description: str | None
    video_path_host: Path | None  # local mp4 path on host

    @property
    def is_failure(self) -> bool:
        """True if the rollout did not succeed (env's ground truth)."""
        return not self.success

    @property
    def judged_failure(self) -> bool:
        """True if the judge said this rollout failed (Pass-1 = fail)."""
        return self.pass1_verdict == "fail"

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
        color = CALIBRATION_COLOR
        kind_label = CALIBRATION_LABEL
        sub = f"expected: {rollout.ground_truth_label}"
    else:
        color = DEPLOYMENT_COLOR
        kind_label = DEPLOYMENT_LABEL
        policy = "BC-RNN" if rollout.policy_kind == "pretrained" else rollout.policy_kind
        sub = f"{policy} · no GT"
    sub_html = (
        ""
        if compact
        else (
            f"<span style='color:#94a3b8;font-size:10px;margin-left:6px;'>{html_escape(sub)}</span>"
        )
    )
    return (
        "<span style='display:inline-flex;align-items:center;gap:4px;"
        f"padding:2px 8px;background:{color}22;color:{color};border-radius:10px;"
        f"font-size:10px;font-weight:700;text-transform:uppercase;"
        "letter-spacing:1px;font-family:-apple-system,system-ui,sans-serif;'>"
        f"<span style='font-size:8px;'>●</span>{kind_label}{sub_html}"
        "</span>"
    )


def cohort_split(rollouts: list[ScoredRollout]) -> tuple[int, int]:
    """Return (n_calibration, n_deployment)."""
    n_cal = sum(1 for r in rollouts if r.population == "calibration")
    return n_cal, len(rollouts) - n_cal


@dataclass(frozen=True)
class JudgeMetrics:
    """Pass-1 binary + Pass-2 label numbers, computed from dispatch_log_jsonl."""

    n_total: int
    n_with_ground_truth: int  # rollouts where env knows the truth (scripted)
    pass1_tp: int  # judge=fail, env=fail
    pass1_fp: int  # judge=fail, env=success
    pass1_fn: int  # judge=pass, env=fail
    pass1_tn: int  # judge=pass, env=success
    pass2_correct: int  # pass2_label == ground_truth_label, only on labeled rows
    pass2_labeled: int  # rollouts that got a Pass-2 label AND have ground truth

    @property
    def pass1_precision(self) -> float:
        denom = self.pass1_tp + self.pass1_fp
        return self.pass1_tp / denom if denom else 0.0

    @property
    def pass1_recall(self) -> float:
        denom = self.pass1_tp + self.pass1_fn
        return self.pass1_tp / denom if denom else 0.0

    @property
    def pass2_label_accuracy(self) -> float | None:
        if self.pass2_labeled == 0:
            return None
        return self.pass2_correct / self.pass2_labeled


def compute_metrics(rollouts: list[ScoredRollout]) -> JudgeMetrics:
    """Compute Pass-1 binary precision/recall + Pass-2 label accuracy."""
    tp = fp = fn = tn = 0
    pass2_correct = 0
    pass2_labeled = 0
    n_with_gt = 0

    for r in rollouts:
        if r.pass1_verdict is None:
            continue  # judge never ran; skip
        env_failed = not r.success
        judge_failed = r.judged_failure
        if env_failed and judge_failed:
            tp += 1
        elif not env_failed and judge_failed:
            fp += 1
        elif env_failed and not judge_failed:
            fn += 1
        else:
            tn += 1

        if r.ground_truth_label is not None and r.ground_truth_label != "":
            n_with_gt += 1
            if r.pass2_label is not None:
                pass2_labeled += 1
                if r.pass2_label == r.ground_truth_label:
                    pass2_correct += 1

    return JudgeMetrics(
        n_total=len(rollouts),
        n_with_ground_truth=n_with_gt,
        pass1_tp=tp,
        pass1_fp=fp,
        pass1_fn=fn,
        pass1_tn=tn,
        pass2_correct=pass2_correct,
        pass2_labeled=pass2_labeled,
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
    coarse_records: dict[str, dict[str, Any]] = {}
    fine_records: dict[str, dict[str, Any]] = {}

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
        elif tool == "coarse":
            coarse_records[rid] = result
        elif tool == "fine":
            fine_records[rid] = result

    rollouts_dir = mirror_root / "rollouts"
    out: list[ScoredRollout] = []
    for rid, rr in rollout_records.items():
        args = rr["args"]
        result = rr["result"]
        coarse = coarse_records.get(rid, {})
        fine = fine_records.get(rid, {})

        pass1_range = coarse.get("failure_frame_range")
        pass2_point = fine.get("point")
        knobs = {
            "injected_action_noise": float(args.get("injected_action_noise", 0.0)),
            "injected_premature_close": bool(args.get("injected_premature_close", False)),
            "injected_angle_deg": float(args.get("injected_angle_deg", 0.0)),
            "injected_grip_scale": float(args.get("injected_grip_scale", 1.0)),
        }
        host_video = rollouts_dir / f"{rid}.mp4"
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
                pass1_verdict=coarse.get("verdict"),
                pass1_failure_frame_range=(
                    (int(pass1_range[0]), int(pass1_range[1])) if pass1_range is not None else None
                ),
                pass1_coarse_total_frames=coarse.get("coarse_total_frames"),
                pass2_label=fine.get("taxonomy_label"),
                pass2_point=(
                    (int(pass2_point[0]), int(pass2_point[1])) if pass2_point is not None else None
                ),
                pass2_description=fine.get("description"),
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
    """One cluster per Pass-2 label that appears among judged-failed rollouts.

    Within each cluster, the breakdown counts which condition bucket each
    rollout falls into — gives the diagnostic 'this label fires under these
    conditions' read.
    """
    failed = [r for r in rollouts if r.judged_failure and r.pass2_label]
    by_label: dict[str, list[ScoredRollout]] = {}
    for r in failed:
        assert r.pass2_label is not None
        by_label.setdefault(r.pass2_label, []).append(r)

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

    Within each cluster, the breakdown counts Pass-2 labels — gives the
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
            label = r.pass2_label or "(no Pass-2)"
            breakdown[label] = breakdown.get(label, 0) + 1
        clusters.append(Cluster(name=condition, rollouts=members, breakdown=breakdown))
    return clusters


def _midpoint_original_frame_idx(
    coarse_range: tuple[int, int], coarse_total: int, original_total: int
) -> int:
    """Map the midpoint of a coarse-pass failure range back to original-mp4 indices."""
    coarse_indices = sample_indices(original_total, coarse_total)
    if not coarse_indices:
        return original_total // 2
    mid = (coarse_range[0] + coarse_range[1]) // 2
    mid = max(0, min(mid, len(coarse_indices) - 1))
    return coarse_indices[mid]


def _scale_point_to_original(
    point_in_fine: tuple[int, int], original_w: int, original_h: int
) -> tuple[int, int]:
    """Scale a (x, y) coordinate from the FINE_LONG_EDGE_PX-resized frame back to original."""
    long_orig = max(original_w, original_h)
    scale = long_orig / FINE_LONG_EDGE_PX
    return int(point_in_fine[0] * scale), int(point_in_fine[1] * scale)


def render_keyframe(rollout: ScoredRollout, out_path: Path) -> Path | None:
    """Extract the failure-midpoint frame and overlay a red dot at Pass-2 point.

    Returns the written path, or None if the rollout has no usable video.
    Caches by writing to `out_path`; caller decides whether to overwrite.
    """
    if rollout.video_path_host is None:
        return None
    frames = read_frames(rollout.video_path_host)
    if not frames:
        return None
    n = len(frames)

    if rollout.pass1_failure_frame_range is not None and rollout.pass1_coarse_total_frames:
        idx = _midpoint_original_frame_idx(
            rollout.pass1_failure_frame_range, rollout.pass1_coarse_total_frames, n
        )
    else:
        idx = n // 2
    idx = max(0, min(idx, n - 1))

    frame = frames[idx]
    img = Image.fromarray(frame)

    if rollout.pass2_point is not None:
        x, y = _scale_point_to_original(rollout.pass2_point, img.width, img.height)
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
