#!/data/data/com.termux/files/usr/bin/sh
set -eu
cd "$(dirname "$0")"
echo "Starting Offline Agent HQ dashboard..."
python dashboard.py
