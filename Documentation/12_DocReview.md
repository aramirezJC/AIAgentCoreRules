# Doc Review Tool

`Tools/doc-review/` previews a document and its Mermaid diagrams as a tabbed page on your own
machine and lets you comment on them before anything is published. Comments are stored next to
the doc, and the agent reads and answers them from the command line. Everything stays local:
the server listens on `127.0.0.1` only. Plain Python 3 (standard library only); marked, mermaid
and svg-pan-zoom load from CDNs in the browser.

## Commands

| Command | What it does |
|---|---|
| `doc_review.py serve <doc.md> [<diagram.mmd>...] [--port N] [--open]` | Live server. One tab per file, live reload on save, in-page comments. Prints the URL |
| `doc_review.py serve <doc.md> ... --static [--output PATH] [--open]` | Writes a single HTML preview (default `_doc_review_preview.html` next to the doc). No server, no comments |
| `doc_review.py comments <doc.md> [--status open\|ready\|addressed\|resolved\|all] [--json]` | Lists comment threads resolved to `file:line`, plus inline `@CLAUDE:` markers |
| `doc_review.py reply <doc.md> <thread_id> "<message>" [--status addressed]` | Adds an agent reply, optionally marking the thread addressed |

`Tools/mermaid-preview/mermaid_preview.py` is the older entry point. It forwards to
`serve --static`.

## Commenting in the page

In live mode, select text in a Markdown tab or click a diagram node, edge or empty space to start
a comment. The sidebar groups threads as Drafts, Active, Orphaned (the anchored text or node is
gone) and Resolved. Each thread moves open → ready → addressed → resolved. The engineer marks a
thread ready for the agent, and the agent replies and marks it addressed. Threads live in
`<doc>.review.json` beside the doc. Unsent drafts survive a reload.

## Progress tab

When the served doc's folder contains a `<Name>_Progress.md` (a CreateFeature feature folder),
a **Progress** tab is added first, automatically. `/preview-feature <Name>` opens a feature this
way, with its TDD and diagrams:

- **Phases and steps.** Phases 1–8 and their gates come from `Processes/CreateFeature/index.md`.
  The steps are the `##` headings of each `Phase*.md` file.
- **Green ✓.** A phase is complete when the progress file has a gate handoff block for it, and
  then all its steps are checked. Steps of the current phase are checked when the checkpoint's
  `done` list mentions them. That match is approximate. A skipped phase stays unchecked even
  when later phases are done.
- **Task list.** Tasks in `<Name>_TaskList.md` are listed under Phase 4 as done (✓), partial (~)
  or not started (○).
- **Current phase.** Highlighted in blue.
- **Gate to pass next, in red.** This is the current phase's gate until its handoff block is
  written, then the next unfinished phase's.

The tab refreshes whenever the progress file, the task list or a CreateFeature phase file
changes. Static mode includes the tab without refreshing.

## Tests

```bash
python3 -m unittest discover -s Tools/doc-review/tests -p 'test_*.py'
node Tools/doc-review/tests/smoke/review_ui_smoke.js   # needs Chrome + puppeteer in the npx cache
```

**Source files:** `Tools/doc-review/` · [[CreateFeature/index|CreateFeature]]

---

← [[11_Contributing|Contributing]] · [[00_Overview|Overview]]
