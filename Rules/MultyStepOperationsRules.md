## apply: on-demand — loaded by [[MetaRouter]]

# Multi-Step Operation Rules

> Covers operations that span multiple frames or iterate through a sequence of steps.
> Companion to [[CodingStandards]] and [[ArchitecturalPrinciples]].
> Load when: async flows, action queues, multi-frame sequences, callback-driven operations.

---

## The Core Rule

Model multi-step sequences as `async/await` flows with an explicit loop — not as callback-driven pumps.

A callback pump hides control flow across multiple methods and event subscriptions. An `async` loop makes the sequence visible as a straight read-top-to-bottom.

---

## What to Avoid — Callback Pump Pattern

```csharp
// ❌ Flow is hidden across Run → RunNext → OnComplete → RunNext (recursive)
public void Run()
{
    _isRunning = true;
    RunNext();
}

private void RunNext()
{
    if (_actions.Count == 0)
    {
        _taskSource.TrySetResult(true);
        return;
    }
    _currentAction = _actions[0];
    _currentAction.CompletedEvent += OnComplete;
    _currentAction.Execute();
}

private void OnComplete()
{
    _currentAction.CompletedEvent -= OnComplete;
    _actions.RemoveAt(0);
    RunNext(); // recursive hidden loop
}
```

Problems:
- Sequence is reconstructed mentally by tracing events and recursion.
- Error handling must be scattered across every callback.
- Subscribe/unsubscribe symmetry is separated by method boundaries.
- Boolean flags mirror state that the `Task` itself already carries.

---

## What to Favor — Async Loop Pattern

```csharp
// ✅ Sequence is a visible for-loop; each step is a named awaitable
private async Task RunQueueInternal()
{
    int actionIndex = 0;
    try
    {
        SortActions();
        for (; actionIndex < _actions.Count; ++actionIndex)
        {
            await ProcessActionAtIndex(actionIndex);
        }
    }
    catch (Exception e)
    {
        _logger.Exception(e);
    }
    finally
    {
        _actions.Clear();
        _queueRunner = null;
    }
}
```

Benefits:
- Reading top-to-bottom reveals the full sequence.
- One `try/catch/finally` covers the entire flow.
- Cleanup is guaranteed in `finally` regardless of failure.
- Loop index preserves context for diagnostics.

---

## Bridging Callback-Based APIs

When a step's completion is signalled by a callback (e.g. an `IAction.CompletedEvent`), wrap it in an awaitable adapter rather than restructuring the outer flow around the callback.

```csharp
// ✅ Subscribe, await, unsubscribe — all in the same method scope
private async Task ExecuteAction(ILevelCompleteAction action)
{
    ObservableCallback callback = new ObservableCallback();
    action.CompletedEvent += callback.Execute;
    CallbackListenerAsyncOperation callbackOperation = new CallbackListenerAsyncOperation(callback);

    action.Execute();

    await callbackOperation;
    action.CompletedEvent -= callback.Execute;
}
```

Rules:
- Subscribe and unsubscribe must be in the **same method**.
- The adapter converts the callback signal into an awaitable without leaking event state to the caller.
- The outer loop sees a clean `await` — it has no knowledge of the callback mechanism.

---

## State Tracking

Use the `Task` reference itself as the running-state signal. Do not shadow it with a boolean flag.

```csharp
// ✅ Null = not running; not-null = running
private Task _queueRunner = null;
public bool isRunning => _queueRunner != null;

// ❌ Boolean duplicates what the task already encodes
private bool _isRunning;
```

Guard against double-run at the entry point using the same reference:

```csharp
public async Task RunAsync()
{
    if (_queueRunner != null)
    {
        await _queueRunner; // join the in-flight run, don't start a second
        return;
    }
    _queueRunner = RunQueueInternal();
    await _queueRunner;
}
```

---

## Guard Against Mutation During Execution

Validate additions at `Append` time, not inside the loop. The queue must be fully built before `Run` is called.

```csharp
public void Append(ILevelCompleteAction action)
{
    if (isRunning)
    {
        _logger.Error("Cannot add actions to a running queue.");
        return;
    }
    _actions.Add(action);
}
```

---

## Quick-Reference

```yaml
checklist:
  - Sequence is an explicit for/foreach loop in a single async Task — not recursive callbacks.
  - One try/catch/finally wraps the entire loop — not individual callbacks.
  - Cleanup (Clear, null-out) is in finally — not scattered across completion handlers.
  - Callback steps wrapped in an awaitable adapter; subscribe and unsubscribe in the same method.
  - Running state derives from the Task reference — not a separate boolean flag.
  - RunAsync guards against double-run by awaiting the existing task if one is in flight.
  - Append rejects mutations while running — never mutate the collection mid-loop.
```
