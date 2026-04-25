# CLAUDE.md — Embodied Eval Orchestrator

> Project memory for Claude Code. Keep this file lean and high-signal.
> Put anything that only matters sometimes in `docs/` and reference with `@docs/filename.md`.

---

## 1. North Star

**Positioning (also the README one-liner):** An agentic system that runs and analyzes robot manipulation policy evaluations end-to-end, reducing manual eval-video review from hours to minutes.

Submitted to the Anthropic Opus 4.7 Hackathon.

**How it works.** Describe an evaluation goal in English → an Opus 4.7 Managed Agent designs a test suite, runs rollouts in simulation, **pauses for the human to label a sampled subset of calibration rollouts** from a closed taxonomy, then watches each failed rollout in a single dense-frame chain-of-thought pass (~30 frames at 2576 px), names the failure frame, annotates it with pixel-accurate pointing (or abstains when there is no contact to point at), and emits a report. Minutes, a few dollars, fully auditable trail.

**The two populations are load-bearing.** *Calibration rollouts* run a scripted IK policy with knobs that steer it into specific failure regimes; a **human labels a sampled subset** (clamp(10% × N, 6, 20), stratified 1/3 successes + 2/3 failures) from the closed taxonomy, and that subset is the judge's measuring stick — judge P/R is computed against the human labels, not against knob intent. *Deployment rollouts* run a real policy (today: a pretrained BC-RNN, also on Lift) under an environmental perturbation (`cube_xy_jitter_m` — widened initial-position range); the judge runs on their failures with the calibration P/R attached as trust chips. Both cohorts run on the **same task, env, and camera**, which is what lets the per-label calibration precision transfer onto the deployment findings. See `@docs/eval_methodology.md` for the full framing + limitations.

**Why it matters.** Robotics teams spend weeks hand-crafting eval suites and watching rollouts. We replace that labor with an agentic pipeline that scales horizontally and **explicitly measures its own judge against human-labeled ground truth on a sampled subset**, then carries that measurement through to the deployment findings. A real "eval the eval" story, not a vibes demo.

**Vocabulary — use these exact terms.**

| Term | What it means | Don't say |
|---|---|---|
| Calibration rollout | scripted policy rollout (whether labeled or not) | "scripted rollout", "scored rollout" |
| Deployment rollout | pretrained / real policy rollout | "pretrained rollout", "unscored" |
| Human label | the calibration GT source — one HumanLabel per reviewed rollout | bare "ground truth" |
| Labeling phase | host-side PHASE 2.5 between rollout and judge; blocks on the Gradio UI | "review", "scoring" |
| Judge calibration | judge P/R against human labels on the labeled subset | "metrics", "judge accuracy" |
| Calibrated estimate | a judge label on a deployment rollout, decorated with its calibration P | bare "judge label" |
| Deployment findings | artifacts of applying the judge to deployment rollouts | "report metrics" |

**Non-goals** (do not scope-creep):
- Training new policies. We evaluate, we do not train.
- Building a new simulator. robosuite/MuJoCo exists.
- Sim-to-real, real robots, deployment.
- A general-purpose agent platform. This is one product, narrow and deep.

---

## 2. Judging context (optimize for these weights)

| Criterion | Weight | What this means for daily decisions |
| --- | --- | --- |
| Impact | 30% | Every feature maps to a real robotics-ops pain. If it doesn't, cut it. |
| Demo | 25% | The 3-minute video is the product. Every major decision must produce a "judges lean forward" moment. |
| Opus 4.7 use | 25% | Surface at least three new 4.7 capabilities visibly: 2576px vision with pointing, 1M context (full-findings clustering), file-based memory, per-frame chain-of-thought video judging with calibrated point-abstention. |
| Depth & execution | 20% | Measured numbers (precision/recall vs injected ground truth), clean code, real tests, no dead code. |

**Rule of thumb:** a feature earns its weekend only if it serves at least two of these four.

---

## 3. Architecture

**Multi-agent, four specialized Managed Agents sessions.** Research-preview access to parallel sessions is **confirmed on our org** — treat it as production-usable, not speculative.

Planner (1 session) → Rollout worker (1 session, sequential, **main-thread**) → Judge workers (K parallel sessions) → Reporter (1 session). Only the judge phase fans out via `concurrent.futures.ThreadPoolExecutor` — that's where the wall-clock win comes from (judging is API-bound; rollouts are sim-bound so fan-out buys nothing). The rollout phase MUST run on the host's main thread: on macOS, GLFW's Cocoa init called from a pool thread wedges in an `[NSApplication reportException:]` loop and the whole process hangs. Shared state (`CostTracker`, `RuntimeState`, `dispatch_log.jsonl`) protected by `threading.Lock`; `_ROLLOUT_LOCK` stays in `src/agents/tools.py` as defense-in-depth for the global GLFW context. Lives in `src/orchestrator.py` + `scripts/smoke_agent.py`. Target wall-clock on the 16-rollout smoke: ~4–6 min.

**Inter-session artifact hand-off.** Each session's `/memories/` is isolated — the host cannot read one session's `/memories/` from another. Agents therefore hand final artifacts back to the host via a family of `submit_*` custom tools (`submit_plan`, `submit_results`, `submit_findings`, `submit_report`) which write to `mirror_root/`. The reporter receives plan/matrix/findings inlined in its first user message. Built-in `read`/`write`/`edit`/`bash` remain available for in-session scratch work; the `submit_*` tools are the host-facing boundary.

