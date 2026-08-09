#!/bin/bash
# Captures the raw bytes the TUI writes to stdout, without touching any tty,
# so they can be inspected for escape sequences the console can't handle.
set -e
cd "$(dirname "$0")/.."
source .venv/bin/activate
export TERM=linux
timeout 5 python -m client.tui --host 192.168.1.120 --port 8000 \
  > /tmp/tui_output.raw 2>/tmp/tui_stderr.log || true
echo "----- stdout (escaped) -----"
cat -v /tmp/tui_output.raw | head -c 2000
echo
echo "----- stderr -----"
cat /tmp/tui_stderr.log | head -c 1000
