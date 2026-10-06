# Small Task Process

For a bounded change: a tool, utility, debug command or behaviour tweak modelled on existing
code. Smaller than a feature — no GDD, TDD or task list, and a single proposal checkpoint.

## When it fits

- Touches one system and at most about 5 files.
- No new config root, player-data schema or server contract.
- An existing example can be followed ("like xyz, but does abc").

If any of these stops being true mid-task, the agent stops, says so in one line and offers
`/feature <Name>`. It does not quietly turn a small task into a feature.

## Steps

| # | Step | What happens |
|---|---|---|
| 1 | **Scope** | For a tool, script or report: ask whether it is one-off or reusable, and where it runs (Editor, runtime, CLI), then wait. Restate the deliverable in one line. |
| 2 | **Context** | Read the Systems entry for the owning system and any matching pattern. Inspect the model example with the host's code index (`codeindex.py`) and read only the bodies being copied. If the change sends or listens for a message, read every listener's handler first. |
| 3 | **Rules** | Coding Standards always; Architectural Principles for new classes or interfaces; Resource Management for subscriptions, timers and loads; Multi-Step Operations for async sequences; Testing Rules if tests are requested. |
| 4 | **Propose** | List the files to create or modify, one line each. The agent waits for approval only when more than 2 files change or a public contract changes. |
| 5 | **Implement** | Stop and Verify checks, then write the code. |
| 5b | **Audit** | Run `/audit` on every changed file, including debug tooling and tests. This is a checkpoint: verification doesn't start until it has run, and self-review is not a substitute. The retrospective flags a skipped audit. |
| 6 | **Verify** | Run the host's compile check (`typecheck.py`). Tell the engineer how to try it (menu path, debug command, steps). When no C# changed (a Python tool, a skill, Markdown), run the changed tool against copies of real data instead and report what was exercised. |
| 7 | **Close** | Offer `/end-session`. |

## What the retrospective expects to see loaded

- The Systems entry for the owning system (if one exists)
- Coding Standards, plus each rule file from step 3 the change matched
- Tools: `codeindex.py`, `typecheck.py`, `/audit` — for C# changes only
- When no C# changed: a run of the changed tool against copies of real data instead. Coding
  Standards and the C# tools are not expected, so the retrospective does not flag them as misses.

**Source files:** [[SmallTask]]

---

← [[04_BugFix|Bug Fix Process]] · [[00_Overview|Overview]] · [[06_Investigation|Investigation Mode]] →
