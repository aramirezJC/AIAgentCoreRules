#!/usr/bin/env bash
# Run from the project root; optionally pass an explicit project directory.
set -euo pipefail
if [[ ${BASH_SOURCE[0]} != "$0" ]]; then
    printf 'Run this script instead of sourcing it.\n' >&2
    return 2
fi
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
exec "${PREVIEW_PYTHON:-python3}" "$SCRIPT_DIR/preview_control.py" "$@"
