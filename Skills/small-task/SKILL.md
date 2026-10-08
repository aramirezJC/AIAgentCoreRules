---
name: small-task
description: Start the SmallTask process for a bounded change - a tool, utility, debug command or behaviour tweak modelled on existing code - without classifying the mode first. Use when the engineer runs /small-task <description>.
argument-hint: "<what to build or change>"
---

# Small Task

Paths are relative to the AIAgentCoreRules root (the parent of the `Rules/` folder that holds
MetaRouter.md). The engineer chose the lane, so skip MetaRouter's "Classify the Mode".

```yaml
steps:
  - "Run: python3 <lifecycle script> set --lane small_task --work-type small_feature --title \"<short title from $ARGUMENTS>\"   # --work-type other for tooling, config or rule edits"
  - "Read: Processes/SmallTask.md and follow it from 1_scope with $ARGUMENTS as the request."
  - "No arguments → ask what to build or change, then continue."
```

SmallTask's limits still apply: if the work outgrows them, stop and offer `/feature <Name>`.
