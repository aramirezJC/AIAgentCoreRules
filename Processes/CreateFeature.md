## apply: superseded

# Create Feature — Wizard Process

> **Superseded.** This file has been replaced by `CreateFeature/index.md` and its phase files.
> Load `./CreateFeature/index.md` instead.

---

An interactive, phase-gated process for designing and implementing a new feature collaboratively.

**Prime directive:** Do not advance past any gate without explicit engineer confirmation. Present findings, pause, proceed only when confirmed. Never write code before Gate 3 is cleared.

---

## Phase 1 — Intake

Gather enough context to scope the work and load the right rules.

### Ask the engineer

```yaml
intake_questions:
  feature_name:        "What is the name of this feature?"
  purpose:             "What does it do and what triggers it?"
  owning_system:       "Which system does it belong to? (event, prize, mission, UI, gameplay, new)"
  existing_reference:  "Is there a similar existing feature to use as a reference?"
  success_criteria:    "How do we know it is complete and working correctly?"
  known_constraints:   "Any technical constraints, deadlines, or integration dependencies to be aware of?"
```

### Gate 1 — Scope Confirmed

Present a 2–3 sentence summary covering:
- What the feature is and what it does
- Which system it belongs to
- What done looks like

**Wait for engineer confirmation. Do not proceed to Phase 2 until confirmed.**

---

## Phase 2 — Discovery

### Load rules

Based on Phase 1 answers, load the applicable rule files now. Do not skip this step.

```yaml
load_rules:
  always:
    - ./Rules/StopAndVerify.md
    - ./Rules/CodingStandards.md
    - ./Rules/ArchitecturalPrinciples.md
  if_feature_has_async_flows_queues_or_sequences:
    - ./Rules/MultyStepOperationsRules.md
  if_feature_has_subscriptions_timers_loads_or_guards:
    - ./Rules/ResourceManagementRules.md
  if_tests_are_in_scope:
    - ./Rules/TestingRules.md
```

### Explore the codebase

```yaml
discovery_actions:
  - Find the base class or interface the feature will extend or implement. Read it fully.
  - Find 1–2 existing similar features. Read their implementation files.
  - Inventory every dependency (interface, enum, config, manager) the feature requires.
  - Identify every existing system the feature must integrate with (factories, registries, manifests, publishers).
  - Run the StopAndVerify pre-generation audit — confirm every dependency source is present in context.
```

### Gate 2 — Discovery Report

Present to the engineer:

```yaml
discovery_report:
  files_read:           [list every file read]
  dependencies_found:   [interface/class and where it was found]
  integration_points:   [factories, registries, tools that must be updated]
  missing_source:       [any dependency whose source was not found — block here if non-empty]
  reference_features:   [existing features used as reference]
```

**Do not proceed to Phase 3 if `missing_source` is non-empty. Request the missing files first.**

---

## Phase 3 — Design

Produce a complete design proposal. No implementation code yet — structure and contracts only.

### Design proposal format

```yaml
design_proposal:
  new_files:
    - path: "relative/path/FileName.cs"
      responsibility: "one-line description"
  modified_files:
    - path: "relative/path/FileName.cs"
      change: "one-line description of what changes and why"
  class_structure:
    - "ClassName : BaseClass, IInterface — one-line responsibility"
  public_contracts:
    - "IMyFeature — methods and properties the feature exposes"
  integration_steps:
    - "Step 1: Register in X"
    - "Step 2: Run Y tool"
  open_questions:
    - "Any design ambiguity requiring engineer input before implementation begins"
```

Present the proposal in full. Address all open questions with the engineer before proceeding.

### Gate 3 — Design Approved

Engineer must explicitly approve the design. Capture any revisions. Do not begin writing code until this gate is cleared.

**This is the last gate before code is written. Ensure the design is complete.**

---

## Phase 4 — Implementation

Implement in this order: interfaces → concrete classes → integration glue.

Present each file to the engineer after writing it. Do not move to the next file until the current one is acknowledged.

### Per-file checklist (run after every file)

```yaml
per_file_checks:
  stop_and_verify:     StopAndVerify post-generation checklist passed.
  naming:              All members follow CodingStandards §1 naming conventions.
  organization:        Member order — Constants → Delegates → Events → Fields → Properties → Constructors → Methods.
  method_order:        public override → public → protected override → protected → private.
  accessibility:       No public fields. Setters at maximum restriction. All modifiers explicit.
  resource_symmetry:   Every subscription has unsubscribe. Every acquire has a release. Guards use IDisposable/using.
  method_design:       No method named with "And". Composers sequence only. Leaves touch data only.
```

### Gate 4 — Implementation Complete

All files written and engineer-reviewed. Engineer confirms implementation is ready for integration.

---

## Phase 5 — Integration

Wire the feature into the systems identified in Phase 2.

```yaml
integration_checklist:
  - Registered in all required factories, registries, and manifests.
  - Required code-generation tools executed (parsers, compilers, publishers, conflict resolvers).
  - No manual edits to any auto-generated file.
  - Existing callers or dependent systems updated if a public contract changed.
```

Report each integration step as it is completed.

### Gate 5 — Integration Verified

Confirm with the engineer that all integration steps are done and the project compiles without errors.

---

## Phase 6 — Verification

Final compliance pass before declaring the feature complete.

```yaml
final_verification:
  coding_standards:
    - Naming conventions followed in every file.
    - File organization correct in every file.
    - No accessibility violations.
  architectural:
    - No concrete casts at high-level system boundaries.
    - Every public surface exposed as an interface.
    - No concrete inheritance chains deeper than one level.
  resource_management:
    - Every subscription has a matching unsubscribe.
    - Every resource load has a matching release.
    - No boolean guards — IDisposable/using used for all scoped state.
  tests:
    - Tests written, OR explicitly deferred with engineer agreement and a follow-up task logged.
```

### Gate 6 — Feature Complete

Present a completion summary:

```yaml
completion_summary:
  built:          "What was implemented (1–2 sentences)"
  files_created:  [list]
  files_modified: [list]
  tools_run:      [list]
  deferred:       [anything explicitly left for follow-up]
```

**The feature is complete when the engineer confirms Gate 6.**
