## apply: on-demand — loaded by [[CreateFeature/index]]

# Phase 4 — Implementation

Goal: Write code file-by-file following the approved design. Present each file to the engineer before moving to the next.

Implement in this order: **interfaces → concrete classes → integration glue.**

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
```

Present each file to the engineer after writing it. Do not move to the next file until the current one is acknowledged.

---

## Gate 4 — Implementation Complete

All files written and engineer-reviewed. Engineer confirms implementation is ready for integration.
