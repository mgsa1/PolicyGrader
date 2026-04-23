"""Launch the Gradio UI pointed at an orchestrator mirror directory.

Usage:
  source .venv/bin/activate
  python scripts/run_ui.py  # defaults to artifacts/smoke/agent
  python scripts/run_ui.py --mirror-root artifacts/sessions/<id>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import gradio as gr  # noqa: E402

from src.ui.app import build_app  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MIRROR_ROOT = REPO_ROOT / "artifacts" / "smoke" / "agent"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mirror-root", type=Path, default=DEFAULT_MIRROR_ROOT)
    parser.add_argument("--port", type=int, default=7860)
    args = parser.parse_args()

    mirror_root = args.mirror_root.resolve()
    mirror_root.mkdir(parents=True, exist_ok=True)
    print(f"UI watching: {mirror_root}", flush=True)
    app = build_app(mirror_root)
    app.launch(
        server_port=args.port,
        inbrowser=True,
        theme=gr.themes.Soft(),
        css=".gradio-container {max-width: 1400px !important;}",
        allowed_paths=[str(mirror_root)],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
