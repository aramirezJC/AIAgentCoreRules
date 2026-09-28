## apply: on-demand — loaded by [[MetaRouter]]

# Create Feature — Process Index

Interactive wizard for designing and implementing a new feature. Load one phase file at a time. Do not advance past any gate without explicit engineer confirmation.

```yaml
working_folder: "Assets/GitIgnoreAssets/Features/<FeatureName>/   # GDD, TDD, TaskList, UseCases, Architecture docs"
session_metrics: "per session, in the Session tracking folder — see MetaRouter Session Lifecycle"
```

A feature usually spans several sessions. Each session gets its own metrics; the Phase 8
retrospective reads all of them (their folders carry the `feature` lane in the name).

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

At every gate, produce this summary before loading the next phase file:

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
  tdd: ../Templates/TDD_Template.md   # fill during Phase 1
```
