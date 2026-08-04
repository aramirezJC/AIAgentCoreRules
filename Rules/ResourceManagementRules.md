## apply: on-demand — loaded by [[MetaRouter]]

# Resource Management Rules

> Load when: subscriptions, Addressables, timers, DI containers, locks, guards, or any IDisposable.

---

## Symmetry Principle

Every resource acquisition must have an equivalent release in the same logical scope. No exceptions without explicit justification.

```yaml
symmetry_pairs:
  event_subscription:   "AddListener / Subscribe  →  RemoveListener / Unsubscribe"
  addressables:         "LoadAssetAsync           →  Release / Destroy"
  timer:                "SetupTimer / Start        →  CleanupTimer / Stop"
  di_container:         "BindWithInstance          →  Dispose"
  disposable:           "new / CreateInstance      →  Dispose / DestroyImmediate"
  scoped_guard:         "Acquire / Lock            →  Release (via using)"
```

**Generation checklist — run before submitting code:**

```yaml
symmetry_checklist:
  - Every AddListener has a RemoveListener in the same class lifecycle (Setup/Teardown or equivalent).
  - Every Addressables load has a corresponding release on the same object.
  - Every IDisposable created without using is disposed in a finally block or Dispose method.
  - Every timer started in Setup is stopped in Cleanup/Teardown.
  - Every DI container created in test SetUp is disposed in TearDown.
```

---

## Scoped State — Prefer IDisposable over Boolean Flags

Boolean flags that guard a process are fragile: they do not survive exceptions and their reset point is implicit.

```csharp
// ❌ Bool flag — does not survive exceptions, reset is invisible
_isProcessing = true;
await DoWork();        // throws — _isProcessing is never reset
_isProcessing = false;

// ❌ Bool flag with manual try/finally — works but hides intent
_isProcessing = true;
try
{
    await DoWork();
}
finally
{
    _isProcessing = false;
}
```

Prefer a scoped guard that implements `IDisposable`. The `using` block makes the scope boundary explicit and guarantees release under any exit path — normal, exception, or cancellation.

```csharp
// ✅ IDisposable guard — scope is explicit, release is guaranteed
private IDisposable BeginProcessing()
{
    _isProcessing = true;
    return new CallbackDisposable(() => _isProcessing = false);
}

// At call site:
using (BeginProcessing())
{
    await DoWork();
} // _isProcessing = false guaranteed here
```

### When to apply this pattern

```yaml
use_disposable_guard_when:
  - A boolean flag is set before an operation and must be reset after.
  - The operation is async and could throw or be cancelled.
  - The guarded region spans multiple await points.
  - Two or more code paths must leave the same flag in the same state.

boolean_flag_acceptable_when:
  - The flag is a permanent state transition (not a scoped guard).
  - The flag is set and never needs to be unset by the same owner.
```

---

## Event Subscriptions

Subscribe and unsubscribe must be in the same logical scope — the same method pair (Setup/Cleanup, Enable/Disable, SetupEvent/CleanupEvent) or the same `using` block.

```csharp
// ✅ Symmetric — same method pair
public override async Task SetupEvent()
{
    _messageManager.Value.AddListener(this);
}

public override void CleanupEvent()
{
    _messageManager.Value.RemoveListener(this);
    base.CleanupEvent();
}

// ❌ Asymmetric — subscribed in constructor, never unsubscribed
public MyClass()
{
    _eventSource.SomeEvent += OnSomeEvent;
}
```

Do not use `Subscribe<T>(delegate)` patterns — they produce anonymous subscriptions with no unsubscribe handle.

---

## Addressables

Every asset loaded via Addressables must have a corresponding release on the same owning object.

```csharp
// ✅
PrizeView prefab = await config.LoadPrizeViewPrefab();
// ... use prefab ...
config.ReleasePrizeViewPrefab(); // same owner, paired with the load
```

Load and release must be traceable to the same owner. If ownership transfers, document it explicitly.
