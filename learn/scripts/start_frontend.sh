#!/usr/bin/env bash
# Start the learner frontend on port 3001 (the internal dashboard uses 3000).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT/learn/frontend"

[[ -d node_modules ]] || npm install
exec npm run dev
