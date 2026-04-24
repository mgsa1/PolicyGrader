# CLAUDE.md — Embodied Eval Orchestrator

> Project memory for Claude Code. Keep this file lean and high-signal.
> Put anything that only matters sometimes in `docs/` and reference with `@docs/filename.md`.

---

## 1. North Star

**Positioning (also the README one-liner):** An agentic system that runs and analyzes robot manipulation policy evaluations end-to-end, reducing manual eval-video review from hours to minutes.

Submitted to the Anthropic Opus 4.7 Hackathon.

**How it works.** Describe an evaluation goal in English → an Opus 4.7 Managed Agent designs a test suite, runs rollouts in simulation across two populations side by side, watches the resulting videos in two passes (coarse then high-resolution), annotates failure frames with pixel-accurate pointing, and emits a report. Minutes, a few dollars, fully auditable trail.

**The two populations are load-bearing.** *Calibration rollouts* run a scripted policy with deliberately-injected output knobs on Lift — ground truth is known by construction, so we measure judge precision/recall against it. *Deployment rollouts* run a real policy (today: a pretrained BC-RNN, also on Lift) under an environmental perturbation (`cube_xy_jitter_m` — widened initial-position range) where ground truth is unknown — the judge is applied with its calibration trust attached. Both cohorts run on the **same task, env, and camera**, which is what lets the calibration precision numbers actually attach to the deployment findings instead of being at-best a floor. The dashboard's headline number is the calibrated judge applied to the deployment population. See `@docs/eval_methodology.md` for the full framing + limitations.

**Why it matters.** Robotics teams spend weeks hand-crafting eval suites and watching rollouts. We replace that labor with an agentic pipeline that scales horizontally, **measures its own judge against synthetic ground truth, and explicitly carries that measurement through to the deployment findings.** A real "eval the eval" story, not a vibes demo.

**Vocabulary — use these exact terms.**

| Term | What it means | Don't say |
|---|---|---|
| Calibration rollout | scripted policy + injected failure (GT known) | "scripted rollout", "scored rollout" |
| Deployment rollout | pretrained / real policy (no GT label) | "pretrained rollout", "unscored" |
| Injected ground truth | the programmed failure label on calibration rollouts | bare "ground truth" |
| Judge calibration | P/R measurement against injected GT | "metrics", "judge accuracy" |
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
| Opus 4.7 use | 25% | Surface at least three new 4.7 capabilities visibly: 2576px vision with pointing, 1M context (full-findings clustering), file-based memory, two-pass forensics. |
| Depth & execution | 20% | Measured numbers (precision/recall vs injected ground truth), clean code, real tests, no dead code. |

**Rule of thumb:** a feature earns its weekend only if it serves at least two of these four.

---

## 3. Architecture

**Deployment decision: build for Plan A. Treat Plan B as stretch only.**

Multi-agent Managed Agents sessions, `outcomes`, and cross-session memory are all **research preview** but the feature are available. 

- **Plan A (default).** ONE Managed Agents session running Opus 4.7 with the full tool suite. The four logical roles — planner, rollout worker, vision judge, report writer — are *phases* within one session, separated by system-prompt markers and distinct artifacts in `/memories/`. The agent thinks to disk; we read along. This is what we actually build.
- **Plan B (only if research preview granted in time).** Swap in a true coordinator with `callable_agents`. Because of the interface discipline below, this is a config change, not a refactor.

