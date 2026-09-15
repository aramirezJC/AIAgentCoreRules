## apply: on-demand — loaded by [[MetaRouter]]

# Investigation Mode

The mode for **understanding a problem before deciding to solve it**. Distinct from
[[CreateFeature/index]], which is for building something already decided.

Load this when the request is to explore, assess feasibility, compare approaches, or produce a
design — and **no gate, TDD, or task list is wanted yet**.

Tag definitions: [[CoreTags]]

---

## Which mode am I in?

```yaml
investigation_mode:
  triggers:
    - "how feasible is X"
    - "how does X compare to Y"
    - "what are the interactions / where does X happen"
    - "lets consider a hypothetical refactor"
    - "compile a list of X"
    - "I want to understand X before deciding"
  output:   "a document, a comparison, or a recommendation — NOT code"
  gates:    none
  metrics:  not initialized — session_metrics.md belongs to feature work

feature_development_mode:
  triggers:
    - "implement X"
    - "build X"
    - "add feature X"
    - "/feature <Name>"
  output:   "working code, tests, integration"
  gates:    "all 8 CreateFeature gates, engineer-confirmed"
  process:  [../Processes/CreateFeature/index]
```

**Do not silently escalate.** An investigation that produces a design document is complete. Offer
`/feature <Name>` as the next step; do not start Phase 1 unsolicited. Equally, do not answer a
feature request with a document.

If the request is ambiguous, say which mode you are assuming in one line and continue. State it —
do not block on it.

---

## Rules

### I. Delegate breadth, keep depth

```yaml
delegate_to_subagents:
  - "Any question of the form 'where / which files / who implements' — use /discover or an Explore agent."
  - "Surveying an unfamiliar system, directory, or feature area — always delegate."
  - "Multiple independent areas — one agent per area, launched in a single message."
keep_in_main_context:
  - "Reading the specific method bodies a conclusion depends on."
  - "The reasoning, comparison, and recommendation itself."
  - "Targeted single-fact verification (one grep, one codeindex query)."
```

Investigation is the mode that most benefits from delegation, because breadth dominates. A survey
that fills the main context with file listings has spent the budget that the analysis needed.

### II. Verify load-bearing claims — cheaply

```yaml
verification:
  rule:   "Any claim a design decision rests on must be grounded in source read this session."
  method: "One targeted grep or codeindex query. Never a full-file read to check one fact."
  when:   "Before the claim enters a document or a recommendation — not after."
```

A single grep that reverses a conclusion is the highest-value token spend available. Budget for it
generously.

Conversely: **a zero result is a claim too.** Before reporting "nothing uses this", confirm the
query could have found it if it existed. See the event-member exception in `/uses`.

### III. The finding may be the deliverable

```yaml
before_building_tooling:
  - "Ask: has the exploration already answered the question?"
  - "If yes, write it down and stop. Do not build a tool to rediscover it."
```

Exploration undertaken to scope a tool often *is* the tool's output. Check before designing the
thing that would reproduce work already done.

### IV. Correct prior claims plainly

```yaml
corrections:
  - "When verification reverses something you asserted earlier, lead with the correction."
  - "State what changes downstream as a result."
  - "No hedging, no re-litigating — one statement, then continue."
```

Investigation is iterative by nature; reversals are expected and are not failures. An uncorrected
claim propagates into the design document and then into code.

### V. Cite, don't assert

Every factual claim in an investigation output carries `file:line`. A design document that asserts
from memory is worse than no document, because the next engineer trusts it.

Record **negative findings** too — "checked and not interactive", "already persisted elsewhere" —
with the evidence. They prevent the next session re-investigating.

### VI. Output is a document

```yaml
investigation_output:
  location: "Assets/GitIgnoreAssets/DesignDocuments/<Topic>.md"
  contains:
    - problem statement and the decision reached
    - verified findings, each cited, traps flagged prominently
    - rejected alternatives WITH the reason  # prevents re-litigation
    - work breakdown, roughly sized
    - open questions, each with the command that answers it
    - how to start a thread from this document
```

Write it so a different engineer — or a fresh session — can act on it without re-deriving anything.

---

## Token discipline

Lessons that cost real budget to learn. Ordered by impact.

```yaml
pitfalls:
  attachments:
    problem: "A re-attached file costs its full length every turn."
    rule:    "Name the file and read the 30 lines that matter. Attach only when the whole body is needed."
  premature_planning:
    problem: "Planning before the deliverable shape is confirmed; plan then discarded."
    rule:    "See [[StopAndVerify]] — the tool-request gate. One question before exploring."
  double_paying_on_tools:
    problem: "A tool whose limits produce a false zero forces a second verification round."
    rule:    "Know each tool's blind spot. Pick the query that can actually find the answer."
  main_context_survey:
    problem: "Broad exploration done inline instead of delegated."
    rule:    "Rule I. Breadth goes to subagents."
  shape_queries_as_file_reads:
    problem: "Reading a whole file to learn a type's members."
    rule:    "codeindex.py for shape. Read for bodies."
```

---

## Closing an investigation

```yaml
investigation_handoff:
  question_asked:      ""
  answer:              ""      # the actual conclusion, one or two sentences
  decision_changed_by: []      # findings that reversed an assumption — call these out
  document:            ""      # path to the written output
  open_questions:      []      # each with the command that resolves it
  recommended_next:    ""      # usually "/feature <Name>" or "resolve open question N first"
```

Then stop. Escalating to feature work is the engineer's call.
