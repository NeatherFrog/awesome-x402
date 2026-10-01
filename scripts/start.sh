#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
task_port="${TRADING_PORT:-8000}"
if python3 scripts/check_ready.py --port "$task_port" --quiet; then
    printf 'PROP LAB already ready on port %s\n' "$task_port"
    exit 0
fi
mkdir -p .local
nohup python3 -m propdesk serve --host 127.0.0.1 --port "$task_port" >.local/server.log 2>&1 &
task_server_pid=$!
printf '%s\n' "$task_server_pid" >.local/server.pid
for task_attempt in {1..50}; do
    if ! kill -0 "$task_server_pid" 2>/dev/null; then
        printf 'Server startup failed; inspect .local/server.log\n' >&2
        exit 1
    fi
    if python3 scripts/check_ready.py --port "$task_port" --quiet; then
        printf 'PROP LAB ready on port %s; PID %s; log .local/server.log\n' "$task_port" "$task_server_pid"
        exit 0
    fi
    sleep 0.2
done
kill "$task_server_pid" 2>/dev/null || true
printf 'Server did not pass functional readiness; inspect .local/server.log\n' >&2
exit 1
