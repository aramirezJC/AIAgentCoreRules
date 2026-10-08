---
name: bug-fix
description: Start the BugFix process (diagnosis, approved fix, regression test) for a reported bug without classifying the mode first. Use when the engineer runs /bug-fix <symptom>.
argument-hint: "<symptom, error or ticket>"
---

# Bug Fix

Paths are relative to the AIAgentCoreRules root (the parent of the `Rules/` folder that holds
MetaRouter.md). The engineer chose the lane, so skip MetaRouter's "Classify the Mode".

```yaml
steps:
  - "Run: python3 <lifecycle script> set --lane bug_fix --work-type bug_fix --title \"<short title from $ARGUMENTS>\""
  - "Read: Processes/BugFix.md and follow it from its first step with $ARGUMENTS as the symptom."
  - "No arguments → ask for the symptom, repro steps or log, then continue."
```

Diagnose before fixing: no code until the engineer approves the fix, as BugFix.md requires.
