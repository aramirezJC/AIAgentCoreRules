## apply: on-demand — loaded by [[CreateFeature/index]]

# Phase 8 — Retrospective

Goal: Extract durable improvements from this feature's implementation cycle. Every answer that becomes a rule, pattern, or system entry reduces cost and back-and-forth on the next feature.

This phase is a conversation — the agent reviews the session, proposes concrete changes, and the engineer confirms before anything is written.

---

## Step 1 — Discovery Gaps

Review what had to be looked up *after* Phase 2 that could have been pre-loaded.

```yaml
questions:
  - Were any source files requested mid-implementation that Phase 2 did not surface?
  - Were any namespaces, base classes, or tool workflows looked up on the fly?
  - Did the agent ask for files the engineer considered "obviously related"?
```

**Output:** additions to the relevant `Systems/` file (`key_interfaces`, `namespaces`, `common_gotchas`, `integration_points.tools`).

---

## Step 2 — Missing Patterns

Review whether any implementation approach was repeated across multiple files or took several cycles to get right.

```yaml
questions:
  - Was any structural pattern applied more than once that is not yet in SystemPatterns/?
  - Did the engineer correct the same type of mistake more than once?
  - Did the design require a non-obvious sequencing or wiring step?
```

**Output:** new `SystemPatterns/` file, or addition to an existing pattern file. Register in `SystemIndex.md`.

---

## Step 3 — Gotchas and Surprises

Review anything that went wrong, required a correction, or was non-obvious.

```yaml
questions:
  - Were any tool steps missed or run in the wrong order?
  - Were any base class behaviors surprising (lifecycle, save mechanics, event wiring)?
  - Were any edge cases in the data or config not covered by the existing gotchas sections?
```

**Output:** additions to `common_gotchas` in the relevant `Systems/` or `SystemPatterns/` file.

---

## Step 4 — Rules Gaps

Review whether any coding standard or architectural rule was applied that is not yet documented.

```yaml
questions:
  - Was any RSS or architectural rule referenced verbally but not present in the rules files?
  - Were there any new access modifier, naming, or resource management situations not covered?
  - Did any test scenario reveal a gap in TestingRules.md?
```

**Output:** proposed additions to `CodingStandards.md`, `ArchitecturalPrinciples.md`, `ResourceManagementRules.md`, or `TestingRules.md`.

---

## Step 5 — Process Gaps

Review whether the phase structure itself caused unnecessary cycles.

```yaml
questions:
  - Was any gate confirmed too early, requiring re-work in a later phase?
  - Was any phase missing a check that would have caught a problem earlier?
  - Was context carried between phases that should be captured in a handoff field?
```

**Output:** proposed edits to the relevant `Phase*.md` or `index.md`.

---

## Step 6 — Session Benchmarks

Before producing the report, compile the session metrics.

```yaml
steps:
  - Run the lifecycle script `compile --final` for this session (done by /end-session).
  - Read metrics.md of this session AND of every session folder listed under `sessions` in [FeatureName]_Progress.md. If the file or list is missing, fall back to folders whose name carries the `feature` lane and this feature's title.
  - Sum tokens, inaccuracies and iterations across those sessions.
  - Use each session's router trace to answer Steps 1 and 5 (what was loaded late, what was never loaded).
  - List the 5 heaviest operations (from the token reports' highest-cost turns, else best estimate).
  - Calculate quality rating per phase: smooth | required_correction | required_redesign.
```

If a session has no metrics.md, note it in the report and estimate from conversation history.

---

## Step 7 — Retrospective Report

Produce a summary of proposed changes before writing anything:

```yaml
retrospective_report:
  feature:            ""
  date:               ""
  systems_touched:    []
  proposed_changes:
    systems_updates:  []   # file: reason
    new_patterns:     []   # file: description
    rules_additions:  []   # file: rule text
    process_updates:  []   # file: change
  deferred:           []   # items that need more data before acting
  benchmarks:
    session_tokens:     ""   # summed from metrics.md of every session of this feature
    estimated_top_costs:     # agent's best estimate of 5 heaviest operations
      - operation: ""
        reason:    ""
    inaccuracy_count:   0    # summed from metrics.md
    iteration_count:    0    # summed from metrics.md
    phase_quality:           # smooth | required_correction | required_redesign
      phase_1_intake:         ""
      phase_2_discovery:      ""
      phase_3_design:         ""
      phase_4_impl:           ""
      phase_5_tests:          ""
      phase_6_integration:    ""
      phase_7_verification:   ""
```

Present the report to the engineer. Do not write any file until the report is confirmed.

---

## Gate 8 — Improvements Applied

Once the engineer approves the report, execute the proposed changes file by file.

Confirm each write with the engineer before advancing to the next.

When an approved change edits a rule, process, skill, tool, Systems or SystemPatterns file,
update the matching `Documentation/` page in the same repository as part of the same change.

Record the outcome in retro.md as an `## Applied` section: one line per proposed change,
`- #N applied: <file> — <what changed>` or `- #N skipped: <reason>` (same format as
`/end-session`, which the session meta-analysis reads).

**The retrospective is complete when all approved changes are written and the engineer confirms.**
