---
name: feature
description: Start the full gated CreateFeature process (GDD to TDD, discovery, design, implementation, tests, integration, verification, retrospective) for a named feature. Use when the engineer runs /feature <Name> or accepts an investigation's recommendation to build.
argument-hint: "<FeatureName> [path to GDD]"
---

# Feature

## Authoritative feature state

Read `Processes/FeatureState.md` for the shared tool contract. `state.json` is authoritative;
Progress Markdown is generated. All legacy references below to editing progress mean tool
operations, never direct Markdown/JSON edits. Use focused `get`, revision-checked mutations,
and explicit migration for legacy features. Preserve engineer approval gates.


Create with `python3 <state-tool> create <feature-directory>`; then use checkpoint to record the current session and initial intake state. Refuse to restart when either state.json or legacy Progress Markdown already exists.


Paths are relative to the AIAgentCoreRules root (the parent of the `Rules/` folder that holds
MetaRouter.md).

```yaml
steps:
  - "Step 0 — /start-session: if no 'Session tracking' block is in context, run: python3 Tools/session-lifecycle/session_lifecycle.py hook-start, and use the lifecycle script and session_id it prints below. If the engineer named the session, add --name \"<name>\" to the set."
  - "Run: python3 <lifecycle script> set --lane feature --title \"$ARGUMENTS\" --feature \"$ARGUMENTS\" --phase 1_intake"
  - "Read: Processes/CreateFeature/index.md"
  - "If <working_folder>/state.json or legacy <FeatureName>_Progress.md already exists: read its state (or report explicit migration required), show current_phase and updated_at, offer /resume-work <FeatureName>, and stop — do not restart Phase 1 over existing work."
  - "Create state with the feature-state CLI and record the current session through checkpoint; Progress Markdown is generated."
  - "Read: Processes/CreateFeature/Phase1_Intake.md and start it. If a GDD path was given, begin with Sub-phase 1a."
```

Load one phase file at a time. Never pass a gate without explicit engineer confirmation, and
write each gate's handoff to the progress file before closing the session. Each phase runs in
its own session (CreateFeature/index.md, "One Session per Phase").
