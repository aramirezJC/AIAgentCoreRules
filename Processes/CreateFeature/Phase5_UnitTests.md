## apply: on-demand — loaded by [[CreateFeature/index]]

# Phase 5 — Unit Tests

Goal: Write tests in three categories, all directly traced to documents produced in earlier phases. Every test must correspond to a documented use case, edge case, or Config class — no speculative tests.

Requires: `[Feature]_UseCases.md` from Phase 1 and implemented classes from Phase 4.

Before writing tests: re-read `../../Rules/TestingRules.md` and the host project's testing setup
(TripleMatch: `Rules/TestingSetup.md` in the metadata repo).

```yaml
running_tests:
  compile:  "Run the host compile check (TripleMatch: typecheck.py) — the agent does this."
  execute:  "The engineer runs the tests in Unity (Window > General > Test Runner) and pastes failures. The agent does not claim a pass it has not seen."
```

---

## Test Categories

```yaml
test_categories:
  1_json_deserialization:
    purpose:  Validate Config classes deserialize correctly from their JSON representation
    source:   Every Config class produced in Phase 4
    catches:  Unsupported field types, JsonProperty typos, missing required fields, designer errors

  2_behavior_tests:
    purpose:  Validate each documented use case works correctly end-to-end
    source:   Use case rows from [Feature]_UseCases.md (non-edge cases)
    rule:     One test per row — no row left without a test

  3_boundary_tests:
    purpose:  Validate each edge case is handled correctly and does not crash or corrupt state
    source:   Edge case rows from [Feature]_UseCases.md
    rule:     One test per row — TBD solutions must be flagged before writing
```

---

## Container Setup

Before writing any test class, establish the DI container following `TestingRules.md`.

```yaml
test_setup:
  create:    "Services.CreateNewService(null)"
  bind_real: "MessageManager for IMessageBus, IMessageDispatcher, IBlackboard, IMessageManager"
  doubles:   Use project Dummy implementations before Substitute.For<T>()
  teardown:  "[RES] Dispose container in TearDown. Destroy ScriptableObject instances via Object.DestroyImmediate(). Reset all test doubles per test."
```

---

## Category 1 — JSON Deserialization Tests

One test class per Config class. Each test deserializes a sample JSON payload and asserts every `[JsonProperty]` field is populated.

```yaml
json_test_rules:
  - Construct a representative JSON string matching the Config's [JsonProperty] fields.
  - Deserialize using the project's standard parser.
  - Assert every [JsonProperty] field has the expected value — do not omit assertions.
  - Include a test with an unrecognized field present — must not throw.
  - Include a test with optional fields absent — required fields must still populate correctly.
```

Naming: `{ConfigClass}_Deserialization`

---

## Category 2 — Behavior Tests

Open `[Feature]_UseCases.md`. Work row by row through the use cases. Write one test per row.

```yaml
behavior_test_rules:
  - Naming pattern: {TestedBehavior}_{Condition}_{ExpectedResult}
  - Structure: Arrange → Act → Assert
  - One scenario per test — do not combine multiple use cases in one test.
  - Tests must not depend on execution order.
  - Use project assertion aggregator if available; fall back to standard assertions.
  - Every assertion must have a descriptive failure message.
```

Present each test class to the engineer after writing it. Do not move to the next class until acknowledged.

---

## Category 3 — Boundary Tests

Open `[Feature]_UseCases.md`. Work row by row through the edge cases. Write one test per row.

```yaml
boundary_test_rules:
  - Same naming and structure rules as Category 2.
  - For any edge case with a TBD solution: stop and flag it to the engineer before writing.
    Do not guess the expected behavior — undefined behavior cannot be tested.
  - Focus assertions on the guard: verify the system does NOT crash, corrupt state, or silently produce wrong output.
```

---

## Coverage Summary

Present this before Gate 5:

```yaml
coverage_summary:
  json_tests:              0   # one per Config class
  behavior_tests:          0   # must equal use case count in [Feature]_UseCases.md
  boundary_tests:          0   # must equal edge case count in [Feature]_UseCases.md
  tbd_cases_skipped:       []  # edge cases deferred — must be logged as follow-up tasks
  failing_tests:           []  # must be empty before gate clears
```

---

## Gate 5 — Tests Passing

Before the gate: run `/audit` on every test file written this phase and fix or report each
violation. Test code follows the same rules as production code.

All tests passing. `failing_tests` must be empty. Engineer confirms coverage is acceptable.
Any skipped TBD cases must be logged as follow-up tasks before the gate clears.
