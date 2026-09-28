---
name: start-session
description: Start or resume session metrics tracking and record the session's lane. The SessionStart hook normally does this automatically; run it by hand when the hook is not installed, when tracking context was lost, or to set the lane and title.
argument-hint: "[lane] [title]"
---

# Start Session

Tracking is normally started by the SessionStart hook, which puts a **Session tracking** block
in context with the session folder and the lifecycle script path. This skill covers the cases
where that did not happen, and records the lane.

Lifecycle script (use the path from the Session tracking block if present):
`GitIgnoredExternals/AIAgentCoreRules/Tools/session-lifecycle/session_lifecycle.py`

```yaml
steps:
  - "Run: python3 <script> hook-start   # creates the folder, or reports it as resumed"
  - "Classify the lane per MetaRouter 'First: Classify the Mode': small_task | bug_fix | investigation | feature | other"
  - "Run: python3 <script> set --lane <lane> --title \"<short title>\""
  - "Reply with one line: lane, title, folder path."
```

Arguments: `$ARGUMENTS` — if a lane and/or title were given, use them instead of classifying.

Do not ask the engineer to confirm the lane unless the request is genuinely ambiguous; state
the assumed lane in one line and continue (same rule as MetaRouter).