```
┌──────────────────────────────────────────────────────────────────┐
│ Layer 4: UI (Gradio)                                             │
│  Tabs: Live · Judge calibration · Deployment findings (label /   │
│        condition sub-tabs)                                        │
│  Top banner: $X spent · Y elapsed · N scenarios (cal + dep)       │
│  Phase progress strip: 4 chips (planner/rollout/judge/report)    │
│  Live tab: agent activity · current rollout · rich gallery       │
│  Judge calibration: cohort pills, binary panel + Wilson CI,      │
│    multiclass heatmap, per-label table, drill-down (filtered)    │
│  Deployment findings: Judge Trust banner over cluster cards      │
│    decorated with per-label calibration P                        │
└──────────────────────────────────────────────────────────────────┘
                                ▲
                       reads via file watcher
                                ▲
┌──────────────────────────────────────────────────────────────────┐
│ Layer 3a: Host-side mirror (IPC files in mirror_root)            │
│  runtime.json · chat.jsonl · dispatch_log.jsonl · keyframes/     │
│  Written by orchestrator + dispatch on every event.              │
└──────────────────────────────────────────────────────────────────┘
                                ▲
┌──────────────────────────────────────────────────────────────────┐
│ Layer 3: ONE Managed Agents session (Opus 4.7)                   │
│  Planner phase   → /memories/plan.md, test_matrix.csv            │
│  Rollout phase   → /memories/rollouts/*.mp4                      │
│  Vision judge    → two-pass                                      │
│    Pass 1 coarse (~768px, 24 frames, earliest-failure-window)    │
│    Pass 2 fine   (2576px, 14 frames, windowed, pointing)         │
│  Report writer   → /memories/report.md (cluster analysis from    │
│                    full findings.jsonl in 1M-context window)     │
└──────────────────────────────────────────────────────────────────┘
                                ▲
┌──────────────────────────────────────────────────────────────────┐
│ Layer 2: Two populations of policies (both on Lift)              │
│  Calibration: scripted IK picker with injected OUTPUT knobs      │
│               → known ground-truth label per rollout             │
│  Deployment:  robomimic BC-RNN pretrained + ENVIRONMENTAL        │
│               perturbation (cube_xy_jitter_m widens placement)   │
│               → no ground truth, judged with calibration trust   │
│  Two different perturbation surfaces (policy output vs env),     │
│  one shared task + judge — that's what makes the calibration P/R │
│  meaningful on the deployment findings.                          │
└──────────────────────────────────────────────────────────────────┘
                                ▲
┌──────────────────────────────────────────────────────────────────┐
│ Layer 1: robosuite + MuJoCo                                      │
│  Lift only (post scope-cut). Default camera = frontview.         │
│  Deployment rollouts widen the UniformRandomSampler xy range via │
│  env.placement_initializer.{x,y}_range before first reset().     │
└──────────────────────────────────────────────────────────────────┘
```

**Hard interface discipline.** The orchestrator never imports MuJoCo or robosuite directly. It calls `sim.run_rollout(config) -> RolloutResult` via `src/sim/adapter.py`. The adapter wraps both the pretrained policy and the scripted-failure policy behind one `Policy` interface. This is what lets §12's pivot (`.mp4` files instead of sim) swap in without touching agent code, *and* what lets Plan B swap in without touching sim code.

**Dual-population data flow.** Every rollout carries a `population` flag derived from `ground_truth_label` (calibration if non-empty, deployment if empty). The Judge calibration tab consumes only the calibration subset for P/R numbers. The Deployment findings tab applies those P/R numbers to deployment rollouts as `calibrated estimate` chips. The Live tab and Live banner break down counts as `N total (n_cal cal + n_dep dep)` in the population colors (amber `#f59e0b` for calibration, steel blue `#38bdf8` for deployment). These are NOT the phase colors — different axis.

---

## 4. Tech stack (pinned)

