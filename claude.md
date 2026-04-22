# CLAUDE.md — Embodied Eval Orchestrator

> Project memory for Claude Code. Keep this file lean and high-signal.
> Put anything that only matters sometimes in `docs/` and reference with `@docs/filename.md`.

---

## 1. North Star

**Positioning (also the README one-liner):** An agentic system that runs and analyzes robot manipulation policy evaluations end-to-end, reducing manual eval-video review from hours to minutes.

Submitted to the Anthropic Opus 4.7 Hackathon.

**How it works.** Describe an evaluation goal in English → an Opus 4.7 Managed Agent designs a test suite, runs parallel rollouts in simulation (mixing pretrained policy and scripted policies with *injected* failure modes), watches the resulting videos in two passes (coarse then high-resolution), annotates failure frames with pixel-accurate pointing, clusters findings, and emits a report with **measured agreement against ground-truth injected failures**. Minutes, a few dollars, fully auditable trail.

**Why it matters.** Robotics teams spend weeks hand-crafting eval suites and watching rollouts. We replace that labor with an agentic pipeline that scales horizontally and reports its own precision/recall — a real "eval the eval" story, not a vibes demo.

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
┌─────────────────────────────────────────────────┐
│ Layer 4: UI (Gradio)                            │
│  Chat / sim grid / /memories viewer / report +   │
│  LIVE banner: spend · elapsed · scenarios run    │
└─────────────────────────────────────────────────┘
                       ▲
