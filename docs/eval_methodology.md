# Evaluation methodology

> How PolicyGrader frames what it measures and what it doesn't.

## Dual-population design

Every eval mixes two cohorts of rollouts. Both now run on **robosuite Lift**
(same task, same env, same camera) — this replaces an earlier design that ran
calibration on Lift and deployment on NutAssemblySquare, and which suffered
from cross-task calibration drift (precision/recall measured on Lift applied
to Nut was at best a floor, not a transferable number).

### Calibration cohort — scripted policy + injected output knobs

- **Policy.** `src/sim/scripted.py::ScriptedLiftPolicy` — a four-phase
  IK-style picker (approach → descend → grasp → lift) that reliably succeeds
  on default-placement Lift when no failures are injected.
- **Perturbation surface.** The policy's output actions. Four knobs map to
  four ground-truth labels (`src/sim/scripted.py::InjectedFailures.to_label`):
  - `action_noise ≥ 0.10` → `knock_object_off_table`
  - `approach_angle_offset_deg > 0` → `approach_miss`
  - `gripper_close_prematurely=True` → `approach_miss`
  - `grip_force_scale < 0.7` → `slip_during_lift`
- **Why the ground truth is trustworthy.** The knobs are implemented as
  explicit branches in the policy's `act()` — the injected failure is the
  policy's commanded behavior, not a hoped-for consequence. Integration tests
  in `tests/test_scripted_failure_injection.py::TestScriptedLiftIntegration`
  pin the knob → outcome mapping to the sim.
- **Placement.** `cube_xy_jitter_m = 0.0` always. The scripted policy is
  hand-tuned for the default ±3 cm placement range; widening it changes the
  probability that the scripted policy itself succeeds, which would muddy
  what the knobs measure. Dispatch rejects non-zero jitter on scripted
  rollouts (`src/agents/tools.py::_dispatch_rollout`).

### Deployment cohort — pretrained BC-RNN under environmental perturbation

- **Policy.** `robomimic` v0.3.0 BC-RNN trained on the Lift proficient-human
  dataset (`artifacts/checkpoints/lift_ph_low_dim.pth`). Verified in-env on
  our stack: **8/8 success at `cube_xy_jitter_m=0.0`** (see
  `scripts/smoke_pretrained_rollout.py`). The policy's forward pass is
  never touched — no output knobs, no post-hoc action manipulation.
- **Perturbation surface.** The environment, not the policy. We widen
  robosuite's `UniformRandomSampler` `x_range`/`y_range` on the cube's
  initial placement via `RolloutConfig.cube_xy_jitter_m`, implemented as
  a pre-reset attribute write on `env.placement_initializer` in
  `src/sim/adapter.py::_apply_cube_xy_jitter`. Default is ±3 cm (training
  distribution); elevated values push the cube to positions the policy
  never saw at training time.
