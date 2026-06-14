#!/usr/bin/env bash
# One-command launcher: sets up a virtualenv, installs deps, runs the app.
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-python3.11}"
command -v "$PY" >/dev/null 2>&1 || PY="python3"

if [ ! -d ".venv" ]; then
  echo "→ Creating virtual environment (.venv)…"
  "$PY" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

echo "→ Installing dependencies…"
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

echo "→ Launching Smart Code Reviewer at http://localhost:8501"
exec streamlit run app.py