```
┌──────────────────────────────────────────────────────────────────┐
│ Layer 4: UI (Gradio)                                             │
│  Tabs: Live · Judge calibration · Deployment findings (label /   │
│        condition sub-tabs)                                        │
│  Top banner: $X spent · Y elapsed · N scenarios (cal + dep)       │
│  Phase progress strip: 5 chips                                    │
│    (planner/rollout/LABELING/judge/report)                        │
│  Live tab: agent activity · current rollout · rich gallery       │
│  Judge calibration: labeling flow (video + radio + submit) at    │
│    top; confusion matrix + per-label P/R + drill-down below      │
│  Deployment findings: Judge Trust banner over cluster cards      │
│    decorated with per-label calibration P (deployment-only)      │
└──────────────────────────────────────────────────────────────────┘
                                ▲
                       reads via file watcher + submits labels
                                ▲
┌──────────────────────────────────────────────────────────────────┐
│ Layer 3a: Host-side mirror (IPC files in mirror_root)            │
│  runtime.json · chat.jsonl · dispatch_log.jsonl · keyframes/     │
│  labeling_queue.json (host → UI handoff)                          │
│  human_labels.jsonl (UI → host: calibration GT)                   │
│  Written by orchestrator, dispatch, and the labeling UI.          │
└──────────────────────────────────────────────────────────────────┘
                                ▲
┌──────────────────────────────────────────────────────────────────┐
│ Layer 3: Agent phases (Managed Agents, Opus 4.7)                 │
│  Planner phase   → /memories/plan.md, test_matrix.csv            │
│  Rollout phase   → /memories/rollouts/*.mp4                      │
│  [PHASE 2.5: HUMAN LABELING — host-side, no agent session.       │
│   Samples a subset of scripted rollouts, blocks on the Gradio    │
│   labeling UI until every queued rollout has a HumanLabel.       │
│   Skipped when --skip-labeling is set.]                           │
│  Vision judge    → single CoT call per rollout                   │
│    2576px, N = clamp(video_duration*3, 12, 36), JPEG q88         │
│    per-frame walkthrough (gripper / cube / contact) →            │
│    earliest failure frame_index → taxonomy label →               │
│    point (int,int) OR null (abstains when no contact)            │
│    Binary success taken from sim, NOT from vision.               │
│  Report writer   → /memories/report.md (cluster analysis from    │
│                    full findings.jsonl in 1M-context window)     │
└──────────────────────────────────────────────────────────────────┘
                                ▲
┌──────────────────────────────────────────────────────────────────┐
│ Layer 2: Two populations of policies (both on Lift)              │
│  Calibration: scripted IK picker with knobs that steer behavior  │
│               toward specific failure modes. HUMAN labels a      │
│               sampled subset → that's the calibration GT.        │
│  Deployment:  robomimic BC-RNN pretrained + ENVIRONMENTAL        │
│               perturbation (cube_xy_jitter_m widens placement)   │
│               → judged with calibration trust attached.           │
│  One shared task + judge + labeler — that's what makes the       │
│  per-label calibration P transfer onto the deployment findings.  │
└──────────────────────────────────────────────────────────────────┘
                                ▲
┌──────────────────────────────────────────────────────────────────┐
│ Layer 1: robosuite + MuJoCo                                      │
│  Lift only (post scope-cut). Default camera = frontview.         │
│  Deployment rollouts widen the UniformRandomSampler xy range via │
│  env.placement_initializer.{x,y}_range before first reset().     │
└──────────────────────────────────────────────────────────────────┘
```

**Hard interface discipline.** The orchestrator never imports MuJoCo or robosuite directly. It calls `sim.run_rollout(config) -> RolloutResult` via `src/sim/adapter.py`. The adapter wraps both the pretrained policy and the scripted-failure policy behind one `Policy` interface — that's what keeps the agent code decoupled from the sim layer.

**Dual-population data flow.** Every rollout carries a `population` flag derived from `policy_kind` (scripted = calibration, pretrained = deployment). The Judge calibration tab shows the labeling flow on the calibration subset, then the confusion matrix + per-label P/R computed from `human_labels.jsonl ⋈ findings.jsonl`. The Deployment findings tab applies the per-label calibration P as `calibrated estimate` chips on deployment cluster cards and a rollout table that is deployment-cohort-only. The Live tab and Live banner break down counts as `N total (n_cal cal + n_dep dep)` in the population colors (amber `#f59e0b` for calibration, steel blue `#38bdf8` for deployment). These are NOT the phase colors — different axis.

---

## 4. Tech stack (pinned)

