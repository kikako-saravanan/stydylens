#!/usr/bin/env bash
# One-command launcher: sets up (first run only) and starts backend + frontend.
# Usage: ./start.sh      Stop with Ctrl+C.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

# --- Backend setup ---
if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env — set ANTHROPIC_API_KEY in it, then re-run ./start.sh"
  exit 1
fi
if ! grep -Eq '^ANTHROPIC_API_KEY=.+' .env; then
  echo "ANTHROPIC_API_KEY is empty in .env — set it, then re-run ./start.sh"
  exit 1
fi
if [ ! -d backend/.venv ]; then
  python3 -m venv backend/.venv
fi
if [ ! -f backend/.venv/.deps-installed ] || [ backend/requirements.txt -nt backend/.venv/.deps-installed ]; then
  backend/.venv/bin/pip install -r backend/requirements.txt
  touch backend/.venv/.deps-installed
fi

# --- Frontend setup ---
[ -f frontend/.env.local ] || cp frontend/.env.local.example frontend/.env.local
if [ ! -d frontend/node_modules ]; then
  (cd frontend && npm install)
fi

# Models are cached locally; skip Hugging Face network checks (avoids TLS/proxy retries)
if [ -d "$HOME/.cache/huggingface/hub/models--sentence-transformers--all-MiniLM-L6-v2" ]; then export HF_HUB_OFFLINE=1; fi

# --- Run both; Ctrl+C stops both ---
trap 'kill 0' EXIT INT TERM
(cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000) &
(cd frontend && npm run dev) &

echo
echo "Backend:  http://127.0.0.1:8000  (docs: /docs)"
echo "Frontend: http://localhost:3000"
wait
