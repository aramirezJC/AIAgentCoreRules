## apply: on-demand — loaded by [[MetaRouter]]

# Small Task

For a bounded change: a tool, utility, debug command, or behaviour tweak modelled on existing
code. Smaller than a feature — no GDD, TDD, or task list. If the work grows past the limits
below, stop and offer `/feature <Name>`.

Tag definitions: [[CoreTags]]

```yaml
fits_when:
  - "Touches one system and at most ~5 files"
  - "No new config root, player-data schema, or server contract"
  - "An existing example can be followed ('like xyz, but does abc')"
escalate_when:
  - "Any fits_when condition breaks mid-task → stop, say so in one line, offer /feature"
```

---

## Steps

```yaml
steps:
  1_scope:
    - "If the request is a tool/script/report: StopAndVerify Scope Gate — ask one-off vs reusable, and Editor/runtime/CLI. Wait."
    - "Restate the deliverable in one line: what it does, where it runs, what it is modelled on."
  2_context:
    - "SystemIndex: Read the Systems/ entry for the owning system, and the SystemPatterns/ file if one matches."
    - "Model example: codeindex.py where/members <Example>; Read only the bodies you will copy the shape of."
    - "Anything broader than one targeted query → /discover, not inline search."
    - "If the change sends or listens for a message/event: read every listener's handler before choosing dispatch points — how often it fires changes what the listener computes."
  3_rules:   # routing table, by what the change touches
    always:                    [../Rules/CodingStandards.md]
    new_class_or_interface:    [../Rules/ArchitecturalPrinciples.md]
    subscriptions_timers_loads:[../Rules/ResourceManagementRules.md]
    async_sequences:           [../Rules/MultyStepOperationsRules.md]
    tests_requested:           [../Rules/TestingRules.md]
  4_propose:
    - "Before writing: list files to create/modify, one line each. Wait for OK only if more than 2 files or any public contract changes."
  5_implement:
    - "StopAndVerify pre-generation checks, then write."
    - "Run /audit on the changed files."
  6_verify:
    - "Run typecheck.py. Report its result verbatim if it fails."
    - "Tell the engineer how to try it (menu path, debug command, steps). Editor-only steps are theirs to run."
  7_close:
    - "Offer /end-session."
```

## Router check (used by /end-session)

```yaml
expected_loads:
  - "Systems/<owning system>.md (if it exists)"
  - "Rules/CodingStandards.md"
  - "plus each 3_rules row the change matched"
expected_tools: [codeindex.py, typecheck.py]
```
