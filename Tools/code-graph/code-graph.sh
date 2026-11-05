#!/usr/bin/env bash
# Code Graph server: start | status | stop [--project DIR] [--db PATH] [--refresh-cmd "<cmd>"]
# Run from the project root, or pass --project. start prints the URL (reuses a healthy server).
set -euo pipefail
if [[ ${BASH_SOURCE[0]} != "$0" ]]; then
    printf 'Run this script instead of sourcing it.\n' >&2
    return 2
fi
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
exec "${CODE_GRAPH_PYTHON:-python3}" "$SCRIPT_DIR/graph_control.py" "$@"
