## apply: on-demand — loaded by [[MetaRouter]]

# Create Feature — Process Index

Interactive wizard for designing and implementing a new feature. Load one phase file at a time. Do not advance past any gate without explicit engineer confirmation.

```yaml
working_folder: "Assets/GitIgnoreAssets/Features/<FeatureName>/   # GDD, TDD, TaskList, UseCases, Discovery, Architecture docs"
progress_file:  "<working_folder>/<FeatureName>_Progress.md        # resume state — template: ../Templates/Progress_Template.md"
session_metrics: "per session, in the Session tracking folder — see MetaRouter Session Lifecycle"
```

A feature usually spans several sessions. Each session gets its own metrics; the Phase 8
retrospective reads all of them, using the `sessions` list in the progress file.

---

## Progress File — resuming across sessions

Chat context does not survive a session end or a summary. The progress file does.

```yaml
progress_file:
  create:     "At the start of Phase 1, from ../Templates/Progress_Template.md, if it does not exist."
  on_session: "Add the current session folder name (from the Session tracking block) to `sessions` the first time this session writes the file."
  on_gate:    "Append the phase_handoff block (below) under 'Gates Passed', set current_phase to the next phase, clear the Checkpoint section, update artifacts."
  mid_phase:  "/checkpoint replaces the Checkpoint section — where work stopped and what comes next."
  on_resume:  "/resume <FeatureName> reads this file, reloads the current phase and its artifacts, and confirms with the engineer before continuing."
```

Write the gate block **before** loading the next phase file. A gate that is confirmed in chat
but not written to the progress file is lost to the next session.

---

## Phases

```yaml
phases:
  1_intake:
    file: ./Phase1_Intake.md
    goal: Convert GDD to structured documents, identify tasks and edge cases, confirm scope
    gate: TDD, task list, use cases, and edge cases reviewed and approved by engineer
    recommended_agent: general-purpose
    recommended_model: sonnet

  2_discovery:
    file: ./Phase2_Discovery.md
    goal: Load rules, explore codebase, confirm all dependencies are visible
    gate: Discovery report approved — no missing source files
    recommended_agent: explore        # use /discover <SystemName> for targeted area surveys
    recommended_model: haiku          # pure search, no generation

  3_design:
    file: ./Phase3_Design.md
    goal: Propose architecture, class structure, public contracts, integration points
    gate: Design explicitly approved — NO CODE WRITTEN BEFORE THIS GATE
    recommended_agent: plan
    recommended_model: sonnet

  4_implementation:
    file: ./Phase4_Implementation.md
    goal: Write code file-by-file with per-file engineer acknowledgment
    gate: All files written and engineer-reviewed
    recommended_agent: general-purpose
    recommended_model: sonnet         # run /audit on each file before presenting it

  5_unit_tests:
    file: ./Phase5_UnitTests.md
    goal: JSON deserialization tests + behavior and boundary tests traced to UseCases.md
    gate: All tests passing, TBD cases logged as follow-up tasks
    recommended_agent: general-purpose
    recommended_model: sonnet

  6_integration:
    file: ./Phase6_Integration.md
    goal: Wire feature into factories, registries, manifests; run required tools
    gate: Project compiles, all integration steps confirmed
    recommended_agent: explore        # verify integration points exist before editing
    recommended_model: haiku

  7_verification:
    file: ./Phase7_Verification.md
    goal: Final rules compliance pass across all files
    gate: Engineer confirms feature complete
    recommended_agent: explore        # grep for rule violations, no generation needed
    recommended_model: haiku

  8_retrospective:
    file: ./Phase8_Retrospective.md
    goal: Identify discovery gaps, missing patterns, gotchas, and process improvements; write approved changes to metadata files
    gate: All approved changes written and confirmed by engineer
    recommended_agent: general-purpose  # run via /end-session
    recommended_model: sonnet
```

---

## Handoff Format

At every gate, produce this summary and append it to the progress file before loading the next
phase file:

```yaml
phase_handoff:
  phase_completed:   "Phase N — Name"
  gate_confirmed_by: "confirmed"
  key_decisions:     [decisions made this phase]
  carry_forward:     [information the next phase needs]
  open_items:        [anything deferred or unresolved]
```

---

## Templates

```yaml
templates:
  tdd:      ../Templates/TDD_Template.md        # fill during Phase 1
  progress: ../Templates/Progress_Template.md   # create at the start of Phase 1
```
