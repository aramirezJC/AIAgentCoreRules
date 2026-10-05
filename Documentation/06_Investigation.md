# Investigation Mode

The mode for **understanding a problem before deciding to solve it**: feasibility, comparing
approaches, mapping where something happens, planning a hypothetical refactor, compiling a list.
The output is a document, comparison or recommendation — **not code** — and there are no gates.

An investigation that produces a design document is complete. The agent offers
`/feature <Name>` as a next step but never starts building unasked. Equally, a feature request
is never answered with only a document.

## Rules

0. **Load what the project already knows first.** Before the first search, the agent reads the
   host SystemIndex entry for every system the question touches, and for a system that comes up
   later, before reading its code. A missing entry is noted as a finding. The retrospective
   counts a late load as a miss.
1. **Delegate breadth, keep depth.** Surveys and "where / which files / who implements"
   questions go to subagents. The main context keeps the method bodies a conclusion depends on,
   and the reasoning.
2. **Verify load-bearing claims cheaply.** Any claim a decision rests on must be grounded in
   source read this session — checked with one grep or index query, not a full-file read, and
   before it enters the document. A zero result is a claim too: the agent confirms the query
   could have found a match if one existed.
3. **The finding may be the deliverable.** If exploration has already answered the question,
   write it down and stop, rather than building a tool to rediscover it.
4. **Correct prior claims plainly.** When verification reverses an earlier statement, the agent
   leads with the correction and says what changes downstream.
5. **Cite, don't assert.** Every factual claim carries `file:line`. Negative findings ("checked
   and not used", "already persisted elsewhere") are recorded with their evidence too.
6. **Output is a document**, with one exception. A safety or implications check of a single
   commit, or any question whose full cited answer fits in about one screen, is answered in chat
   (verdict first, every claim cited), ending with a one-line offer to write the document. The
   retrospective does not count that as a miss. Feasibility studies, comparisons, refactor plans
   and anything heading to `/feature` always get the document.

## The output document

Saved in the host project at `Assets/GitIgnoreAssets/DesignDocuments/<Topic>.md` (the path set in
`InvestigationMode.md`), containing:

- the problem statement and the decision reached,
- verified findings, each cited, with traps flagged prominently,
- rejected alternatives **with the reason** (prevents re-litigating them later),
- a roughly sized work breakdown,
- open questions, each with the command that would answer it,
- how to start a work thread from the document.

It should be usable by a different engineer, or a fresh agent session, without re-deriving
anything.

## Closing summary

```yaml
investigation_handoff:
  question_asked:      ""
  answer:              ""   # the conclusion, one or two sentences
  decision_changed_by: []   # findings that reversed an assumption
  document:            ""   # path to the written output
  open_questions:      []   # each with the command that resolves it
  recommended_next:    ""   # usually "/feature <Name>" or "resolve open question N first"
```

Escalating to feature work is the engineer's call.

**Source files:** [[InvestigationMode]]

---

← [[05_SmallTask|Small Task Process]] · [[00_Overview|Overview]] · [[07_SessionTracking|Session Tracking and Retrospectives]] →
