---
name: close-feature
description: Close or force-terminate an in-progress CreateFeature feature - set a closing status (abandoned, superseded, on_hold or complete) in its <FeatureName>_Progress.md and record why, so it drops off /active-features and the session-start list. Use when the engineer runs /close-feature, or says to drop, cancel, abandon, shelve or stop tracking a feature.
argument-hint: "<FeatureName> [reason]"
---

# Close Feature

Paths are relative to the AIAgentCoreRules root (the parent of the `Rules/` folder that holds
MetaRouter.md). Lifecycle script (path from the Session tracking block, else):
`GitIgnoredExternals/AIAgentCoreRules/Tools/session-lifecycle/session_lifecycle.py`

```yaml
steps:
  - "Feature name: the first word of $ARGUMENTS. None → run `python3 <script> features`, ask which feature to close, and stop until answered."
  - "Progress file: the `progress_file` that `python3 <script> features --json` prints for it. Not listed → say it is not in progress (already complete or closed: `features --closed`) and stop."
  - "Read the progress file. Show one line: feature · phase · status · next."
  - "Ask the closing status with AskUserQuestion (single select, header 'Close as'), in this order:"
  - "  abandoned (Recommended) — work stopped and will not resume as planned"
  - "  superseded             — replaced by another feature; ask which one if $ARGUMENTS does not say"
  - "  on_hold                — parked on purpose; expected to come back with /reopen-feature"
  - "  complete               — finished outside the process; final, /reopen-feature refuses it"
  - "Reason: the rest of $ARGUMENTS, else the engineer's notes on the picker, else ask once. Never invent one."
  - "Edit the header block: status → the chosen value, updated_at → now (ISO). Add the current session folder (Session tracking block) to `sessions` if no entry ends in the same id8."
  - "Append (or extend) a `## Closed` section at the end of the file — see the format below. Leave Checkpoint and Gates Passed as they are: /reopen-feature resumes from them."
  - "Reply with one line: '<Feature> closed as <status> in <phase>. Reopen with /reopen-feature <Feature>.' — for complete, drop the reopen hint."
```

## Closed section

One entry per close or reopen, appended in order — the feature's lifecycle history.

```yaml
closed:
  - at:        "<ISO timestamp>"
    action:    close             # close | reopen (written by /reopen-feature)
    status:    abandoned         # the status set
    phase:     "1_intake"        # current_phase at the time
    was:       "in_progress"     # the status before this change
    reason:    "<engineer's reason>"
    superseded_by: ""            # superseded only
    session:   "<session folder name>"
```

## Rules

```yaml
rules:
  - "The engineer confirms the status through the picker every time — never close a feature without it, even when $ARGUMENTS names one."
  - "Never delete, move or rename the feature folder or any artifact in it."
  - "Never edit a Gates Passed block or the Checkpoint — a reopened feature resumes from them."
  - "Feature folders are ignored by git; a background job cannot write them. In a background job, say so and hand off: /new-session \"/close-feature <Feature> <reason>\"."
```
