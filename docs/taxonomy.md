# Failure Taxonomy

This is the closed set of failure labels the vision judge is allowed to emit,
and the same closed set the human labeler picks from during the calibration
phase. The judge MUST pick exactly one label from this list per failed
rollout; the human labeler additionally has a `success` option (a clean pick)
and an `ambiguous` option (can't tell from the video).

"other" exists only as an escape hatch for genuinely unrecognized modes — using
it for fuzzy cases sinks precision.

The label set is kept in sync with `src/sim/scripted.py::FailureMode` by hand;
adding a label here requires adding it there too, plus updating the judge
prompt in `src/vision/judge.py`.

## Labels

| Label | When to use | Visual cue |
| --- | --- | --- |
| `none` | Clean success — object lifted to target height and held stably. Not emitted by the judge on failed rollouts (sim owns the success bit); only used on the human-labeling side to confirm a clean rollout. | Object clearly in the air, gripper fingers around it, arm stationary at lift height. |
| `approach_miss` | Gripper arrives at a pose where it cannot grasp the object — offset too far to the side, too high, or otherwise geometrically wrong. Gripper is open during approach. | Gripper closes on air; fingers visibly offset from object center OR still well above it. |
| `gripper_never_opened` | Gripper is closed when it should be open during approach or descend. Because the fingers are already together, they cannot straddle the object — the hand either pushes against or skims past the cube without ever being in a grasp-capable configuration. Distinct from `approach_miss` (open fingers that miss) and `gripper_collision` (hard impact). | Gripper arrives at cube with fingers already touching each other. |
| `cube_scratched_but_not_moved` | Brief grazing contact between gripper and object during approach: the cube is grazed or nudged by <1 cm but stays in place, and the rollout still fails to pick it up. Near-miss that is visually distinct from both a clean approach_miss (no contact) and knock_object_off_table (displaced >1 cm). | Cube twitches, spins in place, or wobbles but stays on its original footprint. Gripper continues past. |
| `premature_release` | Gripper grasps the object successfully but releases it before lift completes. Fingers visibly open mid-lift. | Object briefly rises with gripper, then drops while arm continues upward; gripper fingers splay. |
| `slip_during_lift` | Gripper has hold of the object at lift start but loses contact during the lift motion — the fingers DO NOT visibly open. The object slides down along the fingers under gravity because the grip is too weak. | Object descends along the gripper fingers as the arm rises; fingers stay pinched together. |
| `knock_object_off_table` | Gripper or arm contacts the object hard enough to displace it >1 cm (often laterally), so the object is no longer in graspable position by the time the gripper tries to close. Often happens early, during approach. | Object visibly slides, tips, rolls, or is pushed off the table. |
| `gripper_collision` | Gripper or arm collides with the environment (table, wall, fixture) hard enough to interrupt the trajectory. Distinct from `knock_object_off_table` because the collision target is non-object. | Visible contact with non-object geometry; arm jolts, recoils, or freezes. |
| `wrong_object_selected` | Scene has multiple manipulation targets; the policy grasps the incorrect one. Not reachable on Lift (single object); retained in the closed set for future multi-task re-expansion. | Gripper successfully grasps an object but it is not the intended target. |
| `insertion_misalignment` | Pick succeeded but the subsequent placement/insertion failed because the object orientation or position was wrong relative to the receptacle. Not reachable on Lift; retained for future envs. | Object is held above the target but placement fails — rotates wrong, lands on lip, rebounds. |
| `other` | Failure occurred but does not match any above. Use sparingly. | (varies) |

## How the labels are used

- **Judge** emits one of the failure labels (all above except `none`) as part
  of a single-call chain-of-thought pass over the rollout video. The judge
  additionally returns `frame_index` (the earliest frame where the failure is
  visible) and `point` (pixel coordinate on that frame, or `null` if no
  cube-gripper contact is visible to point at).
- **Human labeler**, during the calibration phase, picks one label from the
  full set including `none` (for successes) plus an `ambiguous` escape hatch
  (the video is unclear or cuts off before the failure mode is visible).
  Human labels on the sampled calibration subset are the ground truth the
  judge is measured against; the per-label precision/recall from this
  comparison is what decorates deployment findings.

## Binary success is taken from sim, not vision

`RolloutResult.success` is derived from `env._check_success()` plus a
post-hold re-verification (see `src/sim/adapter.py`): the cube must be above
the success threshold at the end of the post-success hold, not just
transiently during the rollout. This is how `slip_during_lift` rollouts are
correctly classified as sim-failures despite the cube briefly crossing the
success height during the carry phase.

The judge never overrides the sim success bit. It only runs on sim-failures,
and only emits a failure label.