- **Language:** Python 3.12.
- **Model:** `claude-opus-4-7`. See §11 for breaking changes vs 4.6.
- **Agent runtime:** Claude Managed Agents, beta header `managed-agents-2026-04-01`.
- **Simulator:** `mujoco>=3` + `robosuite==1.4.1` (pinned — see below). One env in active use: **`Lift`** (both cohorts). Calibration = scripted policy with knobs that elicit specific failure modes; deployment = pretrained BC-RNN under `cube_xy_jitter_m` environmental perturbation (widens `env.placement_initializer.x_range/y_range` from the default ±3 cm). No custom cameras needed — default `frontview` works.
- **Policy — pretrained (deployment):** `robomimic` v0.3.0 with a pretrained BC-RNN checkpoint for Lift (`artifacts/checkpoints/lift_ph_low_dim.pth`, fetched by `scripts/fetch_checkpoints.py` from the Stanford rt_benchmark model zoo). **Verified 8/8 success** at `cube_xy_jitter_m=0.0` on our stack; failure rate climbs cleanly with the jitter value (0% at 0.12 m → 38% at 0.15 m → 88% at 0.30 m). **Pin robosuite to 1.4.1** — 1.5's composite-controller rewrite re-scales the 1.4-trained BC-RNN's delta actions and produces 0% success (see `@docs/eval_methodology.md` for the full story + robomimic issues #259 / #283). Do **not** use LeRobot — its policies target ALOHA / Koch / SO-100, not Franka Panda.
- **Policy — scripted with injected failures (calibration):** `src/sim/scripted.py`. Knobs steer behavior toward intended visual failure modes: `action_noise>0` destabilizes the approach (produces `missed_approach`), `angle_deg>0` offsets the target laterally (produces `missed_approach`), `premature_close=True` pins the gripper shut from step 0 (produces `missed_approach` — hand skims past with closed fingers), `grip_scale<0.7` carries the cube up for `SLIP_CARRY_STEPS` then releases (produces `failed_grip`; adapter demotes transient-success cases to failure). Ground truth comes from human labels on a sampled subset, not from the knob — see `src/human_labels.py`. Lift-only.
- **UI:** `gradio` ≥ 6 (we run 6.13). Static files served via `/gradio_api/file=<abs_path>` — `allowed_paths=[mirror_root]` MUST be set on `app.launch()` or images 403.
- **Plotting:** `plotly` ≥ 5 (interactive heatmap on the Judge calibration tab; `gr.Plot` only emits `.change` in Gradio 6, no native cell-click — use dropdown filters as the workaround). `matplotlib` available but largely unused.
- **Video:** `imageio-ffmpeg` for `.mp4`. Frame sampling lives in `src/vision/frames.py`.
- **Image overlay:** `pillow` for keyframe rendering. The keyframe is the `frame_index` the judge named (NOT a heuristic midpoint). Red dot is drawn only when the judge returned a non-null `point`; on `point=null` rollouts (e.g. a clean `missed_approach` with no cube contact) the keyframe is the judge-named frame with no overlay. The judge emits one of two named failure modes (`missed_approach` / `failed_grip`) plus `other`; see `docs/taxonomy.md`.
- **Testing:** `pytest`, `pytest-asyncio`.
- **Env:** `uv`. Pin everything in `requirements.txt`. No conda.

**Do not add a dependency without asking first.** Every new dep is a potential install failure.

---

## 5. Directory layout

```
repo/
├── claude.md                     # this file
├── README.md
├── requirements.txt
├── pyproject.toml                # ruff, mypy --strict, pytest config
├── src/
│   ├── agents/
│   │   ├── system_prompts.py     # phase prompts + plain-language rules
│   │   └── tools.py              # rollout/judge custom tools + dispatch
│   ├── sim/
│   │   ├── adapter.py            # run_rollout(config) -> RolloutResult
│   │   ├── policies.py           # Policy interface
│   │   ├── pretrained.py         # robomimic BC-RNN loader (1.4-native passthrough)
│   │   └── scripted.py           # Lift IK picker + InjectedFailures
│   ├── vision/
│   │   ├── judge.py              # single CoT pass: 2576px, ~video_duration*3 frames,
│   │   │                         #   per-frame walkthrough → label + frame_index + point|null
│   │   └── frames.py             # mp4 read + sample_indices + resize + motion-diff helpers
│   ├── ui/
│   │   ├── app.py                # Gradio entrypoint, tab orchestration
│   │   ├── synthesis.py          # ScoredRollout, clusters, copy_button, chips
│   │   ├── metrics_view.py       # cohort, Wilson CI, heatmap, drill-down,
│   │   │                         #   judge_trust banner, calibration chips
│   │   └── panes/
│   │       ├── labeling.py       # human-labeling flow (video + radio + submit)
│   │       ├── calibration.py    # confusion matrix + per-label P/R + drill
│   │       └── findings.py       # deployment cluster cards + rollout table
│   ├── orchestrator.py           # Multi-agent driver: four roles, label phase between rollout+judge
│   ├── label_phase.py            # host-side PHASE 2.5 helper (queue, wait)
│   ├── human_labels.py           # sampler + HumanLabel persistence + resume
│   ├── runtime_state.py          # RuntimeState writes runtime.json + chat.jsonl
│   ├── memory_layout.py          # canonical /memories/ paths
│   ├── schemas.py                # Pydantic: RolloutConfig, RolloutResult, HumanLabel
│   ├── costing.py                # CostTracker + manual-review baseline
│   └── constants.py              # OPUS_MODEL_ID, beta headers, etc.
├── tests/
│   ├── test_schemas.py
│   ├── test_sim_adapter.py
│   ├── test_scripted_failure_injection.py   # @integration sim behavior check
│   ├── test_human_labels.py                  # sampler, persistence, resume
│   ├── test_costing.py                       # Wilson CI, baselines, formatters
│   ├── test_synthesis.py                     # cluster math, scored conversion
│   ├── test_metrics_view.py                  # cohort, drill filter, label adapter
│   ├── test_vision_frames.py
│   ├── test_smoke.py
│   └── test_memory_layout.py
├── scripts/
│   ├── smoke_render.py           # MUJOCO_GL sanity check
│   ├── smoke_scripted_rollout.py # one scripted Lift rollout, no API
│   ├── smoke_pretrained_rollout.py # Lift BC-RNN: single sanity OR --sweep mode
│   ├── smoke_parallel_rollouts.py
│   ├── smoke_agent.py            # full Plan-A end-to-end (REAL API CALLS)
│   ├── fetch_checkpoints.py      # download BC-RNN .pth
│   └── run_ui.py                 # launch the Gradio dashboard
├── docs/
│   ├── taxonomy.md               # closed set of judge labels (load-bearing)
│   ├── install-mujoco-macos.md
│   └── pipeline.html             # standalone pipeline diagram
└── artifacts/                    # per-session, gitignored
    └── runs/<run_id>/            # mirror_root per run
        ├── runtime.json          # banner state (host writes, UI reads)
        ├── chat.jsonl            # phase markers + agent messages + tool calls
        ├── dispatch_log.jsonl    # every rollout/judge call args+result
        ├── labeling_queue.json   # which rollouts go to the human labeler
        ├── human_labels.jsonl    # human-provided GT (calibration)
        ├── rollouts/<id>.mp4
        └── keyframes/<id>.png    # rendered by synthesis layer with red dot
```

---

## 6. Memory layout

There are TWO surfaces, and they are deliberately different.

### Agent-side: `/memories/` (inside the Managed Agents container)

The agent writes its own deliverables here via the built-in `write` tool. The HOST has no direct access to these — the agent thinks to its own disk.

| Path | Owner | Contents |
| --- | --- | --- |
| `/memories/plan.md` | planner | goal, success criteria, scenario budget, mix rationale |
| `/memories/test_matrix.csv` | planner | one row per scenario; columns include `calibration_purpose` (labeler reference, NOT GT) — no `expected_label` |
| `/memories/taxonomy.md` | planner | failure labels copied from `docs/taxonomy.md` |
| `/memories/rollouts/<id>.mp4` | rollout worker | recorded videos (also mirrored host-side, see below) |
| `/memories/findings.jsonl` | vision judge | one line per rollout: `{rollout_id, sim_success, judge: {taxonomy_label, frame_index, point \| null, description}}` |
| `/memories/report.md` | report writer | final markdown deliverable |

### Host-side mirror: `mirror_root/` (e.g. `artifacts/runs/<run_id>/`)

The orchestrator, dispatch, and the labeling UI write a parallel set of files the dashboard reads via file watcher. Path constants in `src/memory_layout.py` and `src/runtime_state.py` — never hardcode.

| Path | Writer | Contents |
| --- | --- | --- |
| `runtime.json` | `RuntimeState.write_snapshot()` on every event | phase, elapsed, cost, dispatch counts, label counts |
| `chat.jsonl` | orchestrator on every agent event | phase markers (including LABELING), agent messages/thinking, tool calls/results |
| `dispatch_log.jsonl` | `tools.dispatch()` on every rollout/judge | full args + result for every custom-tool call |
| `labeling_queue.json` | `src/label_phase.py` at start of PHASE 2.5 | `{queue: [rollout_ids], skipped: bool, created_at}` |
| `human_labels.jsonl` | Gradio labeling UI (`submit_label`) | one HumanLabel per reviewed rollout: `{rollout_id, label, note, labeled_at}` |
| `rollouts/<id>.mp4` | dispatch_rollout (writes locally then surfaces an agent-visible path) | recorded videos |
| `keyframes/<id>.png` | synthesis layer when needed | the `frame_index` the judge named, with red dot at the judge-returned `point` (no dot if `point` is `null`) |

**Rule:** every phase writes the full artifact it produces; every dispatch logs the full call. The dashboard recovers session state purely from disk — replay of an old `mirror_root/` reproduces the same UI.

---

## 7. Project status

Past the original 48-hour sprint. State of the world:

### Done

- **Multi-agent pipeline end-to-end.** Four specialized Managed Agents (planner → rollout worker → K judge workers → reporter) + host-side PHASE 2.5 labeling between rollout and judge. Rollout worker runs on the host main thread (GLFW/Cocoa requirement); judge workers fan out K-wide. All agent phases reach `end_turn` on smoke runs. Entrypoint: `src/orchestrator.py::run_eval`; smoke: `scripts/smoke_agent.py`.
- **Human-labeled calibration.** Knob → label mapping retired (intent-vs-outcome gap was corrupting the scripted GT). Ground truth for calibration now comes from a human reviewer labeling a sampled subset of scripted rollouts via the Gradio labeling UI. Stratified sampler `clamp(10%×N, 6, 20)` / 1/3 successes + 2/3 failures in `src/human_labels.py`. `--skip-labeling` bypasses the UI for unattended smoke runs.
- **Both populations on Lift.** Calibration = scripted Lift with knobs steering behavior toward specific visual failure modes; deployment = pretrained Lift BC-RNN under `cube_xy_jitter_m` environmental perturbation (±15 cm for demo runs). BC-RNN verified **8/8 success at `cube_xy_jitter_m=0.0`**, **38% failure at 0.15 m** (clean OOD stress test). Slip knob carries the cube up for `SLIP_CARRY_STEPS` LIFT-phase steps before releasing; adapter re-verifies success at the end of POST_SUCCESS_HOLD so transient crossings of the height threshold don't register as successes.
- **Outcome-axis taxonomy (2 named labels + `other`).** Collapsed from a 3-label outcome taxonomy on 2026-04-24 to `missed_approach` / `failed_grip` (+ `other` escape). Prior intermediate taxonomies (10-mechanism, then 3-outcome) both ran into distinctions below the pixel+frame-rate resolution of the judge (scratch vs knock vs approach_miss; slip vs premature_release; closed-fingers-all-the-way-down vs no-contact-miss). The 2-mode split is "did the cube ever leave the table inside the gripper? yes → failed_grip, no → missed_approach". See `docs/taxonomy.md`. Legacy on-disk labels are remapped at read time via `_LEGACY_LABEL_MAP` in `src/human_labels.py`.
- **Single-call vision judge.** One Messages-API call per failed rollout at 1920 px × `clamp(video_duration*3, 12, 36)` frames. Prompt tuned to the 2-label outcome axis — no per-frame CoT table, no anti-default heuristics. Binary success still comes from `RolloutResult.success` (sim `env._check_success()`); the judge only classifies the failure mode and points at it (or abstains via `point=null` on no-contact failures).
- **Cost + wall-time accounting.** `src/costing.py` tracks Opus 4.7 token usage live off `span.model_request_end → model_usage` (Messages-API calls go through `response.usage`), computes manual-review baseline ($75/hr × 3 min/rollout for cost, sum of video durations + 60 s/rollout for wall time), surfaces both as the headline banner.
- **Dashboard.** Overview tab (KPI strip, pipeline cards, final-report card rendered from `report.md` once the reporter submits). Live tab (chat + current rollout video + rich gallery). Judge calibration tab (labeling flow at top: video + radio + submit; confusion matrix + per-label P/R below, computed from human_labels ⋈ findings). Deployment findings tab (Judge Trust banner + cluster cards decorated with calibration-precision chips). Phase progress strip shows 5 chips (planner/rollout/**labeling**/judge/report).
- **Plain-language agent messages.** Agents never see human_labels.jsonl and never label rollouts themselves. The planner's test matrix uses `calibration_purpose` as a human-facing metadata column; no `expected_label`.

### Open methodology questions
- **Engineered vs natural failure distribution.** Even with same-task calibration and human labels, scripted failures look visually distinct from BC-RNN natural failures. A held-out human-labeled deployment set would close it — explicitly out of scope.
- **Sub-second event resolution.** The judge samples at ~3 fps (≈0.33 s/frame). Events shorter than that interval can still fall between frames. Escalation paths: adaptive motion-weighted sampling, zoom-and-refine crop re-ask, N=3 self-consistency. Native video is not a Claude option (see §11).

### Remaining for the demo recording

- README.md polish (positioning one-liner, architecture diagram, install, headline numbers).
- `docs/demo_script.md` — shot list (use the new tab structure: open on Overview with the banner, cut to Live mid-run, drop the final-report card at the end).
- 100–200 word written hackathon summary.
- Live smoke to confirm the simplified judge lifts multiclass label accuracy on the 2-label axis (no prior validation yet under the 2-mode prompt).
- Recording itself.

(`docs/eval_methodology.md` already exists and reflects the current Lift-only, same-task calibration framing.)

---

## 8. Code standards

- **Explicit over clever.** Readable 15-line function beats a dense 5-line one. Judges will read this code.
- **DRY, but not at the cost of clarity.** Extract helpers at the second call site, not the first.
- **Schemas at boundaries.** Every cross-module function takes and returns Pydantic models. No dicts across module boundaries.
- **Type hints on all public functions.** `mypy --strict` on `src/`.
- **Errors are loud.** Never `except Exception: pass`. Raise custom exceptions from `src/errors.py`.
- **No dead code.** If a function isn't called, delete it.
- **No magic strings.** Paths, model names, tools, env names live in `src/constants.py` or `src/memory_layout.py`.
- **Comments explain why.** If a comment describes what the code does, rewrite the code.
- **One concern per file.**

**Before claiming a task done:** `ruff check && ruff format && mypy src/ && pytest -q`. All four pass. No exceptions.

---

## 9. Testing philosophy

- **Unit tests** for schemas, metrics, and pure helpers. Fast.
- **Integration tests** behind `@pytest.mark.integration`. Skipped in CI.
- **No API calls in CI.** Mock the Anthropic client. Real calls live in `scripts/smoke_*.py`.
- **Injected-failure fixtures are test gold.** `tests/fixtures/injected_failures/` gives us known-label rollout clips for `test_vision_judge_precision`. Use them.
- **Every bug fix starts with a failing test.** Especially at hackathon tempo.

---

## 10. Commands cheatsheet

```bash
# setup
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt

# lint + type + test (run before every commit)
ruff check . && ruff format . && mypy src/ && pytest -q

# smoke: render one frame (sanity-check MUJOCO_GL on this machine)
MUJOCO_GL=glfw python scripts/smoke_render.py

# smoke: one scripted Lift rollout, no API
python scripts/smoke_scripted_rollout.py

# smoke: one Lift BC-RNN rollout at jitter=0 (expect success), no API
python scripts/smoke_pretrained_rollout.py

# BC-RNN SANITY GATE before any agent-flow run — $0, ~30 s, 3 seeds.
# If this fails, your sim stack is broken (likely robosuite upgraded past
# 1.4.1) and spending $18+ on smoke_agent will just burn money. Fix before
# proceeding. Expected: 3/3 success.
MUJOCO_GL=glfw python -c "
import sys; sys.path.insert(0,'.')
from pathlib import Path
from src.schemas import RolloutConfig
from src.sim.adapter import run_rollout
ck = Path('artifacts/checkpoints/lift_ph_low_dim.pth')
ok = sum(run_rollout(RolloutConfig(rollout_id=f's{s}', policy_kind='pretrained',
                                    env_name='Lift', seed=s, max_steps=200,
                                    checkpoint_path=ck), video_out=None).success for s in range(3))
print(f'BC-RNN sanity: {ok}/3')
assert ok == 3, 'sim stack broken — do not run smoke_agent'
"

# smoke: full end-to-end multi-agent run (HITS REAL ANTHROPIC API — target ~4-6 min for 16 rollouts)
# K controls judge worker fan-out (default 4). --skip-labeling bypasses the
# host-side PHASE 2.5 labeling UI for unattended smoke runs.
python scripts/smoke_agent.py
python scripts/smoke_agent.py --k-workers 4 --skip-labeling

# launch the dashboard (point at a mirror_root; auto-opens in browser)
python scripts/run_ui.py
# or: python scripts/run_ui.py --mirror-root artifacts/smoke/agent
```

---

## 11. Opus 4.7 + Managed Agents specifics — READ THIS, breaking changes

**Model:** `claude-opus-4-7`.

**Two beta headers on two different APIs. Do not conflate them.**

| Feature | API | Beta header |
| --- | --- | --- |
| Managed Agents sessions | Managed Agents | `managed-agents-2026-04-01` |
| Task budgets | Messages API | `task-budgets-2026-03-13` *(verify against docs at ship time)* |

**Effort parameter (`high`, `xhigh`, `max`) is Messages-API-only.** Claude Managed Agents handles effort automatically — do **not** pass `effort` to a Managed Agents session. If you want the `/ultrareview`-style deep reasoning behavior inside an agent session, you get it by default.

**Task budgets (Messages API):** minimum 20k tokens; soft signal to the model, not a hard cap. Pair with `max_tokens` for a hard ceiling. On Managed Agents, the harness manages tokens itself.

**Breaking changes from Opus 4.6 — silent failure territory:**
- `temperature`, `top_p`, `top_k` now **400 error**. Remove from all requests.
- Assistant-turn **prefill removed.** Use structured outputs or explicit instruction constraints instead.
- `thinking.budget_tokens` **removed.** Use `effort` (Messages API) or rely on Managed Agents' auto handling.
- `thinking.display` defaults to `"omitted"`. For the Gradio thought-stream pane we want visible reasoning → set `"display": "summarized"`.
- New tokenizer: ~1.0× to 1.35× tokens for the same text. Budget accordingly.

Migration guide: https://platform.claude.com/docs/en/about-claude/models/whats-new-claude-4-7 (keep `docs/opus-4-7-gotchas.md` synced with anything we hit).

**Core concepts (name code after these):** Agent = model + prompt + tools; Environment = container; Session = running instance; Events = messages in and out.

**Vision.** Up to 2576 px long edge. Supports pointing (returns pixel coordinates that map 1:1 to the submitted image) and bounding-box localization. One dense-frame call per rollout per §3.

**No native video input.** Confirmed via the SDK (no `VideoBlockParam`, only `image/{jpeg,png,gif,webp}` MIME types) and the docs. Frame sampling is the only path. The Files API doesn't bridge video on Opus 4.7 either. Don't waste time chasing this lever.

**Research preview, access confirmed on our org:** parallel Managed Agents sessions (used by the orchestrator per §3). `outcomes` and cross-session memory are also research preview but we do not currently depend on them. Treat the parallel-sessions path as production-usable; do not reintroduce "gated behind preview" caveats in code or prompts.

**Rate limits:** 60 create/min, 600 read/min per org. The orchestrator creates 3 + K sessions (planner + 1 rollout worker + K judge workers + reporter). At K=4 that's 7 sessions per eval — well under the limit.

---

## 11.5 Cost accounting and baseline

`src/costing.py::CostTracker` prices the run at a flat **$0.20 per rollout dispatched** (`COST_PER_ROLLOUT_USD`). The counter ticks once inside `_dispatch_rollout` — phases that don't talk to Claude (idle, planner setup before any rollout, sim-only host work, the human-labeling phase) leave it at $0. Empirical anchor: a 30-rollout end-to-end run (planner + rollout-worker + judges + reporter) lands around **$6 of API spend** on the post-single-pass-judge stack, i.e. ~$0.20 amortised per rollout. We retired token-level pricing (Opus 4.7 per-Mtok rates, `add_usage`, the `span.model_request_end` listener, the Messages-API `response.usage` path) when we moved to this model — there is exactly one number to maintain and it's the per-rollout constant.

The dashboard shows live cost vs two baselines:

- **Cost baseline:** $75/hr × 3 min/rollout (loaded labor cost — engineer reviews video, classifies failure, takes notes). Constants in `src/costing.py`. Edit `BASELINE_HOURLY_RATE_USD` / `BASELINE_SECONDS_PER_ROLLOUT` to retune.
- **Time baseline:** sum of actual video durations + 60 s/rollout review overhead. Closer to "wall time a sequential reviewer would take to watch" than the cost baseline. Helper: `baseline_time_seconds_for_videos`.

The Live banner renders both as side-by-side columns + a green "Cost saved / Time saved" footer. Headline numbers in the demo recording come from the actual session — never fabricate.

If the per-rollout cost shifts (e.g. judge frame budget changes, or the rollout-worker's reasoning gets meaningfully heavier), re-baseline against API-key spend on a fresh full-length smoke and update `COST_PER_ROLLOUT_USD`.

---

## 13. Demo video plan

Full shot list in `docs/demo_script.md`. Principles:

- **Open with the pain, not the product.** "Every robotics team burns weeks on evals. This took ~`<wall_time>`, cost ~`<cost>`, and reports its own judge precision against synthetic ground truth." Numbers come from the recording-day smoke — fill in after.
- **Live cost / time / scenarios banner visible from second 1.** Show `Scenarios: N (n_cal cal + n_dep dep)` so the dual-population framing lands immediately.
- **Population chips on every rollout.** Amber `Calibration` and blue `Deployment` are the visual signature — make sure both colors appear on screen within the first 30 seconds.
- **Exactly one judge annotation at full 1920 px** with the red dot overlay visible on a true-contact failure (e.g. `failed_grip`), AND one abstention example (`point = null`, no dot) on a no-contact failure (e.g. a clean `missed_approach`). The contrast is the point of the abstention design — show both. Click either keyframe to open the source mp4.
- **HERO SHOT: the Judge Trust banner reveal.** When Phase 3 completes, the Deployment findings tab populates the trust banner with measured calibration P/R numbers. This is the "judges lean forward" moment — it visually connects the synthetic calibration on Lift to the trust we have in the deployment labels on the SAME Lift task under environmental perturbation (both cohorts are Lift now; the calibration P transfers directly). Cut to it on a clean transition, hold for 2-3 seconds.
- **Close on measured numbers:** `<cost> · <scenarios> total (n_cal cal / n_dep dep) · multiclass label accuracy <Z>% · per-label precision on calibration · point-abstention rate on no-contact failures`. Real numbers from the recording-day smoke — never aspirational.
- 3:00 hard cap.

**Note on the dropped shot:** the original draft showed `/memories/` filling up live as a "thinking to disk" moment. We removed the /memories tree pane from the UI because the host has no access to the agent's actual `/memories/` (only to the host-side mirror). The Judge Trust banner reveal replaces it as the new lean-forward moment.

---

## 15. Anti-patterns — do not do these

- Do not train a policy.
- Do not wrap LeRobot into a Franka env. (Will fail.)
- Do not invent a simulator abstraction. robosuite behind one adapter, that's it.
- Do not build auth, multi-user, or a database.
- Do not add Docker / Kubernetes.
- Do not add a second LLM provider.
- Do not rebuild the agent harness. Use Managed Agents — that is the point.
- Do not pass `temperature` / `top_p` / `top_k` / `prefill` to Opus 4.7. (Breaking.)
- Do not pass `effort` to Managed Agents sessions.
- Do not implement k-means. Use the 1M context.
- Do not over-invest in the CLI. Gradio is the demo surface.
- Do not let any test take > 30 s.
- Do not write docs for code that does not exist yet.
- Do not try to feed mp4s directly to Claude. Opus 4.7 has no `VideoBlockParam`, only image MIME types. Frame-sampling is the only path. (See §11 "No native video input".)
- Do not use day-tag prefixes (`sat-am:`, `sun-pm:`) in commit messages or status updates. Git timestamps already sequence work; the tag adds no information.
- Do not bump `robosuite` past 1.4.1 without first re-running the BC-RNN sanity gate in §10. 1.5's composite-controller rewrite silently produces 0/16 success — see §16 for the full symptom.
- Do not reintroduce cross-task evaluation (calibration on one env, deployment on another) without a methodology note. Today both cohorts run Lift so per-label calibration P transfers directly onto deployment findings — if you split them again, the Judge Trust chips stop being honest and need explicit `(env)` tagging.
- Do not reintroduce a separate coarse pass. The single-call judge replaced the two-pass design on 2026-04-24 (§7). Binary success comes from sim, not vision. If you need tighter temporal resolution, add frames to the single call (cap 36) or switch to motion-weighted sampling inside `frames.py` — do not add a second API round-trip.
- Do not require the judge to return a `point` on every rollout. `point = null` is a first-class output for failure modes with no gripper-cube contact (e.g. a clean `missed_approach` where the fingers close on empty air, or a rollout that skims past the cube with closed fingers). Pydantic type is `tuple[int, int] | None`, not `tuple[int, int]`. Forcing a coordinate is what caused the "random red dot" regressions.
- Do not render the keyframe from a heuristic (midpoint of any range, `n // 2`, etc.). The keyframe is always the `frame_index` the judge named. If the judge didn't name one, the rollout shouldn't have a keyframe.
- Do not reintroduce the knob → ground-truth-label mapping. `InjectedFailures.to_label` was deleted because knob intent and visual outcome diverged often enough to corrupt GT (action_noise=0.10 labeled knock but visually approach_miss; grip_force_scale=0.5 labeled slip but visually approach_miss because the gripper released before the lift started). Ground truth is human labels on a sampled subset — full stop.
- Do not let an agent touch `human_labels.jsonl`, `labeling_queue.json`, or attempt to label rollouts itself. The judge must stay blind to calibration signal. Agent prompts already enforce this; don't loosen them.
- Do not skip the post-success re-verification in `src/sim/adapter.py`. It demotes transient success crossings (e.g. slip rollouts where the cube is briefly above the success height before falling) to failures. Without it, `failed_grip` rollouts register as sim-successes and never reach the judge.
- Don't reintroduce `gripper_slipped` / `gripper_not_open` as separate modes without a methodology note. The 2-mode taxonomy (`missed_approach` / `failed_grip`) is what the judge prompt is tuned for; splitting fingers-not-open vs closed-at-air back out put the judge inside its sub-second resolution floor. Legacy labels on disk are handled by `_LEGACY_LABEL_MAP` at read time — that's the compatibility surface, not a reopening of the taxonomy question.

---

## 16. Known pitfalls

- **MuJoCo on macOS Apple Silicon.** Try `MUJOCO_GL=glfw` first, fallback `egl`. Document whatever works in `docs/install-mujoco-macos.md` the moment it works.
- **GLFW + Cocoa + worker threads = hang.** On macOS, `glfwInit` can only be called from the process main thread — `NSApplication` enforces it. Calling it from a `ThreadPoolExecutor` worker wedges the process in an `[NSApplication reportException:]` → `_os_log_impl` → `backtrace_symbols` loop (visible at 97% CPU in `sample <pid>`). This is why the rollout phase runs in ONE session on the host's main thread (see §3 + `src/orchestrator.py::_run_rollout_worker`). Do NOT put rollouts back behind a ThreadPoolExecutor unless you've also moved `MUJOCO_GL` off `glfw` (e.g. `cgl`) or moved dispatch to a subprocess. Rollouts were already serialized by `_ROLLOUT_LOCK` anyway, so fan-out gave nothing.
- **Multiprocessing.** Use `get_context("spawn").Pool`, **never fork** — MuJoCo contexts are not fork-safe. Each worker must create its own env; envs are not pickle-safe across processes. Sequential fallback is fine (< 15 min for 30 rollouts).
- **robomimic obs shapes.** Must match the checkpoint's training config. Stick to the canonical Lift observation set (`robot0_eef_pos`, `robot0_eef_quat`, `robot0_gripper_qpos`, `object`); robosuite emits `object-state` and we alias it to `object` in `src/sim/pretrained.py::RobomimicPolicy.act`. Wrap any future mismatch there, never fork the policy.
- **Opus 4.7 literalism.** More literal than 4.6. Be explicit in system prompts; do not expect the model to generalize from one item to another unprompted.
- **Silent 4.7 breakages.** §11 list. Verify any 4.6-era snippet before reusing.
- **Tokenizer change.** Up to ~35% more tokens for the same text. Adjust `max_tokens` and `task_budget` upward vs 4.6 baselines.
- **Cross-task calibration drift — resolved.** Prior design calibrated on Lift and deployed on NutAssemblySquare, so the calibration number was at best a floor. Post scope-cut we run BOTH cohorts on Lift, so the per-label calibration precision can legitimately decorate deployment findings.
- **Knob → label drift — resolved.** The scripted policy used to export an `InjectedFailures.to_label()` mapping that became the calibration GT. It was a lie on many seeds (noise=0.10 produced visual approach_misses, etc.), which penalized the judge for being correct and rewarded it for agreeing with the knob. Replaced 2026-04-24 with human-labeled GT on a sampled subset — see `src/human_labels.py` and the labeling UI at `src/ui/panes/labeling.py`. The knobs are still useful: they reliably produce failure DIVERSITY in the calibration pool; they just don't claim to name what each rollout actually shows.
- **Slip produced no visible lift — resolved.** The prior slip impl paused at grasp height while opening the gripper BEFORE the lift started, so the cube was released back onto the table and the rollout looked like an approach_miss. New impl (`SLIP_CARRY_STEPS`) carries the cube up for ~15 LIFT-phase steps with the gripper closed, THEN commands open; cube falls visibly from height. Adapter's post-success re-verification catches the brief success-threshold crossing and demotes it to failure.
- **robosuite version pin.** We pin `robosuite==1.4.1` in `requirements.txt`. Robosuite 1.5's composite-controller rewrite re-scales the 1.4-trained BC-RNN's delta actions into garbage (symptom: arm rises away from cube with gripper closed from step 0, 0/16 success). Stanford publishes only 1.5-compatible *datasets*, not re-trained checkpoints — upstream context in robomimic issues #259 / #283. 1.4.1 is pure Python on the DeepMind mujoco bindings and installs cleanly on Python 3.12 arm64. Don't upgrade robosuite without also re-validating the BC-RNN succeeds at `cube_xy_jitter_m=0.0`.
- **Frame sampling vs sub-second events.** The judge samples at ~3 fps (≈0.33 s/frame) regardless of clip length. Events shorter than that interval (a brief gripper-cube graze, ~50 ms contact) can still fall between frames — the judge then reasons from consequence frames and may mis-label. Escalation paths: pixel-difference-driven adaptive sampling (redistribute frames toward high-motion windows), a zoom-and-refine crop re-ask around the judge's `frame_index` (CropVLM pattern), self-consistency at N=3. Native video isn't an option (see §11).
- **Judge simplification history.** Two-pass (coarse 768 px → fine 2576 px windowed) was retired on 2026-04-24 in favor of a single-call design with per-frame CoT over 12–36 frames and a 10-label taxonomy. That version then misclassified most runs in live testing — the per-frame observation ritual created ~100 places to mis-observe before label selection, and one anti-default heuristic ("resist approach_miss") was flipping correct answers on BC-RNN's approach failures. A 3-outcome-label intermediate (`missed_approach` / `gripper_slipped` / `gripper_not_open` + `other`) lifted accuracy to ~50% but was still confusion-dominated between `gripper_slipped`↔`gripper_not_open` and `gripper_not_open`↔`missed_approach`. **Current design (2026-04-24 collapse):** one Messages-API call at **1920 px** (the max-dimension cap for many-image requests) over `clamp(video_duration*3, 12, 36)` frames, no per-frame table, no anti-default heuristics, two named outcome labels (`missed_approach` / `failed_grip` + `other`). The decisive cue is "did the cube ever leave the table inside the gripper?". Methodology caveat: the `action_noise` knob previously mapped to `KNOCK_OBJECT_OFF_TABLE` and now maps to `MISSED_APPROACH` (modal outcome), so pre/post-collapse per-label P/R are not directly comparable. Telemetry rows are still appended as a supporting ASCII table. Keyframe comes from the judge's `frame_index`, red dot from `point` (skipped when `null`).

---

## 17. Reference docs

- Managed Agents overview: https://platform.claude.com/docs/en/managed-agents/overview
- What's new in Opus 4.7 + migration: https://platform.claude.com/docs/en/about-claude/models/whats-new-claude-4-7
- Task budgets: https://platform.claude.com/docs/en/build-with-claude/task-budgets
- Memory tool: https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool
- robosuite: https://robosuite.ai
- robomimic: https://robomimic.github.io
- Mandlekar et al. 2021 (BC-RNN / robomimic baselines): https://arxiv.org/abs/2108.03298
- MuJoCo Menagerie: https://github.com/google-deepmind/mujoco_menagerie

---

*Update this file whenever an architectural decision is made or reversed. A stale CLAUDE.md is worse than none.*