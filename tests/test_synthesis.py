"""Tests for src.ui.synthesis cluster math. No PIL/video required."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.agents.tools import DISPATCH_LOG
from src.ui.synthesis import (
    ScoredRollout,
    cluster_by_condition,
    cluster_by_label,
    compute_metrics,
    load_scored_rollouts,
)


def _scored(
    rid: str,
    *,
    success: bool = False,
    pass1: str | None = "fail",
    pass2_label: str | None = "approach_miss",
    knobs: dict[str, Any] | None = None,
    policy_kind: str = "scripted",
    env_name: str = "Lift",
    ground_truth_label: str | None = None,
) -> ScoredRollout:
    base_knobs = {
        "injected_action_noise": 0.0,
        "injected_premature_close": False,
        "injected_angle_deg": 0.0,
        "injected_grip_scale": 1.0,
    }
    if knobs:
        base_knobs.update(knobs)
    return ScoredRollout(
        rollout_id=rid,
        env_name=env_name,
        policy_kind=policy_kind,
        seed=0,
        success=success,
        steps_taken=42,
        ground_truth_label=ground_truth_label,
        injection_knobs=base_knobs,
        pass1_verdict=pass1,
        pass1_failure_frame_range=(3, 13) if pass1 == "fail" else None,
        pass1_coarse_total_frames=14 if pass1 == "fail" else None,
        pass2_label=pass2_label,
        pass2_point=(100, 200) if pass2_label else None,
        pass2_description="x" if pass2_label else None,
        video_path_host=None,
    )


class TestClusterByLabel:
    def test_empty(self) -> None:
        assert cluster_by_label([]) == []

    def test_excludes_passes(self) -> None:
        # Pass-1 = pass should not appear in any cluster.
        rollouts = [
            _scored("a", pass1="pass", pass2_label=None, success=True),
            _scored("b", pass1="fail", pass2_label="slip_during_lift"),
        ]
        clusters = cluster_by_label(rollouts)
        assert len(clusters) == 1
        assert clusters[0].name == "slip_during_lift"
        assert [r.rollout_id for r in clusters[0].rollouts] == ["b"]

    def test_one_cluster_per_label_sorted_by_size(self) -> None:
        rollouts = [
            _scored("a", pass2_label="approach_miss"),
            _scored("b", pass2_label="approach_miss"),
            _scored("c", pass2_label="slip_during_lift"),
            _scored("d", pass2_label="approach_miss"),
        ]
        clusters = cluster_by_label(rollouts)
        assert [c.name for c in clusters] == ["approach_miss", "slip_during_lift"]
        assert len(clusters[0].rollouts) == 3
        assert len(clusters[1].rollouts) == 1

    def test_breakdown_counts_conditions_within_label(self) -> None:
        rollouts = [
            _scored("a", pass2_label="approach_miss", knobs={"injected_angle_deg": 20}),
            _scored("b", pass2_label="approach_miss", knobs={"injected_angle_deg": 15}),
            _scored("c", pass2_label="approach_miss"),  # clean knobs
        ]
        clusters = cluster_by_label(rollouts)
        assert len(clusters) == 1
        bd = clusters[0].breakdown
        # Two with angle perturbation, one clean.
        assert bd.get("angle perturbation (≠0°)") == 2
        assert bd.get("clean (no perturbation)") == 1


class TestClusterByCondition:
    def test_empty(self) -> None:
        assert cluster_by_condition([]) == []

    def test_pretrained_groups_by_env_policy(self) -> None:
        rollouts = [
            _scored("a", policy_kind="pretrained", env_name="Lift"),
            _scored("b", policy_kind="pretrained", env_name="Lift"),
        ]
        clusters = cluster_by_condition(rollouts)
        assert len(clusters) == 1
        assert clusters[0].name == "pretrained · Lift"
        assert len(clusters[0].rollouts) == 2

    def test_one_rollout_can_appear_in_multiple_condition_clusters(self) -> None:
        # A rollout perturbing both noise AND grip_scale should appear in
        # both buckets.
        rollouts = [
            _scored(
                "multi",
                pass2_label="approach_miss",
                knobs={"injected_action_noise": 0.15, "injected_grip_scale": 0.3},
            )
        ]
        clusters = cluster_by_condition(rollouts)
        names = sorted(c.name for c in clusters)
        assert "high action noise (≥0.1)" in names
        assert "low grip scale (<0.7)" in names

    def test_breakdown_counts_labels_within_condition(self) -> None:
        rollouts = [
            _scored(
                "a", pass2_label="knock_object_off_table", knobs={"injected_action_noise": 0.15}
            ),
            _scored(
                "b", pass2_label="knock_object_off_table", knobs={"injected_action_noise": 0.15}
            ),
            _scored("c", pass2_label="approach_miss", knobs={"injected_action_noise": 0.15}),
        ]
        clusters = cluster_by_condition(rollouts)
        # All three are high-noise.
        noise_cluster = next(c for c in clusters if "noise" in c.name)
        assert len(noise_cluster.rollouts) == 3
        assert noise_cluster.breakdown["knock_object_off_table"] == 2
        assert noise_cluster.breakdown["approach_miss"] == 1


class TestComputeMetrics:
    def test_perfect_pass1(self) -> None:
        # 2 clean (env=success, judge=pass) + 2 fail (env=fail, judge=fail).
        rollouts = [
            _scored("c0", success=True, pass1="pass", pass2_label=None),
            _scored("c1", success=True, pass1="pass", pass2_label=None),
            _scored("f0", success=False, pass1="fail", pass2_label="approach_miss"),
            _scored("f1", success=False, pass1="fail", pass2_label="slip_during_lift"),
        ]
        m = compute_metrics(rollouts)
        assert m.pass1_tp == 2
        assert m.pass1_fp == 0
        assert m.pass1_fn == 0
        assert m.pass1_tn == 2
        assert m.pass1_precision == 1.0
        assert m.pass1_recall == 1.0

    def test_pass1_false_positives(self) -> None:
        # Judge cried wolf on a clean rollout.
        rollouts = [
            _scored("c0", success=True, pass1="fail", pass2_label="approach_miss"),
            _scored("f0", success=False, pass1="fail", pass2_label="approach_miss"),
        ]
        m = compute_metrics(rollouts)
        assert m.pass1_tp == 1
        assert m.pass1_fp == 1
        assert m.pass1_precision == 0.5
        assert m.pass1_recall == 1.0

    def test_pass2_label_accuracy(self) -> None:
        rollouts = [
            _scored(
                "f0",
                success=False,
                pass1="fail",
                pass2_label="approach_miss",
                ground_truth_label="approach_miss",  # match
            ),
            _scored(
                "f1",
                success=False,
                pass1="fail",
                pass2_label="approach_miss",
                ground_truth_label="slip_during_lift",  # mismatch
            ),
        ]
        m = compute_metrics(rollouts)
        assert m.pass2_labeled == 2
        assert m.pass2_correct == 1
        assert m.pass2_label_accuracy == 0.5

    def test_pass2_accuracy_none_when_no_ground_truth(self) -> None:
        # All rollouts pretrained — no ground truth label.
        rollouts = [
            _scored("p0", success=False, pass1="fail", pass2_label="approach_miss"),
        ]
        m = compute_metrics(rollouts)
        assert m.pass2_labeled == 0
        assert m.pass2_label_accuracy is None


class TestLoadScoredRollouts:
    def test_no_log_returns_empty(self, tmp_path: Path) -> None:
        assert load_scored_rollouts(tmp_path) == []

    def test_joins_rollout_coarse_fine_by_id(self, tmp_path: Path) -> None:
        log = tmp_path / DISPATCH_LOG
        records = [
            {
                "ts": 1.0,
                "tool": "rollout",
                "args": {
                    "rollout_id": "r1",
                    "env_name": "Lift",
                    "policy_kind": "scripted",
                    "seed": 0,
                    "max_steps": 200,
                    "injected_action_noise": 0.15,
                },
                "result": {
                    "rollout_id": "r1",
                    "success": False,
                    "steps_taken": 200,
                    "video_path": "/memories/rollouts/r1.mp4",
                    "ground_truth_label": "knock_object_off_table",
                },
            },
            {
                "ts": 2.0,
                "tool": "coarse",
                "args": {"rollout_id": "r1", "video_path": "/memories/rollouts/r1.mp4"},
                "result": {
                    "rollout_id": "r1",
                    "verdict": "fail",
                    "failure_frame_range": [3, 12],
                    "coarse_total_frames": 14,
                },
            },
            {
                "ts": 3.0,
                "tool": "fine",
                "args": {"rollout_id": "r1"},
                "result": {
                    "rollout_id": "r1",
                    "taxonomy_label": "knock_object_off_table",
                    "point": [400, 250],
                    "description": "cube knocked aside",
                },
            },
        ]
        log.write_text("\n".join(json.dumps(r) for r in records))

        out = load_scored_rollouts(tmp_path)
        assert len(out) == 1
        r = out[0]
        assert r.rollout_id == "r1"
        assert r.injection_knobs["injected_action_noise"] == pytest.approx(0.15)
        assert r.pass1_verdict == "fail"
        assert r.pass1_failure_frame_range == (3, 12)
        assert r.pass2_label == "knock_object_off_table"
        assert r.pass2_point == (400, 250)
