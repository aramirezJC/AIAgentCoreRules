## apply: on-demand — loaded by [[MetaRouter]] and [[Phase1_Intake]]

# External Doc Pass

For documents that live outside the repository and are reviewed there, such as a feature TDD on
Confluence. Every fetch of a large page and every update re-sends the whole page through the
context, so the cost is set by how many round trips happen, not by how big the change is. Work
in **passes**: read once, change locally, write once.

The host project supplies its conventions (page template, style reference, markup, comment
convention) in a doc-conventions rule file listed in its SystemIndex. Load it before the first
publish of a session.

Tag definitions: [[CoreTags]]

---

## Publish (first version, or a full rewrite)

```yaml
publish:
  - "Load the host's doc-conventions file. Read its style reference page once, for structure only."
  - "Build the complete page body locally (a scratch file next to the local source doc), including diagrams. Validate diagrams before publishing if the host names a validator."
  - "Publish in one create or update call."
  - "Record the page in the progress file's sources_of_truth: kind, id, title, version returned by the call."
```

## Review pass (engineer comments)

One pass handles every comment that is ready. Do not fetch or update per comment.

```yaml
review_pass:
  1_read:     "Fetch once: the page body, its inline comments with replies, and its footer comments. That is the whole read budget for the pass."
  2_list:     "Build the pass list: each actionable thread (per the host's resolution convention), what it asks, and where it applies. Threads still under discussion are listed as skipped."
  3_confirm:  "Show the pass list. Ask only about items that are ambiguous or conflict with each other; do not ask per item."
  4_apply:    "Apply every item to the local copy of the body in one go. An item that removes a question also removes every mention of it."
  5_write:    "One update call. If the update fails on a version conflict, re-read once and re-apply; never loop."
  6_report:   "Reply with: new version, threads addressed (the engineer resolves them; the agent cannot), threads skipped and why. Update sources_of_truth to the new version."
budget:       "Per pass: at most 2 page reads (step 1 and one conflict retry) and 1 update. Exceeding it means the pass was split; say why in the report."
```

## Style decisions

A comment like "move the tags before the name" or "colour new classes yellow" is a convention, not
a one-off edit:

```yaml
style_decisions:
  - "Apply it everywhere it fits in the current pass, not only where the comment is anchored."
  - "Propose adding it to the host's doc-conventions file so the next document starts with it. Do not log it as an /iteration."
```

## Sync with the local source

```yaml
local_sync:
  - "When the external page is the one being reviewed, it is the source of truth: after a pass, bring the local Markdown in line in one edit per file, not per comment."
  - "Never re-publish the local file over the page; that discards the review changes."
```
