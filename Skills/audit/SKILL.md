---
name: audit
description: Check C# files against the coding standards, architectural principles, resource rules and core tags, and report violations with file:line. Use before presenting a file in Phase 4, in Phase 7 verification, or when the engineer runs /audit.
argument-hint: "[file ...]  (default: changed .cs files)"
---

# Audit

Paths are relative to the AIAgentCoreRules root (the parent of the `Rules/` folder that holds
MetaRouter.md).

```yaml
scope:
  files:   "$ARGUMENTS, or every changed .cs file from `git status --porcelain` when empty"
  load:    [Rules/CodingStandards.md, Rules/ArchitecturalPrinciples.md, Rules/ResourceManagementRules.md]
  also:    "CoreTags, StopAndVerify post-generation checks, and the host project's rules (already in context)"
checks:
  - "Phase 4 per-file checklist: naming, organization, method order, accessibility, resource symmetry, method design"
  - "Tags: [EXPLICIT] [ALLMAN] [ACCESS] [FIELD] [DI] [IFACE] [RES] [SYM] [ASYNC] [LOG] [SRP] [GEN]"
  - "Project rules: #if !RC around debug/mock code, Logger channel setup, JCConfigUtil config loading"
```

For more than 5 files, fan out: one agent per group of files, same brief, results merged.

Report:

```yaml
audit_report:
  files_checked:  []
  violations:     # rule tag · file:line · what · minimal fix
    - ""
  clean:          []
```

Report only. Do not edit unless the engineer asks; when fixing, apply [SURG] — change only the
violating lines.
