# Failure Taxonomy

Closed set of failure labels the vision judge emits on the Lift task, and the
set the human labeler picks from during calibration. The judge picks exactly
one failure label per failed rollout; the human labeler has the same set plus
`none` (clean success — judge never emits this because it only runs on
sim-failures) and `ambiguous` (the video is unclear or cuts off).

`other` is an escape hatch for genuinely unrecognized modes. Using it for
borderline cases sinks precision.

The label set is kept in sync with `src/sim/scripted.py::FailureMode` by hand.

> Collapsed from the 3-mode outcome taxonomy on 2026-04-24; legacy labels are
> remapped at read time per `_LEGACY_LABEL_MAP` in `src/human_labels.py`.

## Labels

| Label | When to use | Visual cue |
| --- | --- | --- |
| `none` | Clean success — cube ends held above the success-height threshold. Labeler-only; the judge never emits this. | Cube visibly off the table at end of clip, gripper holding it. |
| `missed_approach` | Arm never established a grip on the cube. The gripper closes on empty air, OR stays closed throughout the descent (pushing / scratching the cube), OR passes by the cube without contact. The cube never leaves the table inside the gripper. | Gripper closes beside / above the cube, or skims past with fingers already shut. Cube never rises with the gripper. |
| `failed_grip` | Arm gripped the cube but lost it during the lift. There is at least one frame where the cube is above the table surface, held by closed gripper fingers, before falling. | Cube briefly airborne inside the gripper, then falls/slides free while the arm keeps rising. |
| `other` | Failure that genuinely doesn't match either of the above. Use sparingly. | (varies) |

The decisive cue between the two named modes: **did the cube ever leave the
table surface inside the gripper?** If yes → `failed_grip`. If no →
`missed_approach`.

## How the labels are used

- **Judge** picks one of the failure labels (all above except `none`) per
  failed rollout, plus a `frame_index` (earliest frame where the failure is
  visible) and `point` (pixel coordinate on that frame, or `null` when there
  is no gripper-cube contact to point at).
- **Human labeler** picks from the full set including `none` (for successes)
  plus `ambiguous` (video unclear). Human labels on the sampled calibration
  subset are the ground truth the judge is measured against; per-label
  precision/recall from that comparison decorates deployment findings.

## The axis: outcome, not mechanism

Prior taxonomies (a 10-label mechanism set, then a 3-label intermediate split
into `missed_approach` / `gripper_slipped` / `gripper_not_open`) tried to
separate failures by mechanism. Several pairs were below the pixel+frame-rate
resolution of the judge (scratch vs knock vs approach_miss hinge on
sub-second contact; slip vs premature_release on whether fingers visibly
splayed; closed-fingers-all-the-way-down vs no-contact-miss often look the
same from the `frontview` camera) and were the main source of multiclass
confusion.

The current 2-label axis is OUTCOME:

- did the policy **never establish a grip**? → `missed_approach` (subsumes
  the old `missed_approach`, `gripper_not_open`, knock, scratch, approach
  miss).
- did the policy **grip then lose** the cube? → `failed_grip` (subsumes the
  old `gripper_slipped` and `premature_release`).

This is the distinction robotics-ops actually cares about — mechanism is a
follow-up question. If finer granularity is needed later, re-split from data.

## Pass-wise usage (single-call judge)

The judge is a single Messages-API call per failed rollout (no two-pass
coarse/fine split). Pick the decisive frame and point in one CoT; the 2-label
axis lives inside that one prompt. See `src/vision/judge.py`.

## Binary success is taken from sim, not vision

`RolloutResult.success` is derived from `env._check_success()` plus a
post-hold re-verification (see `src/sim/adapter.py`): the cube must be above
the success threshold at the end of the post-success hold, not just
transiently during the rollout. This is how `failed_grip` rollouts are
correctly classified as sim-failures despite the cube briefly crossing the
success height during the carry phase.

The judge never overrides the sim success bit. It only runs on sim-failures,
and only emits a failure label.
