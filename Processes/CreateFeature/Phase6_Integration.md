## apply: on-demand — loaded by [[CreateFeature/index]]

# Phase 6 — Integration

Goal: Wire the feature into all systems identified in Phase 2. Report each step as it is completed.

---

## Integration Checklist

```yaml
integration_checklist:
  - Registered in all required factories, registries, and manifests.
  - Required code-generation tools executed (parsers, compilers, publishers, conflict resolvers).
  - "[GEN]"
  - Existing callers or dependent systems updated if a public contract changed.
```

---

## Gate 6 — Integration Verified

Run `/audit` on every C# file this phase changed (registrations, installers, updated callers);
generated files are excluded ([GEN]). Then run the host compile check (TripleMatch: `typecheck.py`) and report its result. Editor-only
generators (e.g. ParserGeneratorWindow) are run by the engineer — list them with exact menu paths.
Confirm with the engineer that all integration steps are complete and the project compiles without errors.
