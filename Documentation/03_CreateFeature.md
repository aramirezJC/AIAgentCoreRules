# Create Feature Process

The full process for building a new feature, from GDD to verified, integrated code. It runs as
an interactive wizard of **8 phases**, each ending in a **gate** that the engineer must
explicitly confirm. The agent loads one phase file at a time and never passes a gate on its own.

Start it with `/feature <FeatureName> [path to GDD]`.

## Working folder

Everything the process produces for a feature lives in one folder in the host project (under a
personal, git-ignored path set in `CreateFeature/index.md`):

```
Assets/GitIgnoreAssets/Features/<FeatureName>/
  <FeatureName>_GDD.md           AI-friendly copy of the source GDD
  <FeatureName>_TDD.md           Technical design document
  <FeatureName>_TaskList.md      Ordered tasks from the development plan
  <FeatureName>_UseCases.md      Use cases and edge cases
  <FeatureName>_Discovery.md     Approved discovery report
  <FeatureName>_Architecture.md  Approved class and sequence diagrams
  <FeatureName>_Progress.md      Resume state: gates passed and the current checkpoint
```

## The phases

| # | Phase | Goal | Gate |
|---|---|---|---|
| 1 | **Intake** | Convert the GDD into a TDD, task list, use cases and edge cases | All documents reviewed and approved; every TBD item has an owner |
| 2 | **Discovery** | Load rules, explore the codebase, confirm every dependency is visible | Discovery report approved, with no missing source files |
| 3 | **Design** | Propose architecture, class structure, public contracts, integration points and diagrams | Design explicitly approved — **no code is written before this gate** |
| 4 | **Implementation** | Write code file by file | Every file written, audited and acknowledged by the engineer |
| 5 | **Unit Tests** | JSON deserialization, behavior and boundary tests traced to the use cases | All tests passing; deferred cases logged as follow-up tasks |
| 6 | **Integration** | Wire into factories, registries and manifests; run generators | Project compiles; every integration step confirmed |
| 7 | **Verification** | Final rules-compliance pass across every file | Engineer confirms the feature is complete |
| 8 | **Retrospective** | Find discovery gaps, missing patterns, gotchas and process gaps; apply approved improvements | Every approved change written and confirmed |

### Phase 1 — Intake

- **1a GDD conversion** — if a GDD is provided, it is converted to Markdown in full, without
  summarising.
- **1b TDD, section by section** — objective, architecture, related docs, development plan
  (stages with T-shirt sizes and assignees), final touches, tools, risks, data reconciliation
  strategy, CS strategy, edge cases, notes and future work. Each section is agreed with the
  engineer before moving on. The data reconciliation strategy cannot be left blank; if it is
  undecided it is marked TBD and logged as an open item.
- **1c consistency and gap review**, **1d metrics**, **1e document generation**.

### Phase 2 — Discovery

The agent loads Stop and Verify, Coding Standards and Architectural Principles, plus
Multi-Step Operations, Resource Management and Testing rules when the feature needs them. It
then reads the base class or interface being extended and 1–2 similar existing features,
inventories dependencies and integration points, and checks the host project's SystemIndex for
existing Systems and SystemPatterns entries. Wide surveys go through `/discover`.

The gate report lists files read, dependencies found, integration points, reference features
and **missing source** — a non-empty missing-source list blocks the gate.

### Phase 3 — Design

A structural proposal (new and modified files, class structure, public contracts, integration
steps, open questions), followed by two Mermaid diagrams: a class diagram and a sequence
diagram. The engineer reviews and edits both before approving.

### Phase 4 — Implementation

Order: interfaces → concrete classes → integration glue. Before the first file the agent
re-reads the rule files, because Phase 2 may be several sessions ago. Every file runs through
`/audit` and is presented to the engineer; the next file is not started until the current one
is acknowledged.

### Phase 5 — Unit Tests

Three categories, each traced to a document from an earlier phase — no speculative tests:

- one JSON deserialization test per config class,
- one behavior test per row in the use cases,
- one boundary test per edge case.

