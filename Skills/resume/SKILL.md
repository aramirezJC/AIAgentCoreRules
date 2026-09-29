---
name: resume
description: Resume an in-progress CreateFeature from its <FeatureName>_Progress.md - reload the current phase file, its rules and artifacts, restate where work stopped, and continue after the engineer confirms. Use when the engineer runs /resume <FeatureName> or asks to pick up / continue a feature from a previous session.
argument-hint: "[FeatureName]"
---

# Resume

Paths are relative to the AIAgentCoreRules root (the parent of the `Rules/` folder that holds
MetaRouter.md). Load files with Read, not shell `cat`, so the router trace records them.

## Step 1 — Find the feature

```yaml
steps:
  - "If $ARGUMENTS names a feature: progress file is <working_folder>/<FeatureName>_Progress.md (working_folder from Processes/CreateFeature/index.md)."
  - "If no name was given: list every *_Progress.md under the Features folder whose status is not complete, with current_phase and updated_at, ask which one, and stop."
  - "If the file does not exist: say so and offer /feature <FeatureName> to start it. Stop."
  - "Run: python3 <lifecycle script> set --lane feature --title \"<FeatureName>\""
  - "Add the current session folder name to `sessions` in the progress file."
```

## Step 2 — Reload

```yaml
reload:
  - "Read: Processes/CreateFeature/index.md"
  - "Read: the progress file in full."
  - "Read: the phase file for current_phase."
  - "Read: the rule files that phase depends on — for Phase 2 and later, the load_rules list in Phase2_Discovery.md, using [FeatureName]_Discovery.md to decide the conditional ones."
  - "Read: the artifacts the current phase works from (e.g. TDD and TaskList for Phase 1–3, Architecture and Discovery for Phase 4, UseCases for Phase 5). Skip ones it does not use."
  - "Checkpoint lists files in `done`: confirm they exist on disk (one ls / codeindex query). Do not re-read their bodies unless the next step needs them."
```

## Step 3 — Restate and confirm

Present, then wait for the engineer:

```yaml
resume_summary:
  feature:           ""
  phase:             ""      # current_phase and its gate from index.md
  gates_passed:      []      # phase names only
  done_this_phase:   []
  in_flight:         ""
  next:              ""
  pending_decisions: []
  drift:             []      # anything on disk that disagrees with the progress file (missing file, extra file, git changes since updated_at)
```

**Do not continue until the engineer confirms.** If they correct the summary, update the
Checkpoint first, then continue from the corrected `next`.
