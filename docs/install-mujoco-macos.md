# MuJoCo + robosuite on macOS Apple Silicon

What worked, first try, on macOS 15.7.3 (Sequoia) / arm64 / M-series:

```bash
uv venv --python 3.12 .venv
source .venv/bin/activate
uv pip install -r requirements.txt
MUJOCO_GL=glfw python scripts/smoke_render.py
```

Versions installed: `mujoco==3.7.0`, `robosuite==1.5.2`. Both shipped native arm64 wheels — no compile-from-source step.

## The `MUJOCO_GL` reality on macOS arm64

The script sets `MUJOCO_GL=glfw` per CLAUDE.md §16, but MuJoCo silently overrides it to `cgl` (Apple Core OpenGL) for the offscreen context — this is hardcoded into the macOS arm64 wheel and is the intended path. The override is invisible from the user perspective: offscreen `env.sim.render(...)` returns valid frames either way.

Practical implication: on this machine, every `MUJOCO_GL` value (glfw, egl, osmesa) ends up routed through CGL for offscreen rendering. Don't waste time chasing the env var if rendering breaks — chase the robosuite/MuJoCo versions instead.

## Harmless warnings to ignore

```
[robosuite WARNING] No private macro file found!
[robosuite WARNING] Could not import robosuite_models. Some robots may not be available.
[robosuite WARNING] Could not load the mink-based whole-body IK.
```

The first is a setup hint; the latter two only matter for robots we don't use (the missing models pack is for non-Panda robots; mink IK is GR1-specific). Ignore.
