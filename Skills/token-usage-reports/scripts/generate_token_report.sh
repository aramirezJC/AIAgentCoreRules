#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  generate_token_report.sh [options]

Options:
  --agent codex|claude|gemini|junie
  --scope current|last-30|all
  --format markdown|json
  --output <file-or-directory>
  --project-config <path>
  --sessions-root <path>
  --since <ISO timestamp>
  --include-content
  --per-session
  -h, --help
EOF
}

SKILL_DIRECTORY="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCOPE="last-30"
FORMAT="markdown"
AGENT=""
OUTPUT=""
PROJECT_CONFIG=""
SESSIONS_ROOT=""
SINCE=""
INCLUDE_CONTENT=false
PER_SESSION=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --agent)
      [[ $# -ge 2 ]] || { usage >&2; exit 2; }
      AGENT="$2"
      shift 2
      ;;
    --scope)
      [[ $# -ge 2 ]] || { usage >&2; exit 2; }
      SCOPE="$2"
      shift 2
      ;;
    --format)
      [[ $# -ge 2 ]] || { usage >&2; exit 2; }
      FORMAT="$2"
      shift 2
      ;;
    --output)
      [[ $# -ge 2 ]] || { usage >&2; exit 2; }
      OUTPUT="$2"
      shift 2
      ;;
    --project-config)
      [[ $# -ge 2 ]] || { usage >&2; exit 2; }
      PROJECT_CONFIG="$2"
      shift 2
      ;;
    --sessions-root)
      [[ $# -ge 2 ]] || { usage >&2; exit 2; }
      SESSIONS_ROOT="$2"
      shift 2
      ;;
    --since)
      [[ $# -ge 2 ]] || { usage >&2; exit 2; }
      SINCE="$2"
      shift 2
      ;;
    --include-content)
      INCLUDE_CONTENT=true
      shift
      ;;
    --per-session)
      PER_SESSION=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

case "$SCOPE" in current|last-30|all) ;; *) echo "Invalid scope: $SCOPE" >&2; exit 2 ;; esac
case "$FORMAT" in markdown|json) ;; *) echo "Invalid format: $FORMAT" >&2; exit 2 ;; esac
if [[ -n "$AGENT" ]]; then
  case "$AGENT" in codex|claude|gemini|junie) ;; *) echo "Invalid agent: $AGENT" >&2; exit 2 ;; esac
fi
if [[ "$INCLUDE_CONTENT" == true && "$FORMAT" != "markdown" ]]; then
  echo "--include-content requires --format markdown" >&2
  exit 2
fi
if [[ "$PER_SESSION" == true && "$FORMAT" != "markdown" ]]; then
  echo "--per-session requires --format markdown" >&2
  exit 2
fi
if [[ "$PER_SESSION" == true && -z "$OUTPUT" ]]; then
  echo "--per-session requires --output directory" >&2
  exit 2
fi

CANDIDATES=()
if [[ -n "${TOKEN_USAGE_SESSION_SUPPORT_ROOT:-}" ]]; then
  CANDIDATES+=("$TOKEN_USAGE_SESSION_SUPPORT_ROOT")
fi
CANDIDATES+=(
  "$SKILL_DIRECTORY/scripts/session_support"
  "$PWD/Tools/session-support"
  "$SKILL_DIRECTORY/../../Tools/session-support"
)

SUPPORT_ROOT=""
for candidate in "${CANDIDATES[@]}"; do
  if [[ -f "$candidate/session-support" ]]; then
    SUPPORT_ROOT="$candidate"
    break
  fi
done

if [[ -z "$SUPPORT_ROOT" ]]; then
  echo "Could not find the portable session-support package." >&2
  echo "Set TOKEN_USAGE_SESSION_SUPPORT_ROOT or install Tools/session-support." >&2
  exit 1
fi

COMMAND=(python3 "$SUPPORT_ROOT/session-support")
[[ -n "$AGENT" ]] && COMMAND+=(--agent "$AGENT")
[[ -n "$PROJECT_CONFIG" ]] && COMMAND+=(--project-config "$PROJECT_CONFIG")
[[ -n "$SESSIONS_ROOT" ]] && COMMAND+=(--sessions-root "$SESSIONS_ROOT")
[[ -n "$SINCE" ]] && COMMAND+=(--since "$SINCE")
COMMAND+=(report --scope "$SCOPE" --format "$FORMAT")
[[ -n "$OUTPUT" ]] && COMMAND+=(--output "$OUTPUT")
[[ "$INCLUDE_CONTENT" == true ]] && COMMAND+=(--include-content)
[[ "$PER_SESSION" == true ]] && COMMAND+=(--per-session)

"${COMMAND[@]}"
