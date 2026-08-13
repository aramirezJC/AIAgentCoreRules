#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if project_root="$(git -C "$PWD" rev-parse --show-toplevel 2>/dev/null)"; then
  output_dir="$project_root/Reports/AllDetailed"
else
  output_dir="$PWD/Reports/AllDetailed"
fi
mkdir -p "$output_dir"

exec "$script_dir/_run_token_report.sh" \
  --agent codex \
  --scope all \
  --format markdown \
  --per-session \
  --output "$output_dir/" \
  --include-content
