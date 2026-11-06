## apply: on-demand — loaded by [[CreateFeature/index]]

# Phase 2 — Discovery

Goal: Load the right rules, explore the codebase, and confirm every dependency is visible before any design work begins.

---

## Load Rules

Based on the Phase 1 TDD and task list, load the applicable rule files. Do not skip this step.

```yaml
load_rules:
  always:
    - ../../Rules/StopAndVerify.md
    - ../../Rules/CodingStandards.md
    - ../../Rules/ArchitecturalPrinciples.md
  if_async_flows_queues_or_sequences:
    - ../../Rules/MultyStepOperationsRules.md
  if_subscriptions_timers_loads_or_guards:
    - ../../Rules/ResourceManagementRules.md
  if_tests_in_scope:
    - ../../Rules/TestingRules.md
```

---

## Explore the Codebase

```yaml
discovery_actions:
  - Find the base class or interface the feature will extend or implement. Read it fully.
  - Find 1–2 existing similar features. Read their implementation files.
  - Inventory every dependency (interface, enum, config, manager) the feature requires.
  - Identify every existing system the feature must integrate with (factories, registries, manifests, publishers).
  - Run the StopAndVerify pre-generation audit — confirm every dependency source is present in context.
```

---

## Gate 2 — Discovery Report

Once discovery_actions are complete, generate the discovery report as `[FeatureName]_Discovery.md`
documenting:

```yaml
discovery_report:
  files_read:          []
  dependencies_found:  []   # interface/class → file where found
  integration_points:  []   # factories, registries, tools that must be updated
  reference_features:  []   # existing features used as reference
  missing_source:      []   # BLOCK if non-empty — request files before proceeding
```

Save the report to the feature's working folder. Register it with the feature-state tool:

```
python3 Tools/feature-state/feature_state.py phase-report <feature_dir> \
  --payload '{"phase": "2_discovery", "path": "[FeatureName]_Discovery.md"}' \
  --revision <N>
```

**Do not proceed to approval if `missing_source` is non-empty. Request the missing files first.**

Once the report is registered, present it to the engineer for approval. A resumed session
reads it instead of re-running discovery.
