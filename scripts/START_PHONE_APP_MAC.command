#!/bin/zsh
set -eu
cd "$(dirname "$0")/.."
echo "Connect your phone and Mac to the same Wi-Fi."
echo "Open http://YOUR_MAC_WIFI_IP:8000/app/ on the phone."
export HOMECUE_HOST=0.0.0.0
exec zsh scripts/START_BACKEND_MAC.command
