#!/usr/bin/env bash
# Subcommands:
#    install            Configure Claude (default), Codex, or both with --agent.
#                       Codex links skills into .agents/skills/ and creates AGENTS.md if missing.
#                       Safe to re-run: only adds or updates what the fragments define.
#    check              Same as `install --dry-run`; accepts --agent too.
#    prepare-worktree   Symlink worktree.symlinkDirectories into a worktree Claude Code did not
#                       create (for example one made by hand with `git worktree add`).
#    worktrees          List the project's linked worktrees with branch, dirty state, and commits
#                       ahead of the current branch (used by /land-worktree).
set -euo pipefail
if [[ ${BASH_SOURCE[0]} != "$0" ]]; then
    printf 'Run this script instead of sourcing it.\n' >&2
    return 2
fi
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
exec "${INSTALL_PYTHON:-python3}" "$SCRIPT_DIR/install.py" "$@"