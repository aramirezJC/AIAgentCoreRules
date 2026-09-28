## apply: always

# Stop and Verify Protocol

Run before generating any code. If a check fails, look the missing piece up yourself first (Read, codeindex, /discover). Stop and ask only when it cannot be found.
Tag definitions: [[CoreTags]]

---

## Scope Gate — before exploring, not just before generating

Fires when the request is for a **tool, script, report, or utility**. One question, asked before any
exploration, because the wrong answer discards the exploration too.

```yaml
scope_gate:
  - "[SHAPE] Is the deliverable a one-off answer, or a reusable tool? Ask — do not infer."
  - "[SHAPE] If a tool: where does it run — Editor, runtime, or CLI? This constrains the assembly and the base class."
  - "[SHAPE] If exploration would already answer the question, say so and offer the answer first."
```

Ask it as a plain question and wait. Do not resolve the ambiguity by building both, by planning
the larger one, or by picking the more impressive one.

> Exploration undertaken to scope a tool is often already the tool's output. Check before
> designing the thing that would reproduce work you have just done.

## Pre-Generation Checklist

```yaml
pre_generation:
  - "[CTX] Inventory every interface, class, enum, and base type the solution requires. Confirm each is present in context."
  - "[SIG] Locate every property, method, and field you intend to use in the provided source text."
  - "[SO]  Verify Unity ScriptableObjects use CreateInstance<T>(), never new T()."
```

## Stop Output Format

When a dependency is missing, first search for it (codeindex.py where, Read, /discover). Only if
it is not in the repository — an external package, an unmerged branch, a server contract —
output this before any code:

> I cannot implement `[Class]` because `[Dependency]` is not in the repository (searched: `[queries run]`). Please provide `[Dependency.cs]` or point me to it.

Do not generate partial code while waiting. Do not guess.

## Post-Generation Verification

```yaml
post_generation:
  - "[SIG]  No API signatures were guessed — every call is grounded in provided source."
  - "[PRES] All existing comments, regions, and TODOs are preserved unchanged."
  - "[SURG] Only the required lines were changed — surrounding code is character-perfect."
```
