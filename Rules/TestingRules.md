## apply: on-demand — loaded by [[MetaRouter]]

# Testing Rules

> Load when: writing or modifying any test code.
> Rules are project-agnostic. Verify that any project-specific utility exists in the codebase before using it.

---

## Container Setup

```yaml
di_container:
  create:   "Services.CreateNewService(null)"  # creates a proper container
  avoid:    "Services.Instance = null"         # does NOT create a proper container
  teardown: "Services.Instance.Dispose()"
```

Always bind a real message bus implementation — substitutes break any code path that dispatches messages.

---

## Test Doubles

```yaml
use_real_or_project_dummy_when:
  - Behavior under realistic conditions must be verified.
  - The code path dispatches messages.
  - The project provides a Dummy for the interface.

use_substitute_when:
  - Specific return values must be configured.
  - Calls must be verified.
  - No project Dummy exists for the interface.

never_substitute:
  - IMessageBus, IMessageDispatcher, IBlackboard — always bind a real MessageManager.
```

---

## Assertions

```yaml
assertion_priority:
  first:    Project aggregator if available — verify it exists before importing.
  fallback: Standard framework assertions (NUnit Assert, etc.)

aggregator_rules:
  - Aggregate all failures — do not short-circuit on first failure.
  - Always provide a descriptive failure message — the aggregator reports only the message.
  - Reference types: reference equality. Structs: value equality.
```

---

## State Reset

```yaml
teardown_requirements:
  - Every SetUp must have a matching TearDown.
  - Recreate or reset all mocks and test doubles per test — never share state between tests.
  - ScriptableObject instances: destroy via Object.DestroyImmediate().
  - "[RES] DI containers: dispose in TearDown."
```

---

## Async

```yaml
async_rules:
  - Prefer Task-returning test methods over async void.
  - Never use DateTime.Now — inject and mock ITimeService or equivalent.
```

---

## Naming

```yaml
test_method_pattern: "{TestedBehavior}_{Condition}_{ExpectedResult}"
examples:
  - CanStartEvent_WhenAlreadyInProgress_ReturnsFalse
  - ProcessPrize_WithMemoryFlag_CallsPrizeProcess
```
