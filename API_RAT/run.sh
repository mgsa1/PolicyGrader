#!/bin/bash
# Launches the API_RAT game in the MuJoCo viewer. On macOS this must go
# through mjpython (the Python interpreter bundled with the mujoco wheel);
# elsewhere plain python works too.
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ "$(uname)" == "Darwin" && -x .venv/bin/mjpython ]]; then
  exec .venv/bin/mjpython -m API_RAT.main "$@"
else
  exec .venv/bin/python -m API_RAT.main "$@"
fi
