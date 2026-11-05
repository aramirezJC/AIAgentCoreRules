---
name: large-task
description: Start the LargeTask process for a change bigger than a small task but without a feature outline - a tool, a framework or shared-infrastructure change, a cross-system refactor - with discovery, an approved plan.md and stepwise implementation, finished within one session. Use when the engineer runs /large-task <description>.
argument-hint: "<what to build or change>"
---

# Large Task

Paths are relative to the AIAgentCoreRules root (the parent of the `Rules/` folder that holds
MetaRouter.md). The engineer chose the lane, so skip MetaRouter's "Classify the Mode".

```yaml
steps:
  - "Step 0 — /start-session: if no 'Session tracking' block is in context, run: python3 Tools/session-lifecycle/session_lifecycle.py hook-start, and use the lifecycle script and session_id it prints below. If the engineer named the session, add --name \"<name>\" to the set."
  - "Run: python3 <lifecycle script> set --lane large_task --work-type large_feature --title \"<short title from $ARGUMENTS>\"   # --work-type other for tooling, framework, config or rule edits"
  - "If the work is for an in-progress CreateFeature feature (named in the ask, or the active-features list fits it), add --feature \"<FeatureName>\" to that set, so the feature's Performance tab counts this session."
  - "Read: Processes/LargeTask.md and follow it from 1_scope with $ARGUMENTS as the request."
  - "No arguments → ask what to build or change, then continue."
```

A large task finishes in this session. No code before plan.md is approved; if the work cannot be
finished here, or outgrows LargeTask's limits, stop and offer `/feature <Name>`.