- **Language:** Python 3.12.
- **Model:** `claude-opus-4-7`. See §11 for breaking changes vs 4.6.
- **Agent runtime:** Claude Managed Agents, beta header `managed-agents-2026-04-01`.
- **Simulator:** `mujoco>=3` + `robosuite==1.4.1` (pinned — see below). One env in active use: **`Lift`** (both cohorts). Calibration = scripted policy with injected output knobs (known ground truth); deployment = pretrained BC-RNN under `cube_xy_jitter_m` environmental perturbation (widens `env.placement_initializer.x_range/y_range` from the default ±3 cm). No custom cameras needed — default `frontview` works.
- **Policy — pretrained (deployment):** `robomimic` v0.3.0 with a pretrained BC-RNN checkpoint for Lift (`artifacts/checkpoints/lift_ph_low_dim.pth`, fetched by `scripts/fetch_checkpoints.py` from the Stanford rt_benchmark model zoo). **Verified 8/8 success** at `cube_xy_jitter_m=0.0` on our stack; failure rate climbs cleanly with the jitter value (0% at 0.12 m → 38% at 0.15 m → 88% at 0.30 m). **Pin robosuite to 1.4.1** — 1.5's composite-controller rewrite re-scales the 1.4-trained BC-RNN's delta actions and produces 0% success (see `@docs/eval_methodology.md` for the full story + robomimic issues #259 / #283). Do **not** use LeRobot — its policies target ALOHA / Koch / SO-100, not Franka Panda.
- **Policy — scripted with injected failures (calibration):** `src/sim/scripted.py`. Knob → label mapping: `action_noise ≥ 0.10 → knock_object_off_table`; `angle_deg > 0 → approach_miss`; `premature_close = True → approach_miss`; `grip_scale < 0.7 → slip_during_lift`. Each config has known ground truth. Lift-only — the scope cut removed all other envs.
- **UI:** `gradio` ≥ 6 (we run 6.13). Static files served via `/gradio_api/file=<abs_path>` — `allowed_paths=[mirror_root]` MUST be set on `app.launch()` or images 403.
- **Plotting:** `plotly` ≥ 5 (interactive heatmap on the Judge calibration tab; `gr.Plot` only emits `.change` in Gradio 6, no native cell-click — use dropdown filters as the workaround). `matplotlib` available but largely unused.
- **Video:** `imageio-ffmpeg` for `.mp4`. Frame sampling lives in `src/vision/frames.py`.
- **Image overlay:** `pillow` for keyframe rendering with red dot at Pass-2 point coordinate.
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
│   │   └── tools.py              # rollout/coarse/fine custom tools + dispatch
│   ├── sim/
│   │   ├── adapter.py            # run_rollout(config) -> RolloutResult
│   │   ├── policies.py           # Policy interface
│   │   ├── pretrained.py         # robomimic BC-RNN loader (1.4-native passthrough)
│   │   └── scripted.py           # Lift IK picker + InjectedFailures
│   ├── vision/
│   │   ├── coarse_pass.py        # 768px, 24 frames, binary + earliest-range
│   │   ├── fine_pass.py          # 2576px, 14 frames, windowed, pointing
│   │   └── frames.py             # mp4 read + sample_indices + resize
│   ├── ui/
│   │   ├── app.py                # Gradio entrypoint, tab orchestration
│   │   ├── synthesis.py          # ScoredRollout, clusters, copy_button, chips
│   │   └── metrics_view.py       # cohort, Wilson CI, heatmap, drill-down,
│   │                             #   judge_trust banner, calibration chips
│   ├── orchestrator.py           # ONE Managed Agents session, four phases
│   ├── runtime_state.py          # RuntimeState writes runtime.json + chat.jsonl
│   ├── memory_layout.py          # canonical /memories/ paths
│   ├── schemas.py                # Pydantic: RolloutConfig, RolloutResult, etc.
│   ├── metrics.py                # P/R against injected ground truth
│   ├── costing.py                # CostTracker + manual-review baseline
│   └── constants.py              # OPUS_MODEL_ID, beta headers, etc.
├── tests/
│   ├── test_schemas.py
│   ├── test_sim_adapter.py
│   ├── test_scripted_failure_injection.py   # @integration where it touches sim
│   ├── test_metrics.py
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
│   ├── taxonomy.md               # closed set of Pass-2 labels (load-bearing)
│   ├── install-mujoco-macos.md
│   └── pipeline.html             # standalone pipeline diagram
└── artifacts/                    # per-session, gitignored
    └── smoke/agent/              # default mirror_root for scripts/smoke_agent.py
        ├── runtime.json          # banner state (host writes, UI reads)
        ├── chat.jsonl            # phase markers + agent messages + tool calls
        ├── dispatch_log.jsonl    # every rollout/coarse/fine call args+result
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
| `/memories/test_matrix.csv` | planner | one row per scenario, knob values, expected_label |
| `/memories/taxonomy.md` | planner | failure labels copied from `docs/taxonomy.md` |
| `/memories/rollouts/<id>.mp4` | rollout worker | recorded videos (also mirrored host-side, see below) |
| `/memories/findings.jsonl` | vision judge | one line per rollout: pass-1 verdict + pass-2 annotation |
| `/memories/report.md` | report writer | final markdown deliverable |

### Host-side mirror: `mirror_root/` (default `artifacts/smoke/agent/`)

The orchestrator and dispatch write a parallel set of files the dashboard reads via file watcher. Path constants in `src/memory_layout.py` and `src/runtime_state.py` — never hardcode.

| Path | Writer | Contents |
| --- | --- | --- |
| `runtime.json` | `RuntimeState.write_snapshot()` on every event | phase, elapsed, cost, dispatch counts, planned_total |
| `chat.jsonl` | orchestrator on every agent event | phase markers, agent messages/thinking, tool calls/results |
| `dispatch_log.jsonl` | `tools.dispatch()` on every rollout/coarse/fine | full args + result for every custom-tool call |
| `rollouts/<id>.mp4` | dispatch_rollout (writes locally then surfaces an agent-visible path) | recorded videos |
| `keyframes/<id>.png` | synthesis layer when needed | failure-midpoint frame with red dot at Pass-2 point |

**Rule:** every phase writes the full artifact it produces; every dispatch logs the full call. The dashboard recovers session state purely from disk — replay of an old `mirror_root/` reproduces the same UI.

---

## 7. Project status

Past the original 48-hour sprint. State of the world:

### Done

- **Plan-A pipeline end-to-end.** ONE Managed Agents session, four phases (planner / rollout / judge / report), multi-tool `requires_action` cycles handled correctly, all four phases reach `end_turn` on smoke runs.
- **Both populations on Lift, both working.** Scope-cut from the earlier Lift + Nut mix to **Lift-only across both cohorts**. Calibration = scripted Lift with injected output knobs; deployment = pretrained Lift BC-RNN under `cube_xy_jitter_m` environmental perturbation (widens the `UniformRandomSampler` xy range from ±3 cm default to ±15 cm for demo runs). BC-RNN verified **8/8 success at `cube_xy_jitter_m=0.0`**, **38% failure at 0.15 m** (clean OOD stress test). Same-task calibration means P/R numbers actually transfer to deployment findings. Post-success hold of 20 frames so clean rollouts show "cube clearly held aloft" — fixes a Pass-1 false-positive class.
- **Two-pass vision judge.** Pass-1 at 24 frames × 768 px (denser than initial 14, prompt asks for the *earliest* failure window not the consequence frame). Pass-2 at 14 frames × 2576 px windowed on the coarse range with 8-frame padding, Pass-2 frames encoded as JPEG (fits the 32 MB request cap), prompt explicit about temporal reasoning between adjacent frames and named anti-bias against `default-to-approach_miss`.
- **Cost + wall-time accounting.** `src/costing.py` tracks Opus 4.7 token usage live, computes manual-review baseline ($75/hr × 3 min/rollout for cost, sum of video durations + 60 s/rollout for wall time), surfaces both as the headline banner.
- **Dashboard.** Live tab (chat + current rollout video + rich gallery), Judge calibration tab (cohort pills + binary panel with Wilson 95% CI + multiclass heatmap + per-label table + drill-down filter), Deployment findings tab with **Judge Trust banner** at the top + cluster cards decorated with calibration-precision chips (no longer carry the "(Lift)" parenthetical — both cohorts are Lift). Phase progress strip below the banner shows X/N for each phase live. Population chips (amber / steel-blue) on every rollout card.
- **Plain-language agent messages.** System prompt includes a translation table — agent.message events translate "knob" → "failure-injection parameter", "scripted policy" → plain English, `cube_xy_jitter_m` → "cube placement perturbation", etc. Internal thinking can stay technical.

### Open methodology questions
- **Engineered vs natural failure distribution.** Even with same-task calibration, scripted-injected failures look visually distinct from BC-RNN natural failures (the engineered ones are obvious; natural ones are subtle). A small human-labeled set is the only true cure; we can defer this if we lean into the floor framing in the demo narrative.
- **Sub-second event resolution.** Vision tuning shipped (24 / 14 frames + earliest-failure prompt) targets the over-collapse to `approach_miss` we observed. Pending validation on a fresh smoke run. If still weak, escalation paths are: hierarchical zoom-and-refine (two-stage coarse), pixel-difference-driven adaptive sampling, or a frame-tiling experiment. **Native video input is NOT supported on Opus 4.7** — confirmed via SDK + docs (no `VideoBlockParam`, only image MIME types). Don't spend time on that lever.

### Remaining for the demo recording

- README.md polish (positioning one-liner, architecture diagram, install, headline numbers).
- `docs/demo_script.md` — shot list (use the new tab structure: open on Live, cut to Judge calibration mid-run, close on Deployment findings with the Judge Trust banner).
- 100–200 word written hackathon summary.
- Cost-tracker validation — one 3-row probe and compare banner number to Anthropic console; ship if within 10%.
- Final cleanup pass: dead code removal (a few orphaned helpers in `src/ui/app.py`), TODO sweep, debug-print scan.
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

# smoke: full Plan-A end-to-end (HITS REAL ANTHROPIC API — ~$18 / 15 min for 16 rollouts)
python scripts/smoke_agent.py

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

**Vision.** Up to 2576 px long edge. Supports pointing (returns pixel coordinates that map 1:1 to the submitted image) and bounding-box localization. Use both passes per §3.

**No native video input.** Confirmed via the SDK (no `VideoBlockParam`, only `image/{jpeg,png,gif,webp}` MIME types) and the docs. Frame sampling is the only path. The Files API doesn't bridge video on Opus 4.7 either. Don't waste time chasing this lever.

**Research preview (do NOT build the critical path on these):** multi-agent (`callable_agents`), `outcomes`, cross-session memory. If access arrives in time, Plan B is a config change per §3.

**Rate limits:** 60 create/min, 600 read/min per org. We run one session per eval — not a concern.

---

## 11.5 Cost accounting and baseline

We track every Anthropic call's tokens via `src/costing.py::CostTracker`. Pricing:

- Opus 4.7 input: **$15 / Mtok** · output: **$75 / Mtok** · cache read: **$1.50 / Mtok** · cache write: **$18.75 / Mtok**

Per-rollout cost on the agent flow is **~$1.15** (mixed 8 cal + 8 dep Lift eval, 16 rollouts → $18.38 on the post-scope-cut smoke run of 2026-04-24, with the denser vision sampling we ship). Was ~$0.60 before the vision tuning bumped Pass-1 from 14→24 frames and Pass-2 from 10→14 frames. **Confirm before any agent-flow run greater than ~5 rollouts** — the auto-memory `project_smoke_run_costs.md` notes the same.

The dashboard shows live cost vs two baselines:

- **Cost baseline:** $75/hr × 3 min/rollout (loaded labor cost — engineer reviews video, classifies failure, takes notes). Constants in `src/costing.py`. Edit `BASELINE_HOURLY_RATE_USD` / `BASELINE_SECONDS_PER_ROLLOUT` to retune.
- **Time baseline:** sum of actual video durations + 60 s/rollout review overhead. Closer to "wall time a sequential reviewer would take to watch" than the cost baseline. Helper: `baseline_time_seconds_for_videos`.

The Live banner renders both as side-by-side columns + a green "Cost saved / Time saved" footer. Headline numbers in the demo recording come from the actual session — never fabricate.

The cost tracker is in **flight-tested but not formally validated** state — known unknown is whether session-event tokens (planner, reporter reasoning) get fully captured or only the Messages-API vision passes. A 5-row probe + Anthropic-console comparison closes this; do it before the demo.

---

## 12. Pivot plan (read before panicking)

If MuJoCo or robosuite fights us past Saturday noon:

1. Delete `src/sim/` internals; replace `adapter.py` with a thin reader over pre-recorded robot failure videos (YouTube robot-fail reels, Open X-Embodiment clips, RoboNet).
2. `RolloutConfig` becomes `VideoConfig`. `RolloutResult` stays identical.
3. The orchestrator, vision judge, metrics, and report writer do not change.
4. Reframe in README + demo as **"Manipulation Failure Forensics"** — applies to sim rollouts and real robot logs alike. Arguably a better product.

The judges score layers 3 and 4. We can lose layer 1 and still win.

---

## 13. Demo video plan

Full shot list in `docs/demo_script.md`. Principles:

- **Open with the pain, not the product.** "Every robotics team burns weeks on evals. This took ~`<wall_time>`, cost ~`<cost>`, and reports its own judge precision against synthetic ground truth." Numbers come from the recording-day smoke — fill in after.
- **Live cost / time / scenarios banner visible from second 1.** Show `Scenarios: N (n_cal cal + n_dep dep)` so the dual-population framing lands immediately.
- **Population chips on every rollout.** Amber `Calibration` and blue `Deployment` are the visual signature — make sure both colors appear on screen within the first 30 seconds.
- **Exactly one Pass-2 annotation at full 2576 px** with the red dot overlay visible. Show the keyframe in the Deployment findings synthesis card, click to open the source mp4.
- **HERO SHOT: the Judge Trust banner reveal.** When Phase 3 completes, the Deployment findings tab populates the trust banner with measured calibration P/R numbers. This is the "judges lean forward" moment — it visually connects the synthetic calibration on Lift to the trust we have in the deployment labels on the SAME Lift task under environmental perturbation (both cohorts are Lift now; the calibration P transfers directly). Cut to it on a clean transition, hold for 2-3 seconds.
- **Close on measured numbers:** `<cost> · <scenarios> total (n_cal cal / n_dep dep) · Pass-1 precision <X>% · Pass-1 recall <Y>% · Pass-2 label accuracy <Z>%`. Real numbers from the recording-day smoke — never aspirational.
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

---

## 16. Known pitfalls

- **MuJoCo on macOS Apple Silicon.** Try `MUJOCO_GL=glfw` first, fallback `egl`. Document whatever works in `docs/install-mujoco-macos.md` the moment it works.
- **Multiprocessing.** Use `get_context("spawn").Pool`, **never fork** — MuJoCo contexts are not fork-safe. Each worker must create its own env; envs are not pickle-safe across processes. Sequential fallback is fine (< 15 min for 30 rollouts).
- **robomimic obs shapes.** Must match the checkpoint's training config. Stick to the canonical Lift observation set (`robot0_eef_pos`, `robot0_eef_quat`, `robot0_gripper_qpos`, `object`); robosuite emits `object-state` and we alias it to `object` in `src/sim/pretrained.py::RobomimicPolicy.act`. Wrap any future mismatch there, never fork the policy.
- **Opus 4.7 literalism.** More literal than 4.6. Be explicit in system prompts; do not expect the model to generalize from one item to another unprompted.
- **Silent 4.7 breakages.** §11 list. Verify any 4.6-era snippet before reusing.
- **Tokenizer change.** Up to ~35% more tokens for the same text. Adjust `max_tokens` and `task_budget` upward vs 4.6 baselines.
- **Cross-task calibration drift — resolved.** Prior design calibrated on Lift and deployed on NutAssemblySquare, so the calibration number was at best a floor on the deployment number. Post scope-cut we run BOTH cohorts on Lift (calibration = scripted policy + output knobs; deployment = BC-RNN + `cube_xy_jitter_m` environmental perturbation), so the per-label calibration precision can legitimately decorate deployment findings. Deployment-finding chips no longer carry the `(Lift)` parenthetical. The remaining gap — engineered-vs-natural failure distribution — is documented in `@docs/eval_methodology.md` and only closable with a human-labeled set.
- **robosuite version pin.** We pin `robosuite==1.4.1` in `requirements.txt`. Robosuite 1.5's composite-controller rewrite re-scales the 1.4-trained BC-RNN's delta actions into garbage (symptom: arm rises away from cube with gripper closed from step 0, 0/16 success). Stanford publishes only 1.5-compatible *datasets*, not re-trained checkpoints — upstream context in robomimic issues #259 / #283. 1.4.1 is pure Python on the DeepMind mujoco bindings and installs cleanly on Python 3.12 arm64. Don't upgrade robosuite without also re-validating the BC-RNN succeeds at `cube_xy_jitter_m=0.0`.
- **Frame sampling vs sub-second events.** Pass-1 at 24 frames covers ~0.4 s/frame on a 10 s clip. Failures shorter than a frame interval (e.g. a brief gripper-knock) can be missed — Pass-1 then returns the consequence frames (arm retreating) and Pass-2 mis-labels what it sees there. The current prompt explicitly asks Pass-1 for the *earliest* failure window and walks Pass-2 through temporal reasoning, but the underlying sampling limit is real. Escalation paths if the prompt fix isn't enough: hierarchical zoom-and-refine (two-stage coarse), pixel-difference-driven adaptive sampling, frame tiling. Native video isn't an option (see §11).

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