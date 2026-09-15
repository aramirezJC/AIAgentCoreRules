## apply: on-demand — loaded by [[MetaRouter]]

# Coding Standards

> Companion to [[ArchitecturalPrinciples]]. Enforces naming, organization, and accessibility.
> Load when: writing or modifying any C# code, refactoring, or reviewing.

---

## 1. Naming

```yaml
naming:
  constant:           UPPER_SNAKE_CASE   # LOGGER_CHANNEL
  delegate:           PascalCase         # ScreenFactory
  event:              PascalCase         # PrizeRewardStarted
  private_field:      _camelCase         # _screenFactory
  protected_field:    _camelCase         # _messageManager
  public_property:    camelCase          # prize, stageConfigs
  protected_property: camelCase          # logger, rewardReasonForBonus
  method:             PascalCase         # TryProcessPrize, InitializeEvent
```

### Semantic naming

- **Booleans:** `is`/`has`/`can` prefix → `isSeen`, `HasPendingRewards`, `CanStartEvent`
- **Try-pattern:** return `bool`, `out` param if needed → `TryGetPrimaryCharacterPrize(out Character c)`
- **External event handlers:** `HandleOn{EventName}` → `HandleOnPrizeRewardStarted`
- **Internal callbacks:** `On{Thing}` → `OnStageChanged`
- **Dispatch helpers:** `Dispatch{Message}` or `Send{Message}` → `DispatchEventUpdateMessage`
- **Factory delegates:** suffix `Factory` → `ScreenFactory`
- **Sub-system objects:** suffix `Controller` → `MissionCenterStageController`

---

## 2. File Organization

```yaml
member_order:
  - Constants
  - Delegates
  - Events
  - Fields          # private first, then protected
  - Properties      # protected first, then public
  - Constructors
  - Methods         # public override → public → protected override → protected → private
```

---

## 3. Accessibility

### Fields — always hidden

- `private` by default; `private readonly` for injected dependencies.
- `protected` only when a subclass genuinely needs direct access. Never `public`.
- Unity Inspector fields: `[SerializeField] private Type _fieldName = defaultValue;`

```csharp
// ✅
private readonly Logger _logger = null;
[SerializeField] private int _maxLives = 5;

// ❌
public Logger logger;
public int maxLives;
```

### Properties — most restrictive setter that satisfies the requirement

```yaml
property_setters:
  constructor_only:  "public T foo { get; }"
  internal_only:     "public T foo { get; private set; }"
  subclass_only:     "public T foo { get; protected set; }"
  fully_mutable:     "public T foo { get; set; }  # justify explicitly"
```

```csharp
// ✅ Set once in constructor
public IPrize prize { get; }

// ✅ Internal mutation only
public bool isSeen
{
    get => eventUserData.isSeen;
    private set => eventUserData.isSeen = value;
}
```

### Methods

- Public overrides before new public methods. Private helpers at the bottom.
- Mark classes `sealed` unless subclassing is intentional.
- Mark overridable methods `virtual` explicitly.

---

## 4. Method Design

### Single responsibility [SRP]

One method = one verb = one reason to change. If a method name needs "And", split it.

### English-readable composition

Higher-level methods read like ordered prose. Concrete logic lives only at the leaves.

```csharp
// ✅ Leaf — touches raw data directly
private void ExecutePrizeMemoryFlow(PrizeFlowProcessAction action, string prizeId) { ... }

// ✅ Composer — sequences named sub-calls, touches nothing directly
private async Task ProcessPrize(PrizeFlowProcessAction action)
{
    PrizeRewardStarted?.Invoke(prize);
    ExecutePrizeMemoryFlow(action, prizeId);
    await ExecutePrizeVisualFlow(action, prizeId);
    ExecutePrizeCleanupFlow(action);
    PrizeRewardCompleted?.Invoke(prize);
}
```

→ For async multi-step sequences, see [[MultyStepOperationsRules]].

### Size heuristics (signals, not hard violations)

- Method > 10 lines → likely doing more than one thing.
- Class/file > 500 lines → likely holding more than one responsibility.

### Guard clauses — exit early, stay flat

Handle edge cases at the top via early returns. The double-run guard in `RunAsync` is a canonical example — see [[MultyStepOperationsRules]].

