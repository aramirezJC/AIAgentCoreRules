---
name: generate-meta-review
description: Run the MetaReview process over past sessions for a time frame - cost, router and process slips, follow-through on retro proposals - and produce the report page and ticket list. Use when the engineer runs /generate-meta-review [time frame] or asks for a review of past sessions.
argument-hint: "[time frame: 'last 2 weeks' | 'since 2026-09-01' | '2026-09-01..2026-09-30']"
---

# Generate Meta Review

Paths are relative to the AIAgentCoreRules root (the parent of the `Rules/` folder that holds
MetaRouter.md).

```yaml
steps:
  - "Run: python3 <lifecycle script> set --lane investigation --work-type question --title \"Meta review <start>..<end>\""
  - "Turn $ARGUMENTS into a window: start and end as YYYY-MM-DD, end defaulting to today. Relative frames ('last 2 weeks', 'this month') count back from today."
  - "No arguments → MetaReview's default window (since the previous review, else the last 7 days)."
  - "Unparseable time frame → ask once, giving the accepted forms from argument-hint."
  - "Read: Processes/MetaReview.md and follow it. The window from this skill replaces its 1_window default; still state it in one line."
```
