"""Launch the Gradio UI over a runs-root containing one subdir per past run.

The dropdown picker discovers all runs in the directory; each run is a tree of
runtime.json + chat.jsonl + dispatch_log.jsonl + rollouts/ + keyframes/ written
by `scripts/smoke_agent.py` under `<runs-root>/<run_id>/`.

Usage:
  source .venv/bin/activate
  python scripts/run_ui.py  # defaults to artifacts/runs/
  python scripts/run_ui.py --runs-root artifacts/runs
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.ui import styles, theme  # noqa: E402
from src.ui.app import build_app  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RUNS_ROOT = REPO_ROOT / "artifacts" / "runs"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs-root", type=Path, default=DEFAULT_RUNS_ROOT)
    parser.add_argument("--port", type=int, default=7860)
    args = parser.parse_args()

    runs_root = args.runs_root.resolve()
    runs_root.mkdir(parents=True, exist_ok=True)
    print(f"UI watching: {runs_root}", flush=True)
    app = build_app(runs_root)
    app.launch(
        server_port=args.port,
        inbrowser=True,
        css=theme.CSS,
        css_paths=[styles.tokens_css_path()],
        allowed_paths=[str(runs_root)],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
