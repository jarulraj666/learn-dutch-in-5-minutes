#!/usr/bin/env bash
# Install Node deps and start the Next.js frontend dev server
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
FRONTEND="$ROOT/webapp/frontend"

cd "$FRONTEND"

if [[ ! -d "node_modules" ]]; then
  echo "Installing Node dependencies..."
  npm install
fi

echo "Starting frontend on http://localhost:3000"
npm run dev
