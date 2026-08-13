#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if project_root="$(git -C "$PWD" rev-parse --show-toplevel 2>/dev/null)"; then
  output_dir="$project_root/Reports/Recent"
else
  output_dir="$PWD/Reports/Recent"
fi
mkdir -p "$output_dir"

exec "$script_dir/_run_token_report.sh" \
  --agent codex \
  --scope last-30 \
  --format markdown \
  --output "$output_dir/"
