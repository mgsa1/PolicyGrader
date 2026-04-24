# Failure Taxonomy

This is the closed set of failure labels the vision judge is allowed to emit.
The same set is the ground-truth label space for scripted-policy rollouts (see
`src/sim/scripted.py` — `FailureMode`). Keeping the two in sync by hand is a
deliberate choice; if a label is added here it must also be added to `FailureMode`.

The judge MUST pick exactly one label from this list when annotating a failed
rollout. "other" exists only as an escape hatch for genuinely unrecognized
modes — using it for fuzzy cases will sink precision.

**Not exercised by the current eval set:** `wrong_object_selected` and
`insertion_misalignment` were relevant to the prior NutAssemblySquare
deployment env (multi-object + insertion task). Post scope-cut to Lift-only
they're unreachable from any scenario we run — Lift has one object and no
placement. They remain in the closed set as escape-hatch labels the judge
may still emit if it ever sees something it can't otherwise classify, and
so the `FailureMode` enum stays stable across any future multi-task
re-expansion.

## Labels

| Label | When to use | Visual cue |
| --- | --- | --- |
| `none` | Rollout succeeded — pick was completed. Used as Pass-1 verdict, not as a Pass-2 annotation. | Object lifted to target height and stable. |
| `approach_miss` | The arm reaches a position where the gripper cannot grasp the object. Includes both "missed by a wide margin" and "closed gripper before reaching object" — both look like "gripper closes on air, never makes contact". | Gripper closes but object does not move. Gripper tips clearly offset from object center, OR gripper closes while still in air well above object. |
| `premature_release` | The gripper grasps the object successfully but releases it before the lift target is reached. Object falls back near the grasp pose. | Object briefly rises with gripper, then drops while arm continues upward. |
| `slip_during_lift` | The gripper has hold of the object at lift start but loses contact during the lift motion. The gripper APPEARS to be holding (fingers around the object) but the object slides out. Distinguish from premature_release: in slip the gripper does not visibly open; in premature_release it does. | Object descends along the gripper fingers as the arm rises. |
| `knock_object_off_table` | The arm contacts the object hard enough to displace it (often laterally), so the object is no longer in graspable position when the gripper closes. Often happens during approach. | Object visibly moves before any grasp attempt — slid, tipped, or pushed off the table. |
| `wrong_object_selected` | Multiple objects in the scene; the policy targets and grasps the incorrect one. Only relevant for envs with multiple manipulation targets (e.g. NutAssemblySquare with both nuts visible). | Gripper successfully grasps an object but it is not the intended target. |
| `insertion_misalignment` | Pick succeeded but the subsequent placement / insertion failed because the object orientation or position was wrong relative to the receptacle. Specific to insertion / assembly tasks. | Object is held above the target receptacle, but the placement attempt fails — object rotates wrong, lands on lip, or rebounds. |
| `gripper_collision` | The gripper or arm physically collides with the environment (table, wall, fixture) hard enough to interrupt the trajectory. Distinct from `knock_object_off_table` because the collision target is the environment, not the object. | Visible contact with non-object geometry; arm jolts, recoils, or freezes. |
| `other` | A failure occurred but does not match any of the above. Use sparingly — prefer the closest-fit specific label. | (varies) |

## Pass-1 vs Pass-2

- **Pass 1 (coarse, ~768 px):** binary `pass | fail` plus, on fail, a frame-range
  estimate `[start, end]` covering when the failure became visible. No
  taxonomy label is required at Pass 1 — speed and recall matter more than
  resolution at this stage.
- **Pass 2 (fine, 2576 px):** only runs on rollouts where Pass 1 said `fail`.
  Emits `{taxonomy_label, point: [x, y], description}` where `point` is a
  pixel coordinate (in the 2576-px frame's coordinate system) on the visual
  evidence — the object, the offending finger, the misalignment axis. Pick
  the single most diagnostic frame from the failure range.
