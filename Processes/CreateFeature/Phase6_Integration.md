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

Once all integration steps are verified, generate an integration summary as `[FeatureName]_Integration.md`
covering each checklist item and its completion status. Register it:

```
python3 Tools/feature-state/feature_state.py phase-report <feature_dir> \
  --payload '{"phase": "6_integration", "path": "[FeatureName]_Integration.md"}' \
  --revision <N>
```

Then present the report to the engineer for approval.

Confirm with the engineer that all integration steps are complete and the project compiles without errors.