```csharp
// ✅
private void ExecutePrizeCleanupFlow(PrizeFlowProcessAction action)
{
    if (!HasFlag(action, PrizeFlowProcessAction.Cleanup) || prize.wasCleaned)
    {
        return;
    }

    prize.Cleanup();
    PrizeCleanedUp?.Invoke(prize);
}
```

### Mathematical integrity

Logic that modifies a numeric value must protect lower bounds and handle degenerate inputs:

```csharp
// ✅ Clamp to zero — never allow negative quantities
currentLives = Mathf.Max(0, currentLives - cost);

// ✅ Guard empty collections before operating on them
if (weights.Count == 0) { return defaultValue; }
float total = weights.Sum();
if (total <= 0f) { return defaultValue; }
```

### Async from synchronous overrides [ASYNC]

When an interface or base class override is synchronous but the implementation needs async work, use `async void` with a full try/catch — never the discard pattern (`_ = Task`):

```csharp
// ✅ async void with try/catch — exceptions are caught, intent is clear
public override void Enter()
{
    base.Enter();
    EnterAsync();
}

private async void EnterAsync()
{
    try
    {
        bool ready = await WaitForDependency();
        if (!ready) { PopState(); }
    }
    catch (Exception e)
    {
        _logger.Exception(e);
    }
}
```

```csharp
// ❌ discard — exceptions are silently swallowed
_ = EnterAsync();

// ❌ .Wait() — blocks the thread, risk of deadlock
EnterAsync().Wait();
```

`async void` is acceptable **only** in this bridging role — synchronous override calling into an async body. All other `async void` uses (event handlers aside) are forbidden.

### Prefer Try-pattern over direct get

When absence of a result is a normal path, use `bool Try…(out T result)`.

```csharp
// ✅
public bool TryGetPrimaryCharacterPrize(out Character character) { ... }
```

Use when: boundary crossing, collection access, config lookup, event retrieval.
Do not use when the operation must always succeed — a failing Try there hides a bug.

---

## 5. Auto-Generated Files [GEN]

Any file that is fully or partially produced by a tool (code generators, editor scripts, build steps) must carry a header comment **outside** the generated region. The header must answer three questions:

```csharp
// AUTO-GENERATED — do not edit manually.
//
// Regenerate: <tool name and exact path or menu step>
//             e.g. Window > PDT Tools > EventGeneratorTools → CompileEventPublishers
//
// Warning: editing this file manually will be overwritten on the next generation run
//          and may produce silent runtime errors or missing registrations.
```

```yaml
required:
  - "AUTO-GENERATED" marker — visible without reading past the first few lines
  - how_to_regenerate: exact tool name, menu path, or command
  - consequence_of_wrong_edit: what breaks if the process is bypassed
placement:    top of file, before any using directives or namespace declarations
scope:        any file touched by a code generator, scaffolder, or editor script
```

If the file has a designated hand-edited region (e.g. partial additions below a generated block), the boundary must be clearly marked with a comment that names the region and states which direction is generated vs. hand-edited.

---

## 6. Quick-Reference

> Rules covered by [[MetaRouter]] non-negotiables are omitted. Items below are domain-specific.

```yaml
checklist:
  organization:
    - "Constants → Delegates → Events → Fields → Properties → Constructors → Methods"
    - "Methods: public override → public → protected override → protected → private"
  properties:
    - Setter at the most restrictive level that satisfies the requirement
  naming:
    - "Booleans: is/has/can prefix"
    - "External event handlers: HandleOn{EventName}"
    - "Internal callbacks: On{Thing}"
  method_design:
    - "[SRP]"
    - Composer methods sequence named sub-calls only — never touch raw data
    - Leaf methods touch data/APIs — never sequence other composers
    - "Methods >10 lines or classes >500 lines: signal to re-examine, not a hard violation"
    - Edge cases handled via early returns at the top
    - "Prefer bool Try(out T) when absence of result is a normal path"
    - "Numeric modification: clamp lower bound (>= 0); guard zero-weight/empty collections"
    - "[ASYNC]"
  auto_generated_files:
    - Header comment at top of file: AUTO-GENERATED marker + how to regenerate + consequence of wrong edit
    - If file has a hand-edited region, mark the boundary explicitly
```
