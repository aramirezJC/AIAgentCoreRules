# Session Analysis

Meta-analysis across every session tracked by `Tools/session-lifecycle`, written as one
self-contained HTML page (inline SVG, no external scripts). Open it in a browser; print it to PDF
from there if you need one.

```bash
cd <project root>
python3 GitIgnoredExternals/AIAgentCoreRules/Tools/session-analysis/session_meta_report.py
# -> GitIgnoreReports/SessionAnalysis.html
```

Options: `--sessions <dir>` (default `GitIgnoreReports/Sessions`), `--repo <dir>` repeatable
(default every git repo under `GitIgnoredExternals/`), `--out <file>`.

## What it shows

1. **Token expenditure.** A histogram of tokens per turn, with a normal curve fitted to
   log10(tokens) and ±1σ/±2σ bands. Toggle between *fresh* tokens (uncached input + output) and
   *total* tokens (including cache reads). A dot plot shows the total for each session.
2. **Worst performers.** Rankings follow the fresh/total toggle:
   - the 10 heaviest turns, with category, tool calls and tokens per call;
   - sessions, with tokens per turn and how much was flagged avoidable;
   - turn categories, lanes and work types, with total, mean per turn, heaviest turn and share.
     Sessions recorded before work types existed get their lane's work type.

   Each turn carries the verdict its retro's Cost section gave it: *necessary*, *partly
   avoidable*, *avoidable*, or *no verdict* when the retro did not discuss that turn.
3. **What saved us.** An estimate of the fresh tokens (and turns) saved by each element of the
   framework: Runnable tools, knowledge docs (Systems, SystemPatterns, SystemIndex, project rules),
   skills, delegation, routing and rule files. Usage comes from the session transcripts: tool runs
   and their results, skill and command invocations, subagent spend, and files loaded. The model
   has two parts, both printed in the report:
   - **Measured baselines:** median fresh tokens per tool call, per turn and per subagent survey.
   - **Stated assumptions**, overridable with `--assumptions <json>`:

   | Element | Credit |
   |---|---|
   | `codeindex.py` | (4 − 1) tool calls per query |
   | `usages.py` | (6 − 1) tool calls per run |
   | `typecheck.py` | 1 turn per run that caught compile errors (passing runs are verification only) |
   | `/audit` | 0.5 turn per run |
   | Knowledge doc | 1 survey when a retro credits it; 0.5 when loaded with no evidence or with both praise and gaps; 0 when a retro says it fell short, or when the read was maintenance (a session editing mostly metadata, or the same doc) |
   | Routing and rule files, delegation | Counted, not token-estimated |
4. **Where issues concentrate.** A heat map of area × session, counting mentions in each retro's
   Proposed changes, Router check misses and Discovery gaps. A second heat map shows correction
   root cause × lane.
5. **Solutions.** Every proposed change, with a status and the evidence for it.
6. **What else could be improved.** Recurring open areas, repeated router misses, tracking gaps
   (no lane, no `/end-session`, no token data, corrections not logged live) and token outliers.

## How proposal status is decided

| Status | Evidence |
|---|---|
| applied / skipped | The retro's `## Applied` section (`- #N applied: …` / `- #N skipped …`) |
| likely applied | A commit touched the proposed file after the session ended, or the file has uncommitted changes made after it |
| open | Neither of the above, or the file could not be found in the scanned repositories |

*Likely applied* is a heuristic. A later commit may have touched the file for another reason,
so check the evidence column before relying on it.

## Parsing limits

- Areas are grouped by file name, so `Runnable/typecheck.py` and `typecheck.py` count as one.
  Discovery gaps that name no file are grouped under "(gap with no file named)".
- Root causes are counted by finding the five known tags in the Corrections section. Prose
  corrections without a tag are not counted.
- Router misses are Router check rows whose *Loaded?* cell starts with "no".
- Turn verdicts are keyword-matched from the Cost section's `T<n>` lines. "Necessary" alongside
  "but", "could have", "wasted" or "slowed" counts as *partly avoidable*; "avoidable" or
  "unnecessary" counts as *avoidable*. Retros only discuss their three heaviest turns by
  **total** tokens, so turns that are heavy on **fresh** tokens often have no verdict.
- Per-turn tokens come from the "Highest-Cost Turns" table in `tokens/token-usage-*.md`. Sessions
  without `tokens/` add no turns.
