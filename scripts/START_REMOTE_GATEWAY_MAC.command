#!/bin/zsh
set -eu
cd "$(dirname "$0")/../backend"
if [[ -z "${HOMECUE_REMOTE_EMAIL:-}" ]]; then
  echo "Set HOMECUE_REMOTE_EMAIL to the approved email address before starting."
  exit 1
fi
if [[ ! -x .venv/bin/python ]]; then
  echo "Run START_BACKEND_MAC.command first to install HomeCue dependencies."
  exit 1
fi
echo "Starting the password-protected remote gateway on loopback port 8001."
echo "This command does not publish a tunnel or change the existing email-code link."
exec .venv/bin/python -m uvicorn remote_gateway:create_app --factory --host 127.0.0.1 --port 8001