The agent runs the host project's compile check (`typecheck.py`); the engineer runs the tests in the Unity Test Runner and
reports the result. The agent never claims a pass it has not seen.

### Phase 6 — Integration

Registration in factories, registries and manifests, and running code generators. Editor-only
generators (for example a JSON parser generator window) are listed with exact menu paths for
the engineer to run.

### Phase 7 — Verification

Final check of naming, file organization, accessibility, interface boundaries, resource
symmetry and tests, closing with a completion summary of what was built, files created and
modified, tools run and anything deferred.

### Phase 8 — Retrospective

Run through `/end-session` (see [[07_SessionTracking#Retrospectives|Retrospectives]]). It reads the metrics of **every** session that worked on the
feature and proposes changes to Systems docs, patterns, rules and processes. Nothing is written
until the engineer approves the report, and each change is confirmed individually. A change to
a rule, process or Systems doc also updates its `Documentation/` page.

## Gate handoffs

At every gate the agent produces a handoff summary:

```yaml
phase_handoff:
  phase_completed:   "Phase N — Name"
  gate_confirmed_by: "confirmed"
  key_decisions:     []
  carry_forward:     []   # what the next phase needs
  open_items:        []   # deferred or unresolved
```

This block is appended to the feature's progress file **before** the session closes.

## One session per phase

Each phase runs in its own session. Context stays small, metrics show what each phase cost,
and each phase can start on its recommended model. When the engineer confirms a gate, the agent:

1. writes the handoff block and advances the progress file,
2. runs `/end-session`, which writes a short retro for the phase (the full retrospective is
   Phase 8, which reads all of them),
3. prints the command for the next phase and stops, for example
   `claude --model haiku "/resume MyFeature"`.

A phase that takes several sittings ends each one with `/checkpoint`; the next sitting is a new
session for the same phase. To keep going in the same session anyway, say so at the gate, and
the reason is recorded in the gate block.

## Working across sessions — checkpoint and resume

A feature usually spans several sessions, and chat context does not survive a session ending or
being summarised. The progress file (`<FeatureName>_Progress.md`) does.

| Event | What is written to the progress file |
|---|---|
| `/feature <Name>` | File created from the template; the session is added to its session list |
| Every gate | The handoff block is appended; the current phase advances; the checkpoint is cleared; the session closes with a phase retro |
| Each approved file in Phase 4 | The file is added to the checkpoint's `done` list and `next` is set |
| `/checkpoint` | The checkpoint is replaced: done, in flight, next action, pending decisions, notes |
| `/end-session` mid-phase | `/checkpoint` runs automatically first |

To continue in a new session, run **`/resume <FeatureName>`**. The agent:

1. switches the session to the feature lane and adds the session to the feature's list,
2. reloads the process index, the progress file, the current phase file, that phase's rule
   files and the documents it works from,
3. checks the files on disk against the progress file and reports any drift,
4. presents a summary — phase, gates passed, what is done, what is next, pending decisions —
   and **waits for confirmation** before continuing.

`/resume` with no name lists every feature that is not complete. Running `/feature` on a
feature that already has a progress file offers `/resume` instead of restarting Phase 1.

Why not just reopen the old conversation? Reopening brings back the whole previous context,
including rule files that may already have been summarised away. A resume starts clean and
loads only what the current phase needs.

**Source files:** [[CreateFeature/index]] · [[Phase1_Intake]] · [[Phase2_Discovery]] · [[Phase3_Design]] · [[Phase4_Implementation]] · [[Phase5_UnitTests]] · [[Phase6_Integration]] · [[Phase7_Verification]] · [[Phase8_Retrospective]] · [[Progress_Template]] · [[TDD_Template]] · [[Skills/feature/SKILL|/feature]] · [[Skills/checkpoint/SKILL|/checkpoint]] · [[Skills/resume/SKILL|/resume]]

---

← [[02_WorkModes|Work Modes and Routing]] · [[00_Overview|Overview]] · [[04_BugFix|Bug Fix Process]] →
