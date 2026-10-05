# Session Tracking and Retrospectives

Every agent session is measured, so we can see what the agent actually did, where it went
wrong, and which rule or process changes would have prevented it. Tracking is automatic; the
engineer's part is logging corrections and running `/end-session`.

## Lifecycle

| Moment | What happens | Who |
|---|---|---|
| Session start | The SessionStart hook creates the session folder and puts a **Session tracking** block in the agent's context | Automatic |
| Naming (optional) | `/start-session <name>` names the session; the name goes into the folder and the metrics heading | Engineer |
| Mode classified | The agent records the lane (feature, bug_fix, small_task, investigation, other), the work type (bug_fix, small_feature, feature, question, other) and a short title | Agent |
| Agent makes a mistake you correct | `/inaccuracy <what was wrong>` | Engineer |
| Agent retracts a claim, or you reject its approach | It logs the inaccuracy itself, marked `agent` | Agent |
| A correction was never logged | `/end-session` records it from the retro's Corrections, marked `retro` | Agent |
| You deliberately change direction | `/iteration <what changed>` | Engineer |
| Wrap up | `/end-session` compiles metrics, writes the retrospective and opens both files | Engineer |
| Session closes without `/end-session` | The SessionEnd hook still compiles metrics (no retrospective) and records the exit time and reason; a resumed session's end time is updated on each exit | Automatic |

Every hook run appends one line to `GitIgnoreReports/Sessions/hooks.log` (event, session, working
directory, outcome). If a session's metrics look stale, check that log first: no `end` line means the
hook never fired; `no folder for this session` or `ERROR` means it fired and failed. The hooks
take the project directory from the hook payload's `cwd`, so they work wherever Claude Code launches them.

The **lane** is the process that ran; the **work type** is what the work was. They usually match,
but not always: an investigation into a crash is lane `investigation`, work type `bug_fix`. If the
agent does not set a work type, it follows the lane (small_task → small_feature, investigation →
question) and metrics.md marks it "(from lane)". The meta-analysis groups cost by work type to
show which kinds of work are most expensive.

An **inaccuracy** is an agent error. An **iteration** is a decision — a scope change or a new
direction — and is not counted against the agent.

Each note records who logged it: `engineer`, `agent` or `retro`. metrics.md shows the split when
it is not all engineer, for example `3 (engineer 1 · agent 1 · retro 1)`. The meta-analysis
treats `retro` entries as found late, so a session whose corrections were all back-filled still
shows up as "not logged live".

## Output

One folder per session:

```
GitIgnoreReports/Sessions/<YYYY-MM-DD_HHMM>_<lane>_<name>_<id8>/
  session.json   state (source of truth)
  metrics.md     rendered report
  retro.md       written by /end-session
  tokens/        per-session token report
```

### metrics.md contains

- Session ID, name, title, lane, work type, start/end time, whether `/end-session` ran
- Total tokens, turns, subagents
- Every logged inaccuracy and iteration, timestamped
- **Lane changes** — each time the lane changed mid-session (for example a Bug Fix detour into
  `small_task` and back), with the time, so earlier lanes are not lost
- **Work type changes** — the same, for the work type
- **Router trace** — the files loaded through `CLAUDE.md`, then every rule and process file
  loaded on demand, in order, with the time and how it was loaded
- A count of each of the host project's Runnable tools the agent ran (for example `typecheck.py`,
  `codeindex.py`, `usages.py`)

The router trace is read from the session transcript, not from the agent's memory. Rows loaded
with the Read tool are exact; rows inferred from shell commands are heuristic (a `grep` over a
file counts as a load).

## Retrospectives

`/end-session` scales the retrospective to the lane.

