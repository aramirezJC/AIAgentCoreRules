---
name: reopen-feature
description: Return a CreateFeature feature closed by /close-feature (abandoned, superseded or on_hold) to in_progress so it shows in /active-features again and /resume-work can pick it up. Refuses a complete feature. Use when the engineer runs /reopen-feature, or asks to revive, unshelve or restart work on a closed feature.
argument-hint: "[FeatureName] [reason]"
---

# Reopen Feature

Paths are relative to the AIAgentCoreRules root (the parent of the `Rules/` folder that holds
MetaRouter.md). Lifecycle script (path from the Session tracking block, else):
`GitIgnoredExternals/AIAgentCoreRules/Tools/session-lifecycle/session_lifecycle.py`

```yaml
steps:
  - "Feature name: the first word of $ARGUMENTS. None → run `python3 <script> features --closed`, ask which one to reopen (AskUserQuestion when 2–4 are listed), and stop until answered. Empty list → say there is nothing to reopen and stop."
  - "Progress file: the `progress_file` that `python3 <script> features --closed --json` prints for it."
  - "Not in that list → read <features folder>/<Feature>/<Feature>_Progress.md if it exists and stop with the reason: status complete → 'complete features cannot be reopened — start a follow-up with /feature <NewName>'; in_progress or at_gate → 'already in progress — /resume-work <Feature>'; no file → 'no such feature'."
  - "Read the progress file. Show one line: feature · phase · closed status · the latest close reason from the Closed section."
  - "Edit the header block: status → in_progress, updated_at → now (ISO). Add the current session folder to `sessions` if no entry ends in the same id8."
  - "Append a reopen entry to the Closed section (format in /close-feature): action reopen, status in_progress, was <closed status>, reason the rest of $ARGUMENTS (else empty — do not ask)."
  - "Reply with one line: '<Feature> reopened in <phase>. Resume with:' and the resume command `python3 <script> features` now prints for it."
```

## Rules

```yaml
rules:
  - "Never reopen a complete feature, and never change complete to anything else."
  - "Reopen only changes status, updated_at, sessions and the Closed section — Checkpoint and Gates Passed stay as they are, so /resume-work continues where the feature stopped."
  - "Do not resume the work here. Resuming is the engineer's call, ideally in a fresh session."
  - "Feature folders are ignored by git; a background job cannot write them. In a background job, say so and hand off: /new-session \"/reopen-feature <Feature>\"."
```
