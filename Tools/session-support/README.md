# Portable Session Support

This dependency-free package provides sanitized local monitoring and reporting
for Codex, Claude Code, Gemini CLI, and Junie sessions.

## Commands

```bash
python3 session_support/session-support \
  --project-config session_support/project.example.json \
  monitor status

python3 session_support/session-support --agent claude history
python3 session_support/session-support --agent gemini monitor status
python3 session_support/session-support --agent junie report
python3 session_support/session-support report
python3 session_support/session-support split
python3 session_support/session-support monitor start
```

Generate sanitized reports for one session, the latest 30, or all discovered
sessions:

```bash
python3 session_support/session-support report --scope current --format markdown --output current.md
python3 session_support/session-support report --scope last-30 --format markdown --output recent.md
python3 session_support/session-support report --scope all --format json --output all.json
python3 session_support/session-support report --scope current --format markdown --include-content --output reports/
python3 session_support/session-support report --scope last-30 --format markdown --per-session --output reports/
```

`--per-session` writes the normal aggregate Markdown report plus one Markdown
report for each session selected by the scope. It requires an output directory
and is intentionally unavailable for JSON, where the aggregate document already
contains structured per-session records. Per-session Markdown includes token
composition, tool-first compliance, category costs, turn trends, highest-cost
turns, and timing/cache problem areas. Prompts and responses remain excluded
unless `--include-content` is explicitly requested.

The dashboard offers the same three Markdown downloads. It also shows average
cache ratio, helper invocation details, category token cost, highest-cost turn
diagnostics, and Codex duration/TTFT when source timestamps are available.

`--include-content` and the dashboard's matching checkbox are explicit
sensitive-data opt-ins. They add prompts, responses, commands, and paths plus a
warning header. Review these reports before sharing or committing them.

Current-session filenames contain the session ID and start timestamp. Multi-
session filenames contain the scope and generation timestamp. Sensitive report
filenames also end in `-sensitive.md` so they cannot silently replace a
sanitized report generated for the same session.

Dashboard diagnostics are interactive: select a sanitized turn to inspect its
metrics, select a category-cost row to list its contributing turns, and hover a
chart point or bar for its underlying values. Selecting any turn opens the same
detail panel; prompts, responses, commands, and paths appear there only while
the sensitive-content checkbox is enabled.

Turn details always list sanitized tool names and counts. Enabling sensitive
content additionally shows each tool call's captured arguments; those arguments
may contain source, paths, identifiers, or secrets and require the same review
as prompts and responses.

Copy `project.example.json` into the consuming repository, then configure its
agent roots, category rules, helper prefixes, warning thresholds, local state
root, labels, and continuation defaults. Paths may use `${HOME}` and paths
relative to the project-config file.

The project label is optional. When omitted, the monitor derives the current
Git repository name. For selected and recent sessions, source metadata takes
precedence so the dashboard can identify sessions from different repositories
without exposing absolute paths.

## Contracts

- live snapshot: version 4
- aggregate support report: version 1
- adapters: `codex`, `claude`, `gemini`, `junie`
- Gemini telemetry: tokens, cache, thought/reasoning tokens, and tool calls;
  context-window size and child agents are unavailable
- Junie telemetry: completed/active tasks, terminal/tool activity, helpers, and
  model usage; reasoning tokens, context-window size, and child agents are
  unavailable
- unavailable telemetry: `null` plus a `false` source capability
- local server: loopback-only HTTP and server-sent events

The contracts exclude prompts, responses, commands, environment values, and
session paths. History is a sanitized metric summary, not a transcript export.

## Install And Update

Pin an exact support-kit revision or copy this directory with
`provenance.json`. Review configuration locally before running it. Updates
replace package-owned files only; project configuration and local state remain
consumer-owned.

Run tests:

```bash
python3 -m unittest discover -s session_support/tests -p 'test_*.py'
```

Rollback by restoring the prior pinned revision or prior provenance-recorded
copy. Local state is disposable and may be removed independently.
