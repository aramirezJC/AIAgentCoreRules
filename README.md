
This project contains general rules that can be used by AI agents to better
help with the development of other projects.

## Session Lifecycle

`Tools/session-lifecycle/session_lifecycle.py` tracks every Claude Code session in the host
project's `GitIgnoreReports/Sessions/<date>_<lane>_<id>/` folder: tokens (via
`Tools/session-support`), logged inaccuracies and iterations, and a router trace of which rule
files were actually loaded, read from the session transcript. A SessionStart hook starts it, a
SessionEnd hook compiles it, and `/end-session` adds a retrospective. Hook setup is in
`Tools/session-lifecycle/README.md`.

## Skills

Install into a host project by symlinking each folder into `<project>/.claude/skills/`.

- `start-session`, `end-session`, `inaccuracy`, `iteration` — session lifecycle.
- `feature` — enters `Processes/CreateFeature`.
- `checkpoint`, `resume` — save and restore feature progress across sessions via
  `<FeatureName>_Progress.md` in the feature's working folder.
- `discover` — subagent survey that returns a compact map.
- `audit` — rules compliance report for C# files.
- `Skills/token-usage-reports/` packages the portable session-report workflow
  for sanitized Codex, Claude Code, Gemini CLI, and Junie token reports. It
  delegates to `Tools/session-support/` so report parsing has one implementation
  owner. Markdown reports can include one aggregate file plus one file per
  selected session.

## Portable Session Support

`Tools/session-support/` is a vendored, dependency-free local toolset for
Codex, Claude Code, Gemini CLI, and Junie session monitoring, sanitized
recent-session history, aggregate support reporting, and advisory split checks.

```bash
python3 Tools/session-support/session-support monitor status
python3 Tools/session-support/session-support --agent claude history
python3 Tools/session-support/session-support --agent gemini monitor status
python3 Tools/session-support/session-support --agent junie report
python3 Tools/session-support/session-support report
python3 Tools/session-support/session-support split
```

Copy `Tools/session-support/project.example.json` into the consuming repository
and configure project labels, session roots, helper prefixes, warning
thresholds, state storage, and continuation defaults. Do not commit agent
session files, local state, or generated reports.

The canonical portable implementation is maintained in
`engineering-support-kit`; `Tools/session-support/provenance.json` records this
copy's source and update policy.
