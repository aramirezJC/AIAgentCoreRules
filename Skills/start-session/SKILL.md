---
name: start-session
description: Start or resume session metrics tracking, optionally under an engineer-given name, and record the session's lane and work type. The SessionStart hook normally starts tracking automatically; run it by hand to name the session, when the hook is not installed, or when tracking context was lost.
argument-hint: "[name]"
---

# Start Session

Tracking is normally started by the SessionStart hook, which puts a **Session tracking** block
in context with the session folder and the lifecycle script path. This skill names the session,
covers the cases where the hook did not run, and records the lane and work type.

Lifecycle script (use the path from the Session tracking block if present):
`GitIgnoredExternals/AIAgentCoreRules/Tools/session-lifecycle/session_lifecycle.py`

```yaml
steps:
  - "Run: python3 <script> hook-start   # prints the tracking block; the folder is created by the set below"
  - "Classify the lane per MetaRouter 'First: Classify the Mode': small_task | bug_fix | investigation | feature | other"
  - "Classify the work type (below). If there is no request yet, record only the name and classify on the first request."
  - "Run: python3 <script> set --name \"<name>\" --lane <lane> --work-type <work_type> --title \"<short title>\""
  - "Reply with one line: name, lane, work type, folder path."
```

Arguments: `$ARGUMENTS` — the session name, taken verbatim (it may contain spaces). It is
optional; with no name, omit `--name`. The name becomes part of the folder
(`<date>_<lane>_<name-slug>_<id8>`) and the metrics.md heading. Running `/start-session <name>`
on a session that is already tracked renames it.

```yaml
work_type:   # what the work is, independent of which lane ran it — used by the meta-analysis
  bug_fix:       "something is broken and gets diagnosed or fixed"
  small_feature: "bounded new behaviour: a tool, utility, debug command, tweak"
  feature:       "a full feature (GDD, CreateFeature)"
  question:      "an answer, explanation, investigation or document — no shipped code"
  other:         "tooling, config, rules, docs, anything else"
```

If `--work-type` is omitted it follows the lane (small_task → small_feature, investigation →
question, …) and metrics.md marks it "(from lane)". Pass it explicitly whenever the two differ,
e.g. an investigation into a crash is lane `investigation`, work type `bug_fix`.

Do not ask the engineer to confirm the lane or work type unless the request is genuinely
ambiguous; state the assumption in one line and continue (same rule as MetaRouter).
