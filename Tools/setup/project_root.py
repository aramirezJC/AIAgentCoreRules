"""Find the host project's root — shared by install.py and session_lifecycle.py, so the installer
and the session tracker always agree on it. No per-project configuration: git knows the root.

    find_project_root(start)   the main checkout (shared by every worktree): where reports live
    find_working_root(start)   the checkout `start` is in (a worktree when inside one)

Both fall back to the nearest ancestor holding CLAUDE.md for a project without git, and return
None when neither is found. Never derive a root from a shell's cwd without one of these: the
agent's `cd` moves the cwd, and a root built from it nests GitIgnoreReports inside itself.
"""

import os
import subprocess

MARKER = "CLAUDE.md"


def git(args, cwd):
    """stdout of a git command, or None when it fails (not a repository, git missing)."""
    try:
        result = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True)
    except OSError:
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def find_marker_root(start):
    """Nearest ancestor of start (inclusive) that holds CLAUDE.md, or None."""
    current = os.path.realpath(start)
    while True:
        if os.path.isfile(os.path.join(current, MARKER)):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def find_project_root(start):
    common = git(["rev-parse", "--path-format=absolute", "--git-common-dir"], start)
    return os.path.dirname(common) if common else find_marker_root(start)


def find_working_root(start):
    return git(["rev-parse", "--show-toplevel"], start) or find_marker_root(start)
