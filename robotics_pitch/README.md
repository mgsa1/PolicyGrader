# robotics_pitch — Remotion explainer

A 40-second animated explainer for **Embodied Eval Orchestrator**, rendered with
[Remotion](https://www.remotion.dev/). Output target:
[`../docs/media/hero.mp4`](../docs/media/hero.mp4) — wired into the main repo
README's hero slot.

## What it shows

| Beat | Time | Scene |
|------|------|-------|
| 1 | 0–4 s | **Title** — "Embodied AI is everywhere. Evaluating it isn't." |
| 2 | 4–10 s | **Pain** — 25 rollout thumbnails get "watched" one by one; counter ticks to **$15 000 · 200 h**. |
| 3 | 10–20 s | **Pipeline** — five phase cards (planner / rollout / labeling / judge ×K / reporter) animate in with their artifacts. |
| 4 | 20–28 s | **Two populations** — amber calibration vs. blue deployment, both on Lift. *"Calibration precision transfers."* |
| 5 | 28–34 s | **Judge** — `dep_14` with pulsing red ring at the contact pixel · `dep_04` shows `point=null`. *"Names the failure. Points. Or honestly abstains."* |
| 6 | 34–40 s | **Numbers** — pipeline `$4 650 · 48 h`, baseline `$15 000 · 200 h`, **saved $10 350**. |

## Headline numbers — coherent ~$10 K savings

Per-rollout factors are **real**, taken from
`artifacts/runs/evalb_d5f0ad/runtime.json` (the most recent complete run):

| Per-rollout | Pipeline | Manual |
|---|---|---|
| Cost | $1.164 | $3.75 |
| Time | 43.6 s | 180 s |

Scaled to **N = 4 000 scenarios** (a realistic pre-deployment sweep size):

| | Pipeline | Manual baseline | Δ |
|---|---|---|---|
| Cost | **$4 650** | $15 000 | **−$10 350** |
| Wall time | **~48 h** | ~200 h (≈ 5 work-weeks) | **−152 h** |

Ratios: **0.31× cost · 0.24× time**. Constants live in
[src/theme.ts](src/theme.ts) under `numbers`.

## Run it

```bash
cd robotics_pitch
npm install         # ~1–2 min, ~250 MB

# Hot-reloading studio (best for editing scenes)
npm run dev
# opens http://localhost:3000

# One-shot render to ../docs/media/hero.mp4 (1920×1080 · 30 fps · h264)
npm run render

# Poster frame for README static fallback
npm run render:poster

# Smaller GIF for README inline (~12 MB)
npm run render:gif
```

The first render downloads a Chromium build (~120 MB) into `~/.cache/`. Render
takes ~2–4 min on Apple Silicon, ~6 min on Intel.

## Project layout

```
robotics_pitch/
├── package.json
├── tsconfig.json
├── remotion.config.ts            # h264 · yuv420p · jpeg image format
├── src/
│   ├── index.ts                  # registerRoot
│   ├── Root.tsx                  # <Composition id="Hero" />
│   ├── Hero.tsx                  # 40-s timeline, 6 sequenced scenes
│   ├── theme.ts                  # tokens.css mirror + scaled numbers
│   ├── components/
│   │   ├── Topbar.tsx            # PG monogram + hackathon chip (persistent)
│   │   ├── PhaseCard.tsx         # one phase card with artifact reveal
│   │   └── easing.ts             # spring + bezier helpers
│   └── scenes/
│       ├── TitleScene.tsx        # 0–4 s
│       ├── PainScene.tsx         # 4–10 s · 5×5 thumbnail wall
│       ├── PipelineScene.tsx     # 10–20 s · five phase cards
│       ├── PopulationsScene.tsx  # 20–28 s · amber / blue split
│       ├── JudgeScene.tsx        # 28–34 s · point + abstain
│       └── NumbersScene.tsx      # 34–40 s · final reveal
└── public/
    └── keyframes/                # 25 PNGs from artifacts/runs/evalb_d5f0ad
        ├── cal_00.png … cal_09.png
        └── dep_00.png … dep_14.png
```

## Editing tips

- **Composition is registered as `Hero`.** Run `npm run dev` and the studio
  opens at `localhost:3000`. Scrub the timeline freely; every scene is
  `useCurrentFrame()`-driven.
- **All colors come from `src/theme.ts`** — change one value, the whole video
  re-skins. Tokens mirror `/tokens.css` (the Gradio dashboard's design
  system).
- **The headline numbers** live in `theme.ts → numbers`. Change the per-rollout
  factor or the scenario count and the Pain + Numbers scenes track
  automatically.
- **Add or swap keyframes** by dropping new PNGs in `public/keyframes/` and
  updating the arrays in `PainScene.tsx` and `PopulationsScene.tsx`.
- **Audio:** none included. To add a track, drop an mp3 in `public/` and
  `<Audio src={staticFile("track.mp3")} />` from `Hero.tsx`.

## Why these scaling numbers?

A pre-deployment sweep at a serious robotics lab is hundreds-to-thousands of
rollouts. Our hackathon smoke is 25; the sweep size in the explainer is
**4 000** — a believable upper bound for "pre-launch, all policies, all
seeds". The savings line scales linearly because the eval orchestrator's
per-rollout cost and wall-time both scale linearly (rollout phase is
sequential on the host main thread; judge phase fans out). At 4 000 rollouts
we cross **$10 000 saved per sweep** — the round-number anchor for the demo.

The factor underneath (`$2.586 / rollout` saved) is real. The N is plausible.
The total is honest.