┌─────────────────────────────────────────────────┐
│ Layer 3: ONE Managed Agents session (Opus 4.7)   │
│  Planner phase   → /memories/plan.md, matrix.csv │
│  Rollout phase   → /memories/rollouts/*.mp4      │
│  Vision judge    → two-pass, findings.jsonl      │
│    Pass 1 coarse (~768px, 12–16 frames)          │
│    Pass 2 fine   (2576px, windowed, pointing)    │
│  Clustering+report → report.md, charts.png       │
└─────────────────────────────────────────────────┘
                       ▲
┌─────────────────────────────────────────────────┐
│ Layer 2: Policies under test                     │
│  robomimic BC-RNN pretrained (NutAssemblySquare) │
│  Scripted IK picker with injected failure modes  │
│    → ground-truth labels for precision/recall    │
└─────────────────────────────────────────────────┘
                       ▲
┌─────────────────────────────────────────────────┐
│ Layer 1: robosuite + MuJoCo                      │
│  NutAssemblySquare (demo) / Lift (smoke only)    │
└─────────────────────────────────────────────────┘
```

**Hard interface discipline.** The orchestrator never imports MuJoCo or robosuite directly. It calls `sim.run_rollout(config) -> RolloutResult` via `src/sim/adapter.py`. The adapter wraps both the pretrained policy and the scripted-failure policy behind one `Policy` interface. This is what lets §12's pivot (`.mp4` files instead of sim) swap in without touching agent code, *and* what lets Plan B swap in without touching sim code.

---

## 4. Tech stack (pinned)

- **Language:** Python 3.12.
- **Model:** `claude-opus-4-7`. See §11 for breaking changes vs 4.6.
- **Agent runtime:** Claude Managed Agents, beta header `managed-agents-2026-04-01`.
- **Simulator:** `mujoco` + `robosuite` ≥ 1.5. Primary env: **NutAssemblySquare** (pretrained BC-RNN ~82% success → ~18% visually rich failures: misalignment, slip during insertion, wrong-nut selection). `Lift` is for Saturday-morning smoke tests only (too reliable for demo).
- **Policy — pretrained:** `robomimic` v0.3.0 (latest on PyPI as of 2026-04-22; v0.4.0 referenced in earlier drafts of this doc does not exist on PyPI) with a pretrained BC-RNN checkpoint for NutAssemblySquare. Checkpoint source TBD — verify whether it lives on HuggingFace or the historical Stanford CDN before relying on a download path. Note: robomimic 0.3.0 was trained against robosuite 1.4.x; obs-spec drift to 1.5 is the known sharp edge — wrap any mismatch in `src/sim/pretrained.py`, never fork the policy. Do **not** use LeRobot — its policies target ALOHA / Koch / SO-100, not Franka Panda, and the obs/action shapes don't match.
- **Policy — scripted with injected failures:** `src/sim/scripted.py`. Parameterized failure modes: `action_noise ∈ {0.0, 0.05, 0.15}`, `gripper_close_prematurely ∈ {True, False}`, `approach_angle_offset ∈ {0°, 15°}`, `grip_force_scale ∈ {0.3, 1.0}`. Each config has a known ground-truth label. This is how we measure the vision judge. Details in `docs/eval_methodology.md`.
- **UI:** `gradio` ≥ 4.x. Three panes plus a live `$X.XX · Y:ZZ · N scenarios` banner. No custom React this weekend.
- **Video:** `imageio-ffmpeg` for `.mp4`; frame sampling via `opencv-python` if needed.
- **Plotting:** `matplotlib`. Boring and legible.
- **Testing:** `pytest`, `pytest-asyncio`.
- **Env:** `uv`. Pin everything in `requirements.txt`. No conda.

**Do not add a dependency without asking first.** Every new dep is a potential Saturday-morning install failure.

---

## 5. Directory layout

```
repo/
├── CLAUDE.md
├── README.md                     # positioning + architecture + demo gif
├── requirements.txt
├── pyproject.toml
├── .env.example                  # ANTHROPIC_API_KEY, HF_TOKEN, MUJOCO_GL
├── src/
│   ├── agents/
│   │   └── system_prompts.py     # planner/rollout/judge/report phase prompts
│   ├── sim/
│   │   ├── adapter.py            # run_rollout(config) -> RolloutResult
│   │   ├── envs.py               # robosuite env factories
│   │   ├── policies.py           # Policy interface
│   │   ├── pretrained.py         # robomimic BC-RNN loader
│   │   └── scripted.py           # IK picker with injected failures
│   ├── vision/
│   │   ├── coarse_pass.py        # 768px, 12–16 frames, binary + range
│   │   └── fine_pass.py          # 2576px, windowed, pointing + taxonomy
│   ├── orchestrator.py           # builds + runs the Managed Agents session
│   ├── memory_layout.py          # canonical /memories/ paths
│   ├── schemas.py                # Pydantic: RolloutConfig, RolloutResult, Finding
│   ├── metrics.py                # precision/recall against injected ground truth
│   ├── ui/app.py                 # Gradio entrypoint
│   └── cli.py
├── tests/
│   ├── test_schemas.py
│   ├── test_sim_adapter.py
│   ├── test_scripted_failure_injection.py
│   ├── test_metrics.py
│   └── fixtures/
│       └── injected_failures/    # ground-truth labels for tests
├── scripts/
│   ├── smoke_render.py           # MUJOCO_GL sanity check (RUN FIRST)
│   ├── smoke_rollout.py          # one rollout end-to-end
│   ├── smoke_agent.py            # one short agent session
│   └── record_demo.py
├── docs/
│   ├── architecture.md
│   ├── eval_methodology.md       # scenario selection, seeds, human baseline
│   ├── opus-4-7-gotchas.md       # breaking changes, migration notes
│   ├── prompts.md                # agent system prompts, versioned
│   ├── demo_script.md            # 3-minute shot list
│   ├── install-mujoco-macos.md   # written the first time we debug it
│   └── postmortem.md
└── artifacts/                    # per-session, gitignored
    └── sessions/<session_id>/
        ├── rollouts/*.mp4
        ├── annotated/*.png
        ├── plan.md
        ├── test_matrix.csv
        ├── findings.jsonl
        └── report.md
```

---

## 6. Memory layout (canonical paths)

The Managed Agent writes to `/memories/` in its container. We mirror to `artifacts/sessions/<id>/` for the UI. Any code reading/writing these paths imports from `src/memory_layout.py` — never hardcode strings.

| Path | Owner | Contents |
| --- | --- | --- |
| `/memories/plan.md` | planner | test matrix intent, success criteria, budget, policy choice |
| `/memories/test_matrix.csv` | planner | one row per scenario, deterministic seed, injected-failure flag |
| `/memories/taxonomy.md` | planner | pre-defined failure labels (see §7 Sat PM) |
| `/memories/rollouts/` | rollout worker | `.mp4` + `.json` per scenario |
| `/memories/findings.jsonl` | vision judge | one line per rollout: pass 1 verdict + pass 2 annotation |
| `/memories/report.md` | report writer | final markdown deliverable |
| `/memories/notes/` | any phase | scratchpad, cross-phase notes |

**Rule:** every phase writes the full artifact it produces. No implicit state. If the session is resumed, reading `/memories/` is enough to orient.

---

## 7. 48-hour execution plan

Track progress here. Update checkboxes as we go.

### Saturday AM — foundations (aim: 4 hours) — resequenced to de-risk env first

- [ ] **H1: `scripts/smoke_render.py`** — MUJOCO_GL smoke test. Try `glfw` first on macOS, fallback to `egl`. Render one frame offscreen from a fresh robosuite env and write `.png`. **If this burns > 60 min, skip to §12 pivot.**
- [ ] **H2: robomimic install + one pretrained rollout.** Load BC-RNN checkpoint for NutAssemblySquare, run one episode, write `.mp4`, confirm success flag matches episode outcome.
- [ ] **H2 (parallel): Scripted IK picker.** `src/sim/scripted.py` with failure-mode parameters and ground-truth label emission.
- [ ] **H3: `src/sim/adapter.py` + Pydantic schemas.** Single interface wrapping both policies.
- [ ] **H4: Parallelism smoke test.** `multiprocessing.get_context("spawn").Pool` with 4 workers, each creating its own env. If parallel fails, document the sequential fallback (30 scenarios × ~15s = < 8 min, fine for demo) and move on.
- [ ] `ruff check && ruff format && mypy src/ && pytest -q` green.

### Saturday PM — the brain (aim: 6 hours)

- [ ] Write `src/agents/system_prompts.py` — phase markers for planner / rollout / judge / report inside ONE Managed Agents session
- [ ] Planner phase reads goal → writes `/memories/plan.md` + `test_matrix.csv` (clean + injected rows mixed, ground-truth column kept *inside matrix* so agent sees it only when we want)
- [ ] Rollout phase consumes matrix, runs scenarios, writes `.mp4`s
- [ ] **Pre-defined failure taxonomy** in `/memories/taxonomy.md`: `approach_miss`, `premature_release`, `slip_during_lift`, `knock_object_off_table`, `wrong_object_selected`, `insertion_misalignment`, `gripper_collision`, `other`. Judge must emit labels from this set.
- [ ] **Vision judge two-pass:**
  - Pass 1 (coarse): sample 12–16 evenly-spaced frames at ~768px, ask for `{verdict: pass|fail, failure_frame_range: [start, end]|null}`.
  - Pass 2 (fine, only on failed rollouts): sample 8–12 frames at **2576px** windowed on the failure range, ask for `{taxonomy_label, point: [x,y], one_line_description}`.
- [ ] End-to-end on 5 scenarios (mix of clean + injected).

### Saturday evening — make it visible (aim: 3 hours)

- [ ] Gradio UI: chat pane / sim-grid pane / `/memories` tree pane
- [ ] **Live banner from second 1**: `$X.XX spent · Y:ZZ elapsed · N / total scenarios`
- [ ] Stream Managed Agents events live
- [ ] Render Pass-2 annotations (points / bboxes) over frames

### Sunday AM — measurement + polish (aim: 5 hours)

- [ ] `src/metrics.py` — precision/recall of judge labels vs injected ground truth
- [ ] **Clustering via ONE final Opus 4.7 call** with full `findings.jsonl` in the 1M-context window. Output: 3–6 labeled clusters with counts and a representative frame per cluster. **Do not implement k-means.**
- [ ] Report writer produces `report.md` with matplotlib bar chart of cluster frequencies + precision/recall table
- [ ] Scale run to 30+ scenarios (≥50% with injected failures) without crashing

### Sunday PM — demo artifacts (aim: 4 hours)

- [ ] README.md polished: positioning one-liner, architecture diagram, demo gif, install, cost/time quote
- [ ] `docs/demo_script.md` — exact shot list
- [ ] `docs/eval_methodology.md` finalized
- [ ] Record 3-minute video
- [ ] 100–200 word written summary
- [ ] Final cleanup: no TODOs, no commented-out code, no debug prints

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

# smoke: render one frame (RUN FIRST, Saturday morning)
MUJOCO_GL=glfw python scripts/smoke_render.py

# smoke: one rollout, no agent
python scripts/smoke_rollout.py

# smoke: short agent session, 3 scenarios
python scripts/smoke_agent.py --goal "grade pick reliability"

# full UI
python -m src.ui.app

# record demo
python scripts/record_demo.py --output demo.mp4
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

**Vision.** Up to 2576 px long edge. Supports pointing (returns pixel coordinates that map 1:1 to the submitted image) and bounding-box localization. Use both passes per §7.

**Research preview (do NOT build the critical path on these):** multi-agent (`callable_agents`), `outcomes`, cross-session memory. If access arrives in time, Plan B is a config change per §3.

**Rate limits:** 60 create/min, 600 read/min per org. We run one session per eval — not a concern.

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

- Open with the pain, not the product. "Every robotics team burns weeks on evals. This took 11 minutes, cost $3, and agreed with ground truth 91% of the time."
- **Live cost / time / scenarios banner visible from second 1** — not retroactive.
- Show `/memories/` filling up live. An agent thinking to disk is a judge moment.
- **Exactly one** Pass-2 annotation must land on screen at full 2576px, with the point overlay visible.
- **Close on measured numbers:** `$2.87 · 32 scenarios · 4 failure modes · Precision 91% · Recall 87%`. This is the "TPM slide" frame.
- 3:00 hard cap.

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

---

## 16. Known pitfalls

- **MuJoCo on macOS Apple Silicon.** Try `MUJOCO_GL=glfw` first, fallback `egl`. Document whatever works in `docs/install-mujoco-macos.md` the moment it works.
- **Multiprocessing.** Use `get_context("spawn").Pool`, **never fork** — MuJoCo contexts are not fork-safe. Each worker must create its own env; envs are not pickle-safe across processes. Sequential fallback is fine (< 15 min for 30 rollouts).
- **robomimic obs shapes.** Must match the checkpoint's training config. Stick to canonical NutAssemblySquare observations; wrap adapters in `src/sim/pretrained.py`, never fork the policy.
- **Opus 4.7 literalism.** More literal than 4.6. Be explicit in system prompts; do not expect the model to generalize from one item to another unprompted.
- **Silent 4.7 breakages.** §11 list. Verify any 4.6-era snippet before reusing.
- **Tokenizer change.** Up to ~35% more tokens for the same text. Adjust `max_tokens` and `task_budget` upward vs 4.6 baselines.

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