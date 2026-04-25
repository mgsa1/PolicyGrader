# PolicyGrader

> **One prompt in. A full control policy stress test out.**
> An agentic system that designs, runs, judges, and reports on robot policy evaluations end-to-end, while measuring its own judge against human ground truth.

<p>
  <a href="#"><img alt="Claude Opus 4.7" src="https://img.shields.io/badge/Claude-Opus%204.7-0b5fff?style=flat-square&labelColor=1f1f1f"></a>
  <a href="#"><img alt="Managed Agents" src="https://img.shields.io/badge/Managed%20Agents-2026--04--01-1967d2?style=flat-square&labelColor=1f1f1f"></a>
  <a href="#"><img alt="robosuite 1.4.1" src="https://img.shields.io/badge/robosuite-1.4.1-b06000?style=flat-square&labelColor=1f1f1f"></a>
  <a href="#"><img alt="Python 3.12" src="https://img.shields.io/badge/Python-3.12-3776ab?style=flat-square&labelColor=1f1f1f"></a>
</p>

<!-- HERO ANIMATION — two panoramic loops (cards + data-flow), click-through to the full explainer.
     Rendered by `robotics_pitch/` (Remotion). Re-render with:
       cd robotics_pitch && npm run render:pipeline-cards-gif   # → docs/media/pipeline-cards.gif
       cd robotics_pitch && npm run render:pipeline-flow-gif    # → docs/media/pipeline-flow.gif
       cd robotics_pitch && npm run render                      # → docs/media/hero.mp4 -->

<p align="center">
  <a href="docs/media/hero.mp4">
    <img src="docs/media/pipeline-cards.gif" alt="Five-phase pipeline: planner · rollout · labeling · judge · reporter" width="100%" />
  </a>
</p>
<p align="center">
  <a href="docs/media/hero.mp4">
    <img src="docs/media/pipeline-flow.gif" alt="Data flow: prompt → rollouts → K parallel judges → report" width="100%" />
  </a>
  <br/>
  <sub>▶ <a href="docs/media/hero.mp4">Play the full explainer</a> &middot; source in <a href="robotics_pitch/"><code>robotics_pitch/</code></a></sub>
</p>

---

## The pitch

Embodied AI is about to be everywhere — warehouses, kitchens, hospitals, homes. Every policy that ships has to be **stress tested** first, and stress test today is a robotics engineer watching rollout videos frame-by-frame for hours.

**PolicyGrader collapses that loop into minutes.** Describe the eval goal in English; an Opus 4.7 Managed Agent designs a test suite, runs rollouts in simulation, **pauses for a human to label a sampled subset** as ground truth, then a vision judge watches every failed rollout, names the failure frame, points at it (or honestly abstains), and a reporter clusters the deployment failures into actionable patterns.

We propose a framework to benchmark the judge performance against a small sample of human labelled ground truth, to provide a confidence index in the vision analysis in the deployment.

---

## Headline numbers — last full run

70 rollouts (20 calibration + 50 deployment) on Lift. Reproducible from [artifacts/runs/eval_d5a040/](artifacts/runs/eval_d5a040/) — `runtime.json`, `findings.jsonl`, [`report.md`](artifacts/runs/eval_d5a040/report.md).

| | **Pipeline** | Manual baseline | Δ |
|---|---|---|---|
| **Cost** | **$13.30** | $175.00 | **13× cheaper** |
| **Wall time** | **31 m 40 s** | 1 h 17 m | **2.4× faster** |
| **Judge findings** | 27 `missed_approach` · 3 `failed_grip` · 28 / 30 with pixel-accurate point | — | — |

Wall time on this laptop run is bottlenecked by single-process MuJoCo rollout generation. The AI grading work itself runs across K parallel Claude Managed Agents, so in a real deployment the pipeline's speed is bounded by the number of agents you fan out to, not by the host machine.

---

## The two populations — load-bearing

Both cohorts run on **the same task, env, and camera (Lift, frontview)**. That’s what lets the per-label judge precision measured on calibration *transfer* directly onto deployment findings.

