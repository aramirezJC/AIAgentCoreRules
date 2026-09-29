---
name: checkpoint
description: Save mid-phase CreateFeature progress to the feature's <FeatureName>_Progress.md so a later session can pick up with /resume. Use when the engineer runs /checkpoint, is about to stop partway through a phase, or when /end-session closes a feature session that is not at a gate.
argument-hint: "[FeatureName] [note]"
---

# Checkpoint

Paths are relative to the AIAgentCoreRules root (the parent of the `Rules/` folder that holds
MetaRouter.md). The progress file lives in the feature's working folder — see
`Processes/CreateFeature/index.md` ("Progress File").

```yaml
steps:
  - "Feature name: the first word of $ARGUMENTS, else the session title (feature lane), else ask and stop."
  - "Progress file: <working_folder>/<FeatureName>_Progress.md. If missing, create it from Processes/Templates/Progress_Template.md."
  - "Add the current session folder name (Session tracking block) to `sessions` if it is not already listed."
  - "Replace the Checkpoint section with the state of the current phase, from this conversation only:"
  - "  done:              steps / files finished and engineer-acknowledged this phase"
  - "  in_flight:         the step or file in progress and how far it got — 'none' if between steps"
  - "  next:              the single next action on resume, concrete enough to start without re-reading chat"
  - "  pending_decisions: questions waiting on the engineer"
  - "  context_notes:     facts learned this phase that are not in any artifact yet (file:line where possible); include the rest of $ARGUMENTS as a note"
  - "Update current_phase, status, updated_at and artifacts in the header block."
  - "Reply with one line: the progress file path and the `next` action."
```

## Rules

```yaml
rules:
  - "Never edit or rewrite a block under 'Gates Passed' — those are the gate record."
  - "Record only what the engineer acknowledged as done. Unreviewed work goes in in_flight."
  - "Do not copy artifact content into the checkpoint — list the artifact, the next session reads it."
  - "Keep the Checkpoint section under ~40 lines; it is reloaded at the start of every resumed session."
```
