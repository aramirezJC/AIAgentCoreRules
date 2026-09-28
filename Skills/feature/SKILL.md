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
  - "Run: python3 <lifecycle script> set --lane feature --title \"$ARGUMENTS\""
  - "Read: Processes/CreateFeature/index.md"
  - "Read: Processes/CreateFeature/Phase1_Intake.md and start it. If a GDD path was given, begin with Sub-phase 1a."
```

Load one phase file at a time. Never pass a gate without explicit engineer confirmation.
