---
name: run-investigation-mode
description: Start Investigation Mode - a feasibility study, comparison, hypothetical refactor, "where does X happen" survey or design document; output is a document or recommendation, not code - without classifying the mode first. Use when the engineer runs /run-investigation-mode <question>.
argument-hint: "<question to investigate>"
---

# Run Investigation Mode

Paths are relative to the AIAgentCoreRules root (the parent of the `Rules/` folder that holds
MetaRouter.md). The engineer chose the lane, so skip MetaRouter's "Classify the Mode".

```yaml
steps:
  - "Run: python3 <lifecycle script> set --lane investigation --work-type question --title \"<short title from $ARGUMENTS>\"   # --work-type bug_fix when investigating a crash or defect"
  - "Read: Rules/InvestigationMode.md and follow it with $ARGUMENTS as the question."
  - "No arguments → ask for the question, then continue."
```

The output is a document or recommendation. If the answer is to build or fix something, offer
the lane change (`/small-task`, `/bug-fix`, `/feature`) — do not start writing code.