**Feature sessions** follow [[03_CreateFeature#Phase 8 — Retrospective|Phase 8]] of the [[03_CreateFeature|Create Feature process]] across every session of the
feature. If the feature is still in progress, `/checkpoint` runs first so the next session can
resume.

**All other lanes** get a short retrospective with these sections:

| Section | Content |
|---|---|
| Outcome | What was delivered and how it was verified |
| Router check | The files the lane's process expects to be loaded vs. what the trace shows — misses and unnecessary loads |
| Corrections | Each inaccuracy with a root cause: missing rule, missing index entry, rule ignored, signature guessed, or scope misread |
| Discovery gaps | Anything looked up mid-task that the host project's SystemIndex or Systems docs should have supplied |
| Proposed changes | Concrete, minimal edits to rules, processes or index — **not applied** |
| Cost | Tokens, turns, subagents, and the heaviest turns ranked by **fresh** tokens (plus the heaviest by total, if different), each judged necessary, partly necessary or avoidable |

After the engineer decides on the proposals, the retro gets an `## Applied` section with one line
per proposal (`- #N applied: …` or `- #N skipped: …`). The meta-analysis report reads it to know
which solutions were actually implemented.

Every claim points at a trace row, a logged note or a `file:line`.

If the session changed lanes, the router check runs once per lane segment, splitting the trace
at each lane change. The depth of the retrospective follows the lane with the heaviest work.

## The improvement gate

Proposed changes are only applied after the engineer approves them, one file at a time. Rule
and index files are shared across every future session, so an unreviewed edit changes the
agent's behaviour everywhere. This is how the framework improves over time: corrections become
root causes, root causes become rule or index changes, and the next session avoids the mistake.

When an approved change edits a rule, process, skill or tool, the matching `Documentation/`
page is updated as part of the same change.

## Meta-analysis report

To see trends across sessions, run from the project root:

```bash
python3 GitIgnoredExternals/AIAgentCoreRules/Tools/session-analysis/session_meta_report.py
```

It writes `GitIgnoreReports/SessionAnalysis.html`, a single page to open in a browser (print it
to PDF if needed), with:

- **Token expenditure:** a bell curve of tokens per turn (normal fit on a log scale, ±1σ/±2σ
  bands), switchable between fresh and total tokens, plus the total for each session.
- **Worst performers:** the heaviest turns, sessions, turn categories, lanes and work types. Each turn shows
  the verdict its retro gave it (necessary, partly avoidable, avoidable), plus how many fresh
  tokens were flagged avoidable.
- **What saved us:** an estimate of the fresh tokens and turns saved by each Runnable tool,
  knowledge doc, skill and routing file. It is based on measured medians (tokens per tool call,
  per turn, per subagent survey) and stated assumptions that the report prints and
  `--assumptions` can override. Knowledge docs earn credit only when no retro says they fell
  short.
- **Issue heat maps:** area × session, from retro proposals, router misses and discovery gaps;
  and correction root cause × lane.
- **Solutions:** every proposed change with its status (applied / skipped from the retro's
  Applied section, *likely applied* from git history, or open) and the evidence.
- **What else could be improved:** recurring open areas, repeated router misses, tracking gaps
  and token outliers.

*Likely applied* is inferred from commits made after the session, so check the evidence column.
The more consistently retros record an `## Applied` section, the more exact the report is.

## Meta review

The report above is the quantitative half. A **meta review** ([[Processes/MetaReview|MetaReview process]])
wraps it in a repeatable review of one time window, by default since the previous review:

1. Sort the window's session folders into real sessions, stubs and uncompiled sessions, and
   compile the uncompiled ones (`session_lifecycle.py compile --session-id <id>`).
2. Run the report, then read every retro in the window for router misses, skipped steps,
   unlogged corrections, discovery gaps and cost.
3. Keep only findings that recur in two or more sessions, or the window's largest cost driver.
4. Check every proposal against the current file contents, plus the previous review's open
   tickets. Proposals the engineer skipped are never raised again.
5. Check the metadata and tools repos for uncommitted or unpushed work.
6. Write `GitIgnoreReports/MetaReviews/<date>_MetaReview.html` (fixed layout) and
   `<date>_Tickets.md`, which lists tickets by priority: P1 for work or data at risk, P2 for
   recurring misses or the top cost driver, P3 for polish. Then work through the tickets one at a time.

**Source files:** [[Processes/MetaReview|MetaReview process]] · [[Tools/session-analysis/README|session-analysis README]] · [[Tools/session-lifecycle/README|session-lifecycle README]] · [[Skills/start-session/SKILL|/start-session]] · [[Skills/end-session/SKILL|/end-session]] · [[Skills/inaccuracy/SKILL|/inaccuracy]] · [[Skills/iteration/SKILL|/iteration]]

---

← [[06_Investigation|Investigation Mode]] · [[00_Overview|Overview]] · [[08_Commands|Command Reference]] →
