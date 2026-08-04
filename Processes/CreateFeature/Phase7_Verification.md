## apply: on-demand — loaded by [[CreateFeature/index]]

# Phase 7 — Verification

Goal: Final rules compliance pass across all files before declaring the feature done.

---

## Verification Checklist

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
    - All tests passing.
    - TBD edge cases logged as follow-up tasks with owners.
```

---

## Gate 7 — Feature Complete

```yaml
completion_summary:
  built:          ""
  files_created:  []
  files_modified: []
  tools_run:      []
  deferred:       []
```

**The feature is complete when the engineer confirms Gate 7.**