- **Chosen value for the demo.** `cube_xy_jitter_m = 0.15` m (±15 cm, 5×
  the training range). Picked by running a sweep over
  {0.02, 0.05, 0.08, 0.12, 0.15, 0.20, 0.25, 0.30} m at 8 seeds each and
  selecting the smallest value yielding a 30-60% failure rate on the
  BC-RNN. Measured failure rates:

  | `cube_xy_jitter_m` | failure rate |
  | --- | --- |
  | 0.02 – 0.12 m | 0/8 (policy's generalization range) |
  | **0.15 m** | **3/8 (38%)** ← chosen |
  | 0.20 m | 4/8 (50%) |
  | 0.25 m | 6/8 (75%) |
  | 0.30 m | 7/8 (88%) |

- **Why this is real deployment evaluation, not a dressed-up injection.**
  The BC-RNN weights are frozen and its forward pass is untouched. Any
  failure we observe is the policy's own response to seeing an
  out-of-distribution initial condition — that's the methodologically
  meaningful signal a robotics team wants when they ask "how will this
  policy behave on real hardware where the cube isn't always at the
  nominal pose?".

## Judge trust: what calibration P/R means for deployment findings

Both cohorts run on Lift with identical camera, lighting, and frame-sampling
settings. The Pass-2 taxonomy label set a rollout can be judged against is
the same closed set (`docs/taxonomy.md`) regardless of cohort. Therefore the
per-label judge precision measured on calibration rollouts (where ground
truth is known by construction) **can** be attached as a first-order trust
estimate to deployment rollouts with the same label. The dashboard's Judge
Trust banner and per-cluster calibration chips both render on this
assumption.

This was not true under the prior cross-task design (Lift calibration → Nut
deployment). Collapsing the deployment task to Lift is the change that
unlocks this transfer.

### Residual gap: engineered vs natural failure distribution

Even with same-task calibration, scripted-injected failures look visually
distinct from the failures a real learned policy produces. The scripted
knocks and slips are abrupt and amplitude-stereotyped; the BC-RNN's
natural failures under OOD placement are subtler (wrong approach angles,
premature closures near the cube edge, etc.). The calibration P/R is
therefore still a *floor*, not a transferable number — if a human labeled
a held-out natural Nut set, the same judge would likely score a bit lower
on natural failures than on scripted ones.

Closing this fully requires a small human-labeled held-out set of deployment
rollouts — explicitly out of scope for this submission. The dashboard's
banner copy acknowledges this.

## Historical: robomimic 0.1 ↔ robosuite 1.5 drift (resolved by pinning to 1.4.1)

An earlier iteration of this repo ran against `robosuite>=1.5`. Robosuite
1.5 replaced the classical OSC_POSE controller with a composite-controller
abstraction, which re-scales and re-frames the ±0.05 m delta commands a
1.4-trained BC-RNN emits. Symptom: the policy saturated `+z` with the
gripper closed from step 0 and the arm rose away from the cube, yielding
0/16 success across {0.0, 0.05, 0.08, 0.12} m × 4 seeds. Verified in two
code paths — the direct `suite.make()` route and robomimic's own
`EnvUtils.create_env_from_metadata` route. Forcing `input_ref_frame="world"`
did not recover task success. See robomimic GitHub issues
[#259](https://github.com/ARISE-Initiative/robomimic/issues/259) and
[#283](https://github.com/ARISE-Initiative/robomimic/issues/283) for the
upstream context — Stanford publishes only 1.5-compatible *datasets*, not
re-trained checkpoints.

**Resolved by pinning `robosuite==1.4.1`** (see `requirements.txt`).
Robosuite 1.4.1 is pure-Python on top of the DeepMind mujoco bindings
(`mujoco>=3`) and installs cleanly on Python 3.12 macOS arm64. Our
scripted calibration policy uses nothing 1.5-specific; both cohorts run
on 1.4.1. The only code surfaces that moved were the controller-config
imports (`load_composite_controller_config` → `load_controller_config`)
and the pretrained shim (`_upgrade_legacy_controller` →
`_controller_passthrough`, now a no-op since the checkpoint's own
controller dict is native on 1.4).

## Scope of what we claim to measure

- **Calibration-cohort claim.** Judge precision and recall on scripted
  Lift failures, with Wilson 95% CIs. Per-label rates via the
  `src.metrics` module; confusion matrix on the dashboard. These are
  the headline calibration numbers.
- **Deployment-cohort claim.** The judge's label distribution over a
  real BC-RNN policy's failures on Lift under a ±15 cm placement
  perturbation. The policy succeeds 8/8 at `cube_xy_jitter_m=0.0` and
  fails 3/8 (38%) at 0.15 m — a clean out-of-distribution stress test.
  Each deployment finding carries its per-label calibration precision chip.
- **Out of scope.** Real-robot deployment, sim-to-real, multi-task
  generalization, clustering beyond the 1M-context single-pass synthesis
  the report writer does.
