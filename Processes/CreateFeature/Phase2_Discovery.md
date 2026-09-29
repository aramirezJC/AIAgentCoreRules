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

Present to the engineer:

```yaml
discovery_report:
  files_read:          []
  dependencies_found:  []   # interface/class → file where found
  integration_points:  []   # factories, registries, tools that must be updated
  reference_features:  []   # existing features used as reference
  missing_source:      []   # BLOCK if non-empty — request files before proceeding
```

**Do not proceed to Phase 3 if `missing_source` is non-empty. Request the missing files first.**

Once approved, save the report as `[FeatureName]_Discovery.md` in the feature's working folder
and add it to `artifacts` in the progress file. A resumed session reads it instead of
re-running discovery.
