## apply: on-demand — loaded by [[MetaRouter]]

# Meta Review

A periodic review of many sessions at once: what they cost, where routing and processes slipped,
and whether earlier retro proposals actually landed. The output is a report page and a ticket
list that the engineer works through in priority order. No code is written during the review
itself; tickets are addressed afterwards, one at a time, each in its own lane.

Record the session as lane `investigation`, work type `question`.

Tag definitions: [[CoreTags]]

```yaml
inputs:
  sessions:  "<reports root>/Sessions/*/  — session.json, metrics.md, retro.md, tokens/"
  hooks_log: "<reports root>/Sessions/hooks.log"
  tool:      "../Tools/session-analysis/session_meta_report.py  — quantitative report over all sessions"
  previous:  "<reports root>/MetaReviews/  — the newest *_Tickets.md and *_MetaReview.html"
  repos:     "every agent-metadata and personal-tools repo the host project links in"
outputs:
  report:    "<reports root>/MetaReviews/<YYYY-MM-DD>_MetaReview.html  (publish it as an Artifact when that tool exists)"
  tickets:   "<reports root>/MetaReviews/<YYYY-MM-DD>_Tickets.md"
```

---

## Steps

```yaml
steps:
  1_window:
    - "Default window: from the previous review's date to today. With no previous review, the last 7 days."
    - "State the window in one line and continue. Ask only if the engineer named a different one."
    - "A session belongs to the window by started_at. Name any session that straddles the start."

  2_compile:
    - "List every session folder in the window and sort each into one of three groups:"
    - "  real: has a lane or a title, or has tokens."
    - "  stub: no lane, no title, no tokens. Count stubs; never analyse them."
    - "  uncompiled: real, but tokens missing. Run `session_lifecycle.py compile --session-id <id>` (never --final) before estimating."
    - "Estimate from the transcript only when compile fails, and label every such number 'est.' with the method."

  3_quantitative:
    - "Run session_meta_report.py. Take token distributions, heaviest turns and heat maps from it; do not recompute them inline."
    - "It covers all history, not the window: filter its rankings to the window when quoting them."

  4_read:
    - "Read every retro.md in the window. Above ~8 retros, fan out the extraction to subagents ([DELEGATE]) and keep the synthesis inline."
    - "Extract per retro: router misses, skipped process steps (/audit, typecheck, tests), corrections (logged vs unlogged), discovery gaps, the three heaviest turns, proposals and their Applied lines."
    - "For real sessions without a retro: read session.json iterations, the lane history and the router trace. A large session with no retro is itself a finding."

  5_patterns:
    - "A finding qualifies when it recurs in 2+ sessions, or is the single largest cost driver in the window."
    - "Quote frequency as 'N of M retros' or 'N sessions', never 'often'."
    - "Tag each finding with one kind: Cost · Router · Process · Tooling · Signal (tracking data is wrong or missing) · Noise."
    - "For each finding, say what already mitigates it (an applied rule, a saved preference) and what lever is left."

  6_follow_through:
    - "Check every proposal from the window's retros, plus every open ticket from the previous review."
    - "Verify against the current file contents (grep for the change itself). The tool's 'likely applied' is a hint, not evidence."
    - "Statuses: Landed · Open · Skipped (engineer declined; record the reason) · Superseded (a later change made it moot)."
    - "Skipped is final. Never re-propose a skipped change or one that contradicts a saved preference."

  7_repo_state:
    - "For each metadata and tools repo: `git status --short` and ahead/behind its upstream."
    - "Uncommitted or unpushed rule work is a risk item, with file counts."
    - "Re-check just before writing the report: the engineer may have committed during the review."

  8_report:
    - "Write the report page in the layout below, then publish it."
    - "Every number on the page traces to a file or a command run this session."

  9_tickets:
    - "Turn every open item from 5–7 into a ticket in the format below, ordered by priority."
    - "Present the list in chat and stop. The engineer picks the order; each ticket then runs in its own lane (small_task, bug_fix, or other for rule edits)."
    - "When a ticket is done, mark it in the tickets file with the commit that closed it."

  10_close:
    - "Offer /end-session."
```

## Report layout

Fixed, so reviews can be compared side by side.

```yaml
sections:
  header:        "Window, sources read, link or path to the previous review"
  figures:       "Exactly 4: real sessions (and stubs), total tokens (compiled + est.), retros written, logged vs observed corrections"
  tokens_chart:  "One bar per real session, one scale. Compiled bars solid, estimated bars hatched. Lane and outcome on hover."
  findings:      "From step 5, most costly or most frequent first, each with its kind chip and its evidence line"
  follow_through:"Table: proposal · source session · status"
  risks_next:    "Uncommitted work and missing retros · the next 3–5 actions"
  sessions:      "Table of every real session: date, title, id8, lane, tokens, turns, retro yes/no"
```

## Ticket format

```markdown
### MR-<YYYYMMDD>-<NN> · P<1|2|3> · <short title>
- **Repo / files:** <repo> · `<path>` (say which repo before editing, per the host's workspace rules)
- **Problem:** <one or two sentences> — evidence: <session ids or retro sections>
- **Change:** <what to do>
- **Done when:** <a check anyone can run: a grep, a command, a re-run of the tool>
- **Status:** open | done (<commit>) | skipped (<reason>)
```

```yaml
priority:
  P1: "Work or data at risk: uncommitted rule work, a tool that silently reports wrong results, metrics that misreport"
  P2: "Recurring miss (3+ sessions) or the top cost driver in the window"
  P3: "One-off gap, documentation or comment polish, noise reduction"
order_within_priority: "Higher frequency first, then larger token cost"
```

## Router check (used by /end-session)

```yaml
expected_loads:
  - "Processes/MetaReview.md"
  - "the previous review's *_Tickets.md, when one exists"
expected_tools: [session_meta_report.py, session_lifecycle.py compile]
expected_outputs: ["<date>_MetaReview.html", "<date>_Tickets.md"]
```
