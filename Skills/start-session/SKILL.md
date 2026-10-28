---
name: start-session
description: Start or resume session metrics tracking, optionally under an engineer-given name, and record the session's lane and work type. The SessionStart hook normally starts tracking automatically; run it by hand to name the session, when the hook is not installed, or when tracking context was lost.
argument-hint: "[name]"
---

# Start Session

Tracking is normally started by the SessionStart hook, which puts a **Session tracking** block
in context with the session folder and the lifecycle script path. This skill names the session,
covers the cases where the hook did not run, and records the lane and work type.

The lane-entry skills (`/small-task`, `/bug-fix`, `/feature`, `/resume-work`,
`/run-investigation-mode`, `/generate-meta-review`) run this skill's `hook-start` step as their
step 0 and then their own `set` with a fixed lane — no separate `/start-session` is needed.

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

## Codex session tracking

The lifecycle tracker accepts Codex rollouts as well as Claude transcripts. In Codex,
`CODEX_THREAD_ID` selects the exact thread; `--session-id` can select a known thread explicitly.
It never picks the newest Codex thread. Missing or ambiguous rollouts fail without attaching
another session's data. Rollouts are located below `$CODEX_HOME/sessions` (default
`~/.codex/sessions`). Do not pass `unknown` or invent an ID.

Run the existing commands from the host checkout:

```bash
python3 <lifecycle-script> hook-start
python3 <lifecycle-script> set --lane other --work-type other --title "Session tooling"
python3 <lifecycle-script> note --kind inaccuracy --source agent "Description of correction"
python3 <lifecycle-script> compile
```

Use the appropriate lane/title for the actual task. `compile --final` belongs at session end.
Session folders contain the agent type, notes, metrics and sanitized token reports. The existing
session-support Codex parser supplies usage; cumulative token events must not be summed.
Codex shell reads, including supported nested JavaScript exec commands, produce heuristic
Bash rows in the router trace. Main-thread trace coverage does not imply complete child-agent
trace coverage. Detailed standardized-operation attribution and comparison charts remain
unavailable for Codex rather than showing misleading zeros. Token reports may still include
child-agent telemetry supported by session-support.

These parser changes do not install automatic hooks. Current Codex supports a trusted project
`.codex/hooks.json` with `SessionStart`, `Stop` and `SessionEnd` command hooks calling
`hook-start`, `hook-stop` and `hook-end`. Hook payloads supply `session_id` and `transcript_path`.
Use the resolved lifecycle script path; preserve any existing hooks. Configure Stop with an
adequate timeout (for example 30 seconds), and SessionEnd with its supported maximum of 3
seconds. The Stop hook keeps metrics current even when closing a window does not end a thread.
Trust/reload the project hooks in Codex before expecting automatic execution. No Claude hook
execution is implied by a Codex skills installation.

Reference: https://learn.chatgpt.com/docs/hooks . Transcript formats are not a stable hook API;
keep synthetic regression fixtures and report parser failures as unavailable. Without a usable
transcript, retain the sanitized usage report and `retro --path` HTML fallback.

