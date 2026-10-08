# Command Reference

Core slash commands, available once the skills are linked (see [[01_Setup|Setup]]). Commands marked
*engineer only* are never run by the agent on its own. Host project layers can add their own
commands — see the host project's documentation.

## Session lifecycle

| Command | What it does |
|---|---|
| `/start-session [name]` | Starts or resumes tracking, names the session (folder and metrics heading) when a name is given, and records the lane and work type. Tracking itself is automatic via the SessionStart hook — use it to name a session or when tracking context was lost. |
| `/end-session` | If the session worked in a worktree that still has work in it, first asks whether to land it and, on yes, runs `/land-worktree`. Then compiles metrics and the router trace, writes the retrospective scaled to the lane, opens both files, and proposes (not applies) rule improvements. |
| `/inaccuracy <what was wrong>` | *Engineer only.* Logs an agent mistake you just corrected. |
| `/iteration <what changed>` | *Engineer only.* Logs a deliberate change of direction or scope. |

## Feature work

| Command | What it does |
|---|---|
| `/feature <Name> [GDD path]` | Starts the 8-phase Create Feature process. If the feature already has a progress file, offers `/resume` instead. |
| `/checkpoint [Name] [note]` | Saves where work stopped inside the current phase to `<Name>_Progress.md`: done, in flight, next action, pending decisions, notes. |
| `/resume [Name]` | Picks a feature up in a fresh session: tags the session with the feature and phase, reloads the current phase, its rules and documents, reports drift (including a newer Confluence version), and waits for confirmation. With no name, lists unfinished features. |
| `/active-features` | Lists every feature that is not complete: phase, status, last update, next step, and the command that resumes it with the phase's recommended model. New sessions show a short version of this list at start. |

## Analysis and review

| Command | What it does |
|---|---|
| `/discover <area>` | Surveys a system or directory in a subagent and returns a compact map: key types, entry points, integration points, gotchas and negative findings, each with `file:line`. Uses the host's Runnable tools when available. Offers to save the map as a Systems entry if none exists. |
| `/audit [files]` | Checks C# files (default: changed files) against the coding standards, architecture principles, resource rules, rule tags and host project rules. Reports violations with `file:line` and a minimal fix. Report only — no edits unless asked. Fans out to subagents for more than 5 files. |

## Worktrees

| Command | What it does |
|---|---|
| `/land-worktree [name] [--squash]` | Merges an agent worktree's branch into your current branch without committing, waits while you test it, then commits and removes the worktree and branch — or rolls the merge back. With no name, lists the worktrees. Warns when a worktree branched from the default branch instead of yours and offers to cherry-pick only the agent's commits. Never pushes. |

## Reporting

| Command | What it does |
|---|---|
| `/token-usage-reports` | Sanitized token-usage and session-telemetry reports for current, recent or all sessions, exportable as Markdown or JSON. |

**Source files:** [[Skills/start-session/SKILL|/start-session]] · [[Skills/end-session/SKILL|/end-session]] · [[Skills/inaccuracy/SKILL|/inaccuracy]] · [[Skills/iteration/SKILL|/iteration]] · [[Skills/feature/SKILL|/feature]] · [[Skills/checkpoint/SKILL|/checkpoint]] · [[Skills/resume/SKILL|/resume]] · [[Skills/active-features/SKILL|/active-features]] · [[Skills/discover/SKILL|/discover]] · [[Skills/audit/SKILL|/audit]] · [[Skills/land-worktree/SKILL|/land-worktree]] · [[Skills/token-usage-reports/SKILL|/token-usage-reports]]

---

← [[07_SessionTracking|Session Tracking and Retrospectives]] · [[00_Overview|Overview]] · [[09_CodingRules|Coding Rules]] →
