# Session Lifecycle

Per-session metrics for Claude Code: tokens, logged inaccuracies and iterations, and a router
trace (which rule and process files were loaded, in order, read from the session transcript).

## Output

```
<project>/GitIgnoreReports/Sessions/<YYYY-MM-DD_HHMM>_<lane>_<id8>/
  session.json   state
  metrics.md     rendered report
  retro.md       written by /end-session
  tokens/        session-support per-session token report
```

Override the root with `SESSION_REPORTS_ROOT` or `--reports-root`.

## Install in a host project

1. Hooks in `<project>/.claude/settings.json`:

```json
{
  "hooks": {
    "SessionStart": [{ "hooks": [{ "type": "command",
      "command": "cd \"$CLAUDE_PROJECT_DIR\" && python3 <path-to>/Tools/session-lifecycle/session_lifecycle.py hook-start" }] }],
    "SessionEnd":   [{ "hooks": [{ "type": "command",
      "command": "cd \"$CLAUDE_PROJECT_DIR\" && python3 <path-to>/Tools/session-lifecycle/session_lifecycle.py hook-end" }] }]
  }
}
```

2. Symlink `Skills/start-session`, `end-session`, `inaccuracy`, `iteration` into
   `<project>/.claude/skills/`.

## Commands

```bash
python3 session_lifecycle.py set --lane bug_fix --title "Crash on HUD open"
python3 session_lifecycle.py note --kind inaccuracy "Guessed PrizeManager signature"
python3 session_lifecycle.py compile [--final]
python3 session_lifecycle.py open
python3 session_lifecycle.py path
```

`--session-id` defaults to the running session (the newest transcript for the project).
Hook subcommands always exit 0 so a failure never blocks a session.

## Limits

- Router-trace rows from `Read` are exact; rows from shell commands are inferred from paths in
  the command text, so a `grep` counts as a load and a path held in a shell variable is missed.
- Token numbers come from `session-support --scope current`; they are marked unavailable when the
  project's newest session is not this one (e.g. two sessions running at once).