| | **Calibration** (amber) | **Deployment** (steel blue) |
|---|---|---|
| Policy | Scripted IK picker with knobs steering toward specific failure modes | Pretrained robomimic BC-RNN (`lift_ph_low_dim.pth`) |
| Source of failures | Injected (`action_noise`, `angle_deg`, `premature_close`, `grip_scale`) | Environmental — `cube_xy_jitter_m` widens cube placement from ±3 cm to ±15 cm |
| Ground truth | **Human labels** on a sampled subset — `clamp(10 % × N, 6, 20)`, stratified | Inherits the calibration-level trust; not independently labeled |
| Role | Measures the judge’s P/R | The thing we actually want to know about |

A calibration cohort with no ground truth gives you a vibes demo. Cross-task calibration gives you a P/R that doesn’t transfer. **Same-task calibration with human labels gives you a precision number you can attach to every deployment finding.** Full framing + limitations in [docs/eval_methodology.md](docs/eval_methodology.md).

---

## Three Opus 4.7 capabilities, used visibly

1. **2576-px vision with pointing.** The judge points at the failure on the keyframe, with `point = null` as a first-class output for no-contact failures.
2. **1M-context window.** The reporter clusters across the full `findings.jsonl` in a single pass — no k-means, no embeddings, just the model holding all 70 rollouts in its head at once.
3. **Managed Agents parallelism.** Four phases run as four separate sessions; the judge fans out to K workers in parallel.

Each phase’s `/memories/` is isolated; sessions hand artifacts back to the host via `submit_plan` / `submit_results` / `submit_findings` / `submit_report` tools that write to `mirror_root/`.

---

## Quickstart

**Prereqs.** macOS or Linux · Python 3.12 · Anthropic API key with Opus 4.7 + Managed Agents access · ~1 GB disk. **No GPU.**

```bash
git clone <this-repo> && cd Robotics
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt

cp .env.example .env                          # set ANTHROPIC_API_KEY
python scripts/fetch_checkpoints.py           # ~100 MB BC-RNN .pth

python scripts/smoke_agent.py                 # full pipeline, ~5 min, ~$15
python scripts/run_ui.py                      # dashboard at localhost:7860
```

<details>
<summary>Sanity gate, smoke variants, lint &amp; test</summary>

Run the BC-RNN sanity gate before any agent run — $0, ~30 s. If this fails, `robosuite` was likely upgraded past 1.4.1 and a smoke run will burn money for nothing.

```bash
MUJOCO_GL=glfw python -c "
import sys; sys.path.insert(0,'.')
from pathlib import Path
from src.schemas import RolloutConfig
from src.sim.adapter import run_rollout
ck = Path('artifacts/checkpoints/lift_ph_low_dim.pth')
ok = sum(run_rollout(RolloutConfig(rollout_id=f's{s}', policy_kind='pretrained',
                                    env_name='Lift', seed=s, max_steps=200,
                                    checkpoint_path=ck), video_out=None).success for s in range(3))
assert ok == 3, f'sim stack broken — {ok}/3'
"
```

API-free smokes:

```bash
MUJOCO_GL=glfw python scripts/smoke_render.py              # one frame
MUJOCO_GL=glfw python scripts/smoke_scripted_rollout.py    # one scripted Lift rollout
MUJOCO_GL=glfw python scripts/smoke_pretrained_rollout.py  # one BC-RNN rollout
MUJOCO_GL=glfw python scripts/smoke_pretrained_rollout.py --sweep   # jitter sweep
```

`smoke_agent.py` flags: `--k-workers` (judge fan-out, default 4) · `--skip-labeling` (unattended runs) · `--run-id` · `--goal` · `--label-seed`.

Lint, type, test (run before every commit):

```bash
ruff check . && ruff format . && mypy src/ && pytest -q
```

</details>

---

## Acknowledgements

**Anthropic** for Opus 4.7, the Managed Agents harness, and research-preview parallel sessions. **Stanford / robomimic & robosuite teams** for the BC-RNN baseline and the Lift checkpoint (Mandlekar et al. 2021). **DeepMind / MuJoCo** for the simulator. **maaurin**, my other GitHub account that I do not know how to log out from. Submitted to the **Anthropic Opus 4.7 Hackathon**.
