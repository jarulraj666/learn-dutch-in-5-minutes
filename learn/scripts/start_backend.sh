#!/usr/bin/env bash
# Start the learner API on port 8001 (the internal ops dashboard uses 8000).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENV="$ROOT/learn/.venv"

if [[ ! -x "$VENV/bin/python" ]]; then
  echo "Creating venv at $VENV"
  python3.11 -m venv "$VENV"
fi

"$VENV/bin/python" -m pip install --quiet -r "$ROOT/learn/backend/requirements.txt"

cd "$ROOT/learn/backend"
exec "$VENV/bin/python" -m uvicorn main:app --host 127.0.0.1 --port 8001 --reload
