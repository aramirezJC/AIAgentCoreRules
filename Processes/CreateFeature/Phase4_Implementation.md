## apply: on-demand — loaded by [[CreateFeature/index]]

# Phase 4 — Implementation

Goal: Write code file-by-file following the approved design. Present each file to the engineer before moving to the next.

Implement in this order: **interfaces → concrete classes → integration glue.**

Before the first file: re-read `../../Rules/CodingStandards.md` and `../../Rules/ArchitecturalPrinciples.md`
(and ResourceManagementRules / MultyStepOperationsRules if Phase 2 loaded them). Phase 2 may be
several sessions or a context summary ago.

---

## Per-File Checklist

Run after writing every file. Do not present a file to the engineer until all checks pass.

```yaml
per_file_checks:
  stop_and_verify:   "StopAndVerify post-generation checklist passed."
  naming:            "All members follow CodingStandards §1 naming conventions."
  organization:      "Constants → Delegates → Events → Fields → Properties → Constructors → Methods."
  method_order:      "public override → public → protected override → protected → private."
  accessibility:     "No public fields. Setters at maximum restriction. All modifiers explicit."
  resource_symmetry: "Every subscription has unsubscribe. Every acquire has release. Guards use IDisposable/using."
  method_design:     "No method named with And. Composers sequence only. Leaves touch data only."
  audit:             "REQUIRED: /audit <file> ran and every violation is fixed or reported. It covers the checks above; self-review is not a substitute."
```

Run `/audit <file>` before presenting each file — a file is not presented until its audit has
run. Present each file to the engineer after writing it. Do not move to the next file until the
current one is acknowledged.

After each acknowledgment, update the progress file's Checkpoint: add the file to `done`, marked
`(audited)`, and set `next` to the following file from the design. Implementation is where a session most often
ends mid-phase.

---

## Gate 4 — Implementation Complete

All files written and engineer-reviewed. Engineer confirms implementation is ready for integration.
