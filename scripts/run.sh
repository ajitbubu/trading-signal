#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ ! -d ".venv" ]]; then
  echo "No .venv detected. Create one with: python -m venv .venv && pip install -r requirements.txt" >&2
  exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate

if [[ ! -f ".env" ]]; then
  echo "No .env detected. Copy .env.example to .env and fill in keys." >&2
  exit 1
fi

mkdir -p data logs briefings diskcache

PORT="${STREAMLIT_SERVER_PORT:-8501}"
exec streamlit run app.py --server.port "$PORT"
