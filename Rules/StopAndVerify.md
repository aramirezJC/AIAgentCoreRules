## apply: always

# Stop and Verify Protocol

Run before generating any code. If any check fails, stop and request the missing information before continuing.

---

## Pre-Generation Checklist

```yaml
pre_generation:
  - Inventory every interface, class, enum, and base type the solution requires.
  - Confirm source code or full signature for each dependency is present in context.
    on_fail: STOP — request the missing file.
  - Locate every property, method, and field you intend to use in the provided source text.
    on_fail: STOP — do not assume or infer signatures.
  - Verify Unity ScriptableObjects use CreateInstance<T>(), never new T().
```

## Stop Output Format

When a dependency is missing, output this before any code:

> I cannot implement `[Class]` because I have not seen the definition for `[Dependency]`. Please provide `[Dependency.cs]`.

Do not generate partial code while waiting. Do not guess.

## Post-Generation Verification

```yaml
post_generation:
  - No API signatures were guessed — every call is grounded in provided source.
  - No property or field was used that was not physically found in the source text.
  - All existing comments, regions, and TODOs are preserved unchanged.
  - Only the required lines were changed — surrounding code is character-perfect.
```
