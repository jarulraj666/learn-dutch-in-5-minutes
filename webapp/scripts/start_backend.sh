#!/usr/bin/env bash
# Start the FastAPI backend (uses the same .venv311 as the pipeline)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
VENV="$ROOT/.venv311"
BACKEND="$ROOT/webapp/backend"

if [[ ! -d "$VENV" ]]; then
  echo "ERROR: venv not found at $VENV"
  echo "Run: python3.11 -m venv .venv311 && source .venv311/bin/activate && pip install -r webapp/backend/requirements.txt"
  exit 1
fi

source "$VENV/bin/activate"

# Install backend dependencies if needed
"$VENV/bin/python" -m pip install -q -r "$BACKEND/requirements.txt"

cd "$BACKEND"
echo "Starting backend on http://localhost:8000"
echo "caffeinate active — laptop will stay awake while backend is running"
caffeinate -s "$VENV/bin/python" -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
