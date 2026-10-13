#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
MIE_PYTHON="${MIE_PYTHON:-$PROJECT_DIR/.venv/bin/python}"
export MIE_FRONTEND_DIST="${MIE_FRONTEND_DIST:-$PROJECT_DIR/frontend/dist}"
if [[ ! -f "$MIE_FRONTEND_DIST/index.html" ]]; then
  printf '%s\n' 'Compile o frontend primeiro: cd frontend && npm ci && npm run build' >&2
  exit 1
fi
if [[ ! -x "$MIE_PYTHON" ]]; then
  printf '%s\n' "Python não encontrado: $MIE_PYTHON. Crie a .venv e instale .[web]." >&2
  exit 1
fi
# Artifact paths must be explicitly configured. No fitting occurs in this server.
exec "$MIE_PYTHON" -m market_intelligence.web --host "${MIE_HOST:-127.0.0.1}" --port "${MIE_PORT:-8000}"
