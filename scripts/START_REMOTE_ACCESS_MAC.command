#!/bin/zsh
# Approved password-protected gateway. Never tunnel the unprotected backend port.
set -eu
cd "$(dirname "$0")/.."
tunnel_bin="${HOMECUE_CLOUDFLARED:-}"
if [[ -z "$tunnel_bin" ]]; then
  tunnel_bin="$(command -v cloudflared || true)"
fi
if [[ -z "$tunnel_bin" && -x /private/tmp/homecue-tunnel/cloudflared ]]; then
  tunnel_bin=/private/tmp/homecue-tunnel/cloudflared
fi
if [[ -z "$tunnel_bin" ]]; then
  echo "Install cloudflared from https://developers.cloudflare.com/tunnel/downloads/"
  exit 1
fi
allowed_email="${HOMECUE_REMOTE_EMAIL:-}"
if [[ -z "$allowed_email" ]]; then
  read "allowed_email?Approved email address (comma-separated for several): "
fi
if [[ "$allowed_email" != *@*.* || "$allowed_email" == *\** ]]; then
  echo "Enter specific email addresses; wildcard access is not supported."
  exit 1
fi
if lsof -tiTCP:8001 -sTCP:LISTEN >/dev/null; then
  echo "A remote gateway is already running. Use its existing link, or stop it before restarting."
  exit 1
fi
export HOMECUE_REMOTE_EMAIL="$allowed_email"
gateway_pid=''
tunnel_pid=''
cleanup() {
  if [[ -n "$tunnel_pid" ]]; then kill "$tunnel_pid" 2>/dev/null || true; fi
  if [[ -n "$gateway_pid" ]]; then kill "$gateway_pid" 2>/dev/null || true; fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
zsh scripts/START_REMOTE_GATEWAY_MAC.command &
gateway_pid=$!
ready=false
for attempt in {1..40}; do
  if curl -fsS --max-time 1 http://127.0.0.1:8001/remote-access >/dev/null 2>&1; then
    ready=true
    break
  fi
  if ! kill -0 "$gateway_pid" 2>/dev/null; then break; fi
  sleep 0.2
done
if [[ "$ready" != true ]]; then
  echo "The protected gateway could not start. No public tunnel was opened."
  exit 1
fi
echo "Remote sign-in uses the approved email and existing HomeCue password."
echo "Keep the Mac awake. Open the printed HTTPS link, or add /app/ for the app."
echo "Ctrl+C stops this tunnel and its gateway."
"$tunnel_bin" tunnel --url http://127.0.0.1:8001 --protocol quic --no-autoupdate &
tunnel_pid=$!
wait "$tunnel_pid"
