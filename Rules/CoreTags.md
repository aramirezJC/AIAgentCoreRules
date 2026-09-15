## apply: always

# Core Rule Tags

Short labels defined here once and referenced across all rule and process files.
Any file that uses a tag inherits the full definition below — no re-statement needed.

---

## Tag Definitions

| Tag | Rule |
|---|---|
| **[CTX]** | All required dependencies must be confirmed in context before generating. If anything is missing: STOP — do not generate, request the file. |
| **[SIG]** | No signature guessing. Every property, method, and field must be physically located in provided source text before use. |
| **[PRES]** | Preserve all existing comments, XML summaries, regions, and TODOs unchanged. |
| **[SURG]** | Surgical edits only — change only the required lines; surrounding code must be character-perfect. |
| **[SO]** | Unity ScriptableObjects: `CreateInstance<T>()` only, never `new T()`. |
| **[RES]** | Every resource acquisition (subscription, load, timer, guard) requires a matching release in the same logical scope. |
| **[SYM]** | Subscribe and unsubscribe must be in the same method pair — `SetUp/TearDown`, `Enable/Disable`, `SetupEvent/CleanupEvent`. |
| **[DI]** | No `ServiceLocator.Instance` — use constructor injection or `LazyService<T>`. |
| **[IFACE]** | Never cast to a concrete type inside a high-level system — widen the interface instead. |
| **[ASYNC]** | No `async void` except event handlers and synchronous overrides bridging into async. Bridging overrides must have a full `try/catch`. |
| **[SRP]** | One class or method = one reason to change. If the name needs "And", split it. |
| **[GEN]** | Auto-generated files must not be edited manually — re-run the generator tool instead. |
| **[EXPLICIT]** | No `var` — all types must be declared explicitly everywhere. |
| **[ALLMAN]** | Allman braces — `{` always on its own new line. |
| **[ACCESS]** | All access modifiers must be explicit on every member — no implicit defaults. |
| **[LOG]** | All logging via the project Logger wrapper only. Never `UnityEngine.Debug.Log`, `Debug.LogWarning`, or `Debug.LogError`. |
