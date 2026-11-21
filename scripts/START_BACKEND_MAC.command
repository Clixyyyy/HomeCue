#!/bin/zsh
set -eu
cd "$(dirname "$0")/../backend"
if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv
fi
if ! .venv/bin/python -c 'import fastapi, uvicorn, sqlalchemy, jwt' 2>/dev/null; then
  .venv/bin/python -m pip install -r requirements.txt
fi
echo "HomeCue: http://127.0.0.1:8000 (Ctrl+C to stop)"
exec .venv/bin/python -m uvicorn main:app --host "${HOMECUE_HOST:-127.0.0.1}" --port 8000
