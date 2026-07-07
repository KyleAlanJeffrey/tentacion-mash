#!/usr/bin/env bash
# setup.sh — create the project virtualenv (.venv) and install dependencies
set -e
cd "$(dirname "$0")"

# rebuild if the venv is missing or broken (e.g. built on another machine)
if ! .venv/bin/python -c "" 2>/dev/null; then
  rm -rf .venv
fi

[ -x .venv/bin/python ] || python3 -m venv .venv

.venv/bin/pip install --quiet pillow "opencv-python-headless<5" "numpy<3"

echo "✔ .venv ready — use ./run.sh"
