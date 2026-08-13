
This project contains general rules that can be used by AI agents to better
help with the development of other projects.

## Skills

- `Skills/token-usage-reports/` packages the portable session-report workflow
  for sanitized Codex, Claude Code, Gemini CLI, and Junie token reports. It
  delegates to `Tools/session-support/` so report parsing has one implementation
  owner.

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
