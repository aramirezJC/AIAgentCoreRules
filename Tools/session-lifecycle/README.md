# Session Lifecycle

Per-session metrics for Claude Code: tokens, logged inaccuracies and iterations, and a router
trace (which rule and process files were loaded, in order, read from the session transcript).

## Output

```
<project>/GitIgnoreReports/Sessions/<YYYY-MM-DD_HHMM>_<lane>_<name>_<id8>/   # lane and name once set
  session.json   state
  metrics.md     rendered report
  retro.md       written by /end-session; "## Applied" tracks each proposal's status
  retro.html     rendered from retro.md by retro_page.py (`retro`, `open`), with token charts
  tokens/        session-support per-session token report
```

`<root>/hooks.log` gets one line per hook run (event, session, cwd, outcome) — the first place to
look when a session's metrics were not updated on exit. Hooks resolve the project from the
payload's `cwd`, not the process working directory.

Override the root with `SESSION_REPORTS_ROOT` or `--reports-root`.

Folders are created only when there is something to record: on the first `set`, `note` or
`compile`, or by `hook-stop` / `hook-end` once the transcript has a typed prompt. `hook-start`
creates nothing. `hook-end` deletes a folder that is still empty: no lane, title, name or notes,
no tokens, no retro, and no typed prompt. `prune-empty [--dry-run]` applies the same test to
every folder, for one-off cleanup.

## Install in a host project

1. Hooks in `<project>/.claude/settings.json`:

```json
{
  "hooks": {
    "SessionStart": [{ "hooks": [{ "type": "command",
      "command": "cd \"$CLAUDE_PROJECT_DIR\" && python3 <path-to>/Tools/session-lifecycle/session_lifecycle.py hook-start" }] }],
    "SessionEnd":   [{ "hooks": [{ "type": "command",
      "command": "cd \"$CLAUDE_PROJECT_DIR\" && python3 <path-to>/Tools/session-lifecycle/session_lifecycle.py hook-end" }] }],
    "Stop":         [{ "hooks": [{ "type": "command", "async": true,
      "command": "cd \"$CLAUDE_PROJECT_DIR\" && python3 <path-to>/Tools/session-lifecycle/session_lifecycle.py hook-stop" }] }]
  }
}
```

`SessionEnd` only fires when the Claude process exits (clear, resume, logout, exit). A session
the app marks completed after going idle never exits, and Claude Code has no idle hook. `Stop`
fires after every main-agent reply, and `hook-stop` recompiles then (at most every 2 minutes,
async, never marking the session ended), so metrics stay current however the session ends.

2. Symlink `Skills/start-session`, `end-session`, `inaccuracy`, `iteration` into
   `<project>/.claude/skills/`.

## Commands

```bash
python3 session_lifecycle.py set --name "HUD crash" --lane bug_fix --work-type bug_fix --title "Crash on HUD open"
python3 session_lifecycle.py note --kind inaccuracy "Guessed PrizeManager signature"
python3 session_lifecycle.py note --kind inaccuracy --source agent "Diffed branch tips without the merge-base"
python3 session_lifecycle.py compile [--final]
python3 session_lifecycle.py open
python3 session_lifecycle.py path
python3 session_lifecycle.py retro [--folder <id8>] [--open]
python3 session_lifecycle.py retro [--folder <id8>] --mark 2 --status applied --note "<file> — <what changed>"
```

`retro` renders `retro.html` (a standalone page, no external assets, light and dark) from
`retro.md` and prints each proposal's status. `--mark N --status applied|skipped|pending` first
rewrites proposal N's line in the `## Applied` section, creating the section with every other
proposal `pending` when it is missing. Without `--note`, the old note is kept only if the status
is unchanged. The line shape is the one `session_meta_report.py` reads. `--folder` targets
another session's retro: a path, a folder name, or a unique part of one such as the session id's
first 8 characters, so a proposal resolved in a later session can be marked where it was raised.
`open` re-renders the page and opens it with metrics.md.

`compile` also runs `token_breakdown.py` and stores `breakdown` (tokens per category, the
standardized-operations total, and the savings per mechanism) and `comparison` (every session's
de-duplicated total, for the average) in session.json. metrics.md renders them as *Token breakdown
(estimated)*, and retro.html renders them as a *Token charts* section before Cost: this session vs
the average/median/lane average, the standardized-operations share, and what saved tokens and
round-trips. Each model call is counted once. The token report counts a call once per content
block (~2–3× higher), so the charts use their own totals for every session. A tool result costs
its size × every later call that re-reads it. The savings assumptions are in `AVOIDED_BY_TOOL`.

retro.md stays the source of truth. A page opened from disk cannot write back, so each open
proposal has a button that copies its `retro --mark … --status applied` command.

`note --source` records who logged the entry: `engineer` (default, the `/inaccuracy` and
`/iteration` skills), `agent` (the agent's own self-correction) or `retro` (back-filled by
`/end-session` from the retro's Corrections). Older entries without a source count as `engineer`.

`set --lane` on a session that already has a different lane appends `{at, from, to}` to
`lane_history` in session.json; metrics.md lists it under *Lane changes*.

`--name` is the engineer-given session name (`/start-session <name>`). It is slugged into the
folder name, which `set` renames, and heads metrics.md.

`--work-type` (`bug_fix | small_feature | feature | question | other`) records what the work is,
separately from the lane that ran it, so the meta-analysis can compare cost by kind of work. Until
it is passed explicitly it follows the lane (`small_task → small_feature`, `investigation →
question`, others map to themselves) and `work_type_source` is `"lane"`; once explicit, later lane
changes no longer touch it. Changes are kept in `work_type_history` and listed under *Work type
changes*.

`--session-id` defaults to `$CLAUDE_CODE_SESSION_ID` (set by Claude Code in the Bash tool), else the
newest transcript for the project. An ID with no folder is an error — the script never falls
back to another session's folder.
A session launched from a subdirectory has its transcript filed under that directory's
`~/.claude/projects/<encoded-dir>/`, not the project root's. When the expected path is missing,
the script finds `<session_id>.jsonl` under any project folder, at hook-start and again at compile.
Hook subcommands always exit 0 so a failure never blocks a session.

## Limits

- Router-trace rows from `Read` are exact; rows from shell commands are inferred from paths in
  the command text, so a `grep` counts as a load and a path held in a shell variable is missed.
- Token numbers come from `Tools/session-support`, driven through its Python API with this session's
  transcript as an explicit rollout — so they are exact even when other sessions are running. The
  vendored package is not modified; if an upstream update renames `load_monitor`,
  `support_report`, `generated_session_reports` or `SessionMonitor.explicit_rollout`, tokens show as
  "unavailable (report failed: …)" until this script is updated. Upstream `engineering-support-kit`
  should still gain a `report --session-id` flag so other consumers get the same.
- `Started` is the transcript's first entry; `Tracking since` is when the hook first ran (they differ
  for sessions resumed from before the hooks were installed).
