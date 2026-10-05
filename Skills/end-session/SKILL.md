---
name: end-session
description: Close the session - compile token metrics and the router trace, write a retrospective scaled to the session's lane, open both files for the engineer, and propose (not apply) rule and index improvements. Use when the engineer runs /end-session or asks to wrap up, close out, or review the session.
---

# End Session

Lifecycle script (use the path from the Session tracking block if present):
`GitIgnoredExternals/AIAgentCoreRules/Tools/session-lifecycle/session_lifecycle.py`

All rule paths below are relative to the AIAgentCoreRules root (the parent of the `Rules/`
folder that holds MetaRouter.md).

---

## Step 1 — Compile

```yaml
steps:
  - "If the lane is not set: classify it now and run: python3 <script> set --lane <lane> --title \"<title>\""
  - "Feature lane, feature not complete: if work stopped partway through a phase, run /checkpoint first; if it stopped at a gate, confirm the gate block is in <FeatureName>_Progress.md."
  - "Run: python3 <script> compile --final     # prints the metrics.md path"
  - "Read metrics.md. It has tokens, inaccuracies, iterations, the router trace and Runnable tool counts."
```

The router trace comes from the session transcript, not memory. Treat it as the record of
what was actually loaded. Rows marked `Bash` are inferred from shell commands (a grep counts);
rows marked `Read` are certain.

## Step 2 — Retrospective, scaled by lane

```yaml
depth:
  feature:        "Load ../Processes/CreateFeature/Phase8_Retrospective.md and follow it. Its report is retro.md. Its benchmarks come from metrics.md — do not ask for /cost."
  small_task:     short
  bug_fix:        short
  investigation:  short
  other:          short
```

If metrics.md lists **Lane changes**, the session ran in more than one lane: run the Router check
once per lane segment, splitting the router trace at each change's timestamp. The retrospective
depth follows the lane with the heaviest work.

Short retrospective — write `retro.md` in the session folder with exactly these sections:

```markdown
# Retrospective — <title>

## Outcome
<1–3 lines: what was delivered and how it was verified (typecheck, tests, engineer check)>

## Router check
| Expected for this lane | Loaded? | Note |
<expected loads come from the lane's process file (Processes/SmallTask.md, Processes/BugFix.md,
 Rules/InvestigationMode.md) plus the routing-table rows the work matched. Flag both misses and
 loads that were not needed.>

## Corrections
<one row per correction: every logged inaccuracy, plus every correction visible in the conversation
 that was not logged (the engineer redirected you or rejected an approach, or you retracted a claim).
 Each row: what went wrong → root cause, one of:
 missing-rule | missing-index-entry | rule-ignored | signature-guessed | scope-misread
 and how it was recorded: engineer | agent | retro (see "Back-fill" below).>

## Discovery gaps
<anything looked up mid-task that SystemIndex / Systems/ / SystemPatterns/ should have supplied>

## Proposed changes
| # | File | Change | Why |
<concrete, minimal edits. Not applied.>

## Cost
<total tokens, turns, subagents from metrics.md; the 3 heaviest turns and whether each was necessary.
 Rank turns by FRESH tokens (Uncached In + Output in the "Highest-Cost Turns" table of tokens/*.md),
 not Total Tokens, which is mostly cache reads. If the heaviest turn by Total is not already in the
 list, add it as a 4th. One numbered line per turn, in this shape, so the meta-analysis can read it:
   1. **T<n>, <fresh> fresh / <total> total, <k> tool calls:** <what the turn did>. **Necessary.** |
      **Partly necessary** — <what was avoidable>. | **Avoidable** — <why>.
 If tokens/ is missing or metrics.md marks tokens unavailable, label the list "estimated" and say why.>
```

Keep it evidence-based: every claim points at a trace row, a logged note, or `file:line`.
Write "none" for an empty section rather than padding it.

**Back-fill.** For each Corrections row that metrics.md does not already list, record it so
the metrics match the retro:
`python3 <script> note --kind inaccuracy --source retro "<what went wrong> → <root cause>"`.
Never back-fill a row that is already logged. The `retro` source keeps back-filled entries
apart from ones logged live, so reports can still tell whether corrections are logged during
the session.

## Step 3 — Open and hand off

```yaml
steps:
  - "Run: python3 <script> open        # opens metrics.md and retro.md"
  - "In chat: 3–5 lines — outcome, cost, top router finding — then the Proposed changes table."
  - "Ask which proposed changes to apply."
```

## Gate — improvements

Apply only the changes the engineer approves, one file at a time. Rule and index files are
shared across sessions; an unreviewed edit there changes every future session.

Once the engineer has decided, append an `## Applied` section to retro.md with one line per
proposal, in this exact shape (the meta-analysis report reads it):

```markdown
## Applied
- #1 applied: <file> — <what changed>
- #2 skipped: <reason, or "by engineer">
```

Every proposal gets a line, including skipped ones. Write "- none proposed" when the table was
empty.

When an approved change edits a rule, process, skill or tool, update the matching
`Documentation/` page in the same repository as part of the same change.
