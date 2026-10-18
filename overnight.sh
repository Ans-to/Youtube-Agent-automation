#!/data/data/com.termux/files/usr/bin/sh
set -eu
cd "$(dirname "$0")"
if command -v termux-wake-lock >/dev/null 2>&1; then
  termux-wake-lock
fi
python agent.py --loop --interval 60
