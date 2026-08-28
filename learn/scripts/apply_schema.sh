#!/usr/bin/env bash
# Apply learn/db/schema.sql to $DATABASE_URL.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
: "${DATABASE_URL:?DATABASE_URL is not set}"

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f "$ROOT/learn/db/schema.sql"
echo "✅ Schema applied"
