## apply: always

# Agent Rule Router

This file and [[StopAndVerify]] are the only files loaded unconditionally. Classify the task, then use your Read tool to load the relevant files **before generating any code**.

```yaml
directory_layout:
  ./Rules/      # Standards and principles — what code must look like
  ./Processes/  # Step-by-step wizard workflows — how to carry out specific tasks
```

All paths below are relative to the directory containing this file.

---

## Absolute Non-Negotiables

```yaml
non_negotiables:
  - "No var — explicit types everywhere."
  - "Allman braces — { always on a new line."
  - "No public fields — ever. Wrap in a property."
  - "All access modifiers explicit on every member."
  - "private readonly for every injected dependency."
  - "No ServiceLocator.Instance — use constructor injection or LazyService<T>."
  - "Never cast to a concrete type inside a high-level system."
  - "Every resource acquisition has a matching release in the same scope (subscriptions, loads, timers, guards)."
  - "No async void except: event handlers, and synchronous overrides bridging into async (must have try/catch)."
  - "All logging via the project Logger wrapper only — never native platform debug logging."
```

---

## Routing Table

When a task matches a process, load the process and follow it. Processes are wizard workflows — they reference the rules internally at the right steps.

```yaml
routing:
  # Processes — load and follow step by step
  create_new_feature:             [../Processes/CreateFeature/index]

  # Rules — load and apply when writing or reviewing code
  write_or_modify_csharp:         [Rules/CodingStandards]
  design_classes_or_interfaces:   [Rules/ArchitecturalPrinciples]
  async_flows_queues_sequences:   [Rules/MultyStepOperationsRules]
  write_or_modify_tests:          [Rules/TestingRules]
  resource_management:            [Rules/ResourceManagementRules]
  refactor_or_review:             [Rules/CodingStandards, Rules/ArchitecturalPrinciples]
  new_feature_multi_system:       [Rules/CodingStandards, Rules/ArchitecturalPrinciples, Rules/MultyStepOperationsRules]
```

---

## How to Load

```
# Processes
Read: ../Processes/CreateFeature/index.md

# Rules
Read: ./CodingStandards.md
Read: ./ArchitecturalPrinciples.md
Read: ./MultyStepOperationsRules.md
Read: ./TestingRules.md
Read: ./ResourceManagementRules.md
```

Do not generate code until the relevant files are read.
