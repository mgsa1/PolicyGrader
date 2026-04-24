# Failure Taxonomy

Closed set of failure labels the vision judge emits on the Lift task, and the
set the human labeler picks from during calibration. The judge picks exactly
one failure label per failed rollout; the human labeler has the same set plus
`none` (clean success — judge never emits this because it only runs on
sim-failures) and `ambiguous` (the video is unclear or cuts off).

`other` is an escape hatch for genuinely unrecognized modes. Using it for
borderline cases sinks precision.

The label set is kept in sync with `src/sim/scripted.py::FailureMode` by hand.

## Labels

| Label | When to use | Visual cue |
| --- | --- | --- |
| `none` | Clean success — cube lifted to target height and held stably. Labeler-only; the judge never emits this. | Cube in the air, gripper fingers around it, arm stationary at lift height. |
| `missed_approach` | Policy never secured the cube. The fingers close on empty air, OR the gripper grazes / nudges / knocks the cube without grasping it. Use this whenever the rollout failed BEFORE a real grasp was established, regardless of whether there was contact. | Gripper closes beside / above the cube, or bumps it aside. Cube never lifts with the gripper. |
| `gripper_slipped` | Policy DID secure the cube (the cube is clearly inside the fingers, rising with the arm, at least briefly) and then lost it during the lift — fingers opening mid-lift or the cube sliding out of a weak grip. | Cube briefly airborne inside the gripper, then falls/slides free while the arm keeps rising. |
| `gripper_not_open` | Fingers are closed (pinched together) when the hand arrives at the cube. Because the fingers never opened, no grasp can form — the hand bumps or skims past the cube with closed fingers. | Gripper arrives at the cube with fingers already touching each other; no open-finger pose during descent. |
| `other` | Failure that genuinely doesn't match any of the above. Use sparingly. | (varies) |

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

The previous 10-label taxonomy (approach_miss / knock_object_off_table /
cube_scratched_but_not_moved / gripper_collision / slip_during_lift /
premature_release / gripper_never_opened / wrong_object_selected /
insertion_misalignment / other) tried to separate failures by mechanism.
Several pairs were below the pixel+frame-rate resolution of the judge
(scratch vs knock vs approach_miss often hinge on a sub-second contact; slip
vs premature_release on whether fingers visibly splayed) and were the main
source of multiclass confusion.

The new 3-label axis is OUTCOME:

- did the policy **never grasp** the cube? → `missed_approach`
- did the policy **grasp then lose** the cube? → `gripper_slipped`
- were the **fingers closed** during the approach so no grasp was possible?
  → `gripper_not_open`

This is the distinction robotics-ops actually cares about — mechanism is a
follow-up question. If finer granularity is needed later, re-split from data.

## Binary success is taken from sim, not vision

`RolloutResult.success` is derived from `env._check_success()` plus a
post-hold re-verification (see `src/sim/adapter.py`): the cube must be above
the success threshold at the end of the post-success hold, not just
transiently during the rollout. This is how `gripper_slipped` rollouts are
correctly classified as sim-failures despite the cube briefly crossing the
success height during the carry phase.

The judge never overrides the sim success bit. It only runs on sim-failures,
and only emits a failure label.
