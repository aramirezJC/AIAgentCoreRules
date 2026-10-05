---
name: feature
description: Start the full gated CreateFeature process (GDD to TDD, discovery, design, implementation, tests, integration, verification, retrospective) for a named feature. Use when the engineer runs /feature <Name> or accepts an investigation's recommendation to build.
argument-hint: "<FeatureName> [path to GDD]"
---

# Feature

Paths are relative to the AIAgentCoreRules root (the parent of the `Rules/` folder that holds
MetaRouter.md).

```yaml
steps:
  - "Run: python3 <lifecycle script> set --lane feature --title \"$ARGUMENTS\" --feature \"$ARGUMENTS\" --phase 1_intake"
  - "Read: Processes/CreateFeature/index.md"
  - "If <working_folder>/<FeatureName>_Progress.md already exists: show its current_phase and updated_at, offer /resume <FeatureName>, and stop — do not restart Phase 1 over existing work."
  - "Create <FeatureName>_Progress.md from Processes/Templates/Progress_Template.md and add the current session folder to `sessions`."
  - "Read: Processes/CreateFeature/Phase1_Intake.md and start it. If a GDD path was given, begin with Sub-phase 1a."
```

Load one phase file at a time. Never pass a gate without explicit engineer confirmation, and
write each gate's handoff to the progress file before closing the session. Each phase runs in
its own session (CreateFeature/index.md, "One Session per Phase").
