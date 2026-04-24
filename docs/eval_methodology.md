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
  dataset (`artifacts/checkpoints/lift_ph_low_dim.pth`, reported ~100%
  success on training distribution in robosuite 1.4). The policy's forward
  pass is never touched — no output knobs, no post-hoc action manipulation.
- **Perturbation surface.** The environment, not the policy. We widen
  robosuite's `UniformRandomSampler` `x_range`/`y_range` on the cube's
  initial placement via `RolloutConfig.cube_xy_jitter_m`, implemented as
  a pre-reset attribute write on `env.placement_initializer` in
  `src/sim/adapter.py::_apply_cube_xy_jitter`. Default is ±3 cm (training
  distribution); elevated values push the cube to positions the policy
  never saw at training time.
- **Chosen value for the demo.** `cube_xy_jitter_m = 0.08` m (i.e., ±8 cm,
  ~2.7× the training range). Verified to actually spread cube positions:
  across 15 seeds, the default range spans roughly x∈[-0.03, +0.03] and
  the 0.08 override spans x∈[-0.08, +0.07].
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

## Known limitation: robomimic 0.1 ↔ robosuite 1.5 drift

The Lift BC-RNN checkpoint was trained under robosuite 1.4.x. Between that
version and 1.5 (the version we ship against, required by the rest of our
stack for Python 3.12 + MuJoCo compatibility), robosuite changed the default
reference frame for OSC_POSE delta actions from WORLD to BASE, and may have
reordered observables. The net effect is that **the BC-RNN consistently
fails under robosuite 1.5 regardless of cube placement**: in a sweep of
{0.00, 0.05, 0.08, 0.12} m × 4 seeds, 0 of 16 rollouts succeeded.

This was verified two ways:
1. Direct `suite.make()` + `RobomimicPolicy` path used by the adapter.
2. Via robomimic's own `EnvUtils.create_env_from_metadata` path (with a
   `mujoco_py` stub since robomimic 0.3.0's env adapter imports the dead
   package). Same 0% success.

Adding `input_ref_frame="world"` to the migrated controller config was
tried and did not recover task success on either Lift or Square — so the
shim in `src/sim/pretrained.py::_upgrade_legacy_controller` leaves the
library defaults alone.

**Demo implication.** The deployment cohort's failure rate is ~100%
regardless of `cube_xy_jitter_m`. What `cube_xy_jitter_m` still buys us is
**visual diversity in the failure modes** — a cube that starts at
(+8 cm, +8 cm) produces a visually different failure than one starting at
the origin, which means the vision judge gets a richer label distribution
to work with. But we cannot claim "placement perturbation caused this
failure rate to rise" — the floor failure rate is the drift, not the
perturbation.

**What this does NOT affect.** The calibration cohort, the judge
calibration numbers, and the dual-population dashboard scaffolding are all
independent of this drift — those run the scripted policy, which is built
directly against robosuite 1.5's controllers and does succeed reliably in
the clean configuration. The judge trust story holds.

**Out-of-scope fixes.**
- Downgrading robosuite to 1.4 — breaks the rest of our stack.
- Retraining the BC-RNN against robosuite 1.5 — explicitly a non-goal
  (claude.md §1: "We evaluate, we do not train.").
- Using the `lift_mh_low_dim` checkpoint as a fallback — verified via
  the model zoo docs and HEAD probes that this checkpoint is not
  published (see conversation notes in the branch history).

## Scope of what we claim to measure

- **Calibration-cohort claim.** Judge precision and recall on scripted
  Lift failures, with Wilson 95% CIs. Per-label rates via the
  `src.metrics` module; confusion matrix on the dashboard. These are
  the headline calibration numbers.
- **Deployment-cohort claim.** The judge's label distribution over a
  real BC-RNN policy's failures on Lift under a ±8 cm placement
  perturbation (and, in this release, under robosuite 1.5 drift — see
  above). Each deployment finding carries its per-label calibration
  precision chip. We do not claim a failure *rate* for this cohort —
  the rate is dominated by the drift floor.
- **Out of scope.** Real-robot deployment, sim-to-real, multi-task
  generalization, clustering beyond the 1M-context single-pass synthesis
  the report writer does.
