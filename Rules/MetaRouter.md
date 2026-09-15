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

## First: Classify the Mode

Before the routing table, decide which mode the request is in. They have different outputs and
different rules, and picking wrong wastes the whole turn.

```yaml
mode_fork:
  investigating:
    looks_like: "how feasible / how does X compare / where does X happen / hypothetical refactor / compile a list"
    output:     "a document or recommendation — NOT code"
    load:       [Rules/InvestigationMode]
  building:
    looks_like: "implement / build / add feature X / /feature <Name>"
    output:     "code, tests, integration — with gates"
    load:       [../Processes/CreateFeature/index]
```

Never silently escalate investigation into feature work, or answer a build request with a document.
If genuinely ambiguous, state the assumed mode in one line and continue — do not block.

---

## Absolute Non-Negotiables

```yaml
non_negotiables:
  - "[EXPLICIT] No var — explicit types everywhere."
  - "[ALLMAN]   Allman braces — { always on a new line."
  - "[FIELD]    No public fields — ever. Wrap in a property."
  - "[ACCESS]   All access modifiers explicit on every member."
  - "[FIELD]    private readonly for every injected dependency."
  - "[DI]       No ServiceLocator.Instance — use constructor injection or LazyService<T>."
  - "[IFACE]    Never cast to a concrete type inside a high-level system."
  - "[RES]      Every resource acquisition has a matching release in the same scope (subscriptions, loads, timers, guards)."
  - "[ASYNC]    No async void except: event handlers, and synchronous overrides bridging into async (must have try/catch)."
  - "[LOG]      All logging via the project Logger wrapper only — never native platform debug logging."
  - "[DELEGATE] Breadth goes to subagents. Any 'where / which files / who implements' question is delegated, not run inline."
  - "[SHAPE]    A tool/script/report request hits the [[StopAndVerify]] Scope Gate before any exploration."
```

### [DELEGATE] — when to spawn, when not to

```yaml
delegate_aggressively:
  - "Surveying a system, directory, or feature area           → /discover <area>"
  - "'Where is X / which files / who implements Y'            → Explore agent, or /discover"
  - "Several independent areas                                → one agent per area, ONE message"
  - "A compliance or review sweep over many files             → fan out, then synthesise"
keep_inline:
  - "Reading the specific method bodies a conclusion rests on."
  - "A single targeted fact check — one grep or one codeindex query is cheaper than an agent."
  - "The reasoning, comparison, and recommendation itself."
```

The failure mode is not over-delegating; it is filling the main context with file listings and
leaving no budget for the analysis they were gathered for.

---

## Routing Table

When a task matches a process, load the process and follow it. Processes are wizard workflows — they reference the rules internally at the right steps.

```yaml
routing:
  # Processes — load and follow step by step
  create_new_feature:             [../Processes/CreateFeature/index]

  # Modes — decide this first, see "Classify the Mode" above
  investigate_or_preplan:         [Rules/InvestigationMode]
  feasibility_or_comparison:      [Rules/InvestigationMode]
  produce_design_document:        [Rules/InvestigationMode]

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
Read: ./InvestigationMode.md
Read: ./CodingStandards.md
Read: ./ArchitecturalPrinciples.md
Read: ./MultyStepOperationsRules.md
Read: ./TestingRules.md
Read: ./ResourceManagementRules.md
```

Do not generate code until the relevant files are read.
