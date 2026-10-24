# Contributing

How to change a core rule, process, template, skill or tool.

## Where a change belongs

| You are changing | Repository |
|---|---|
| A portable rule, process, template, skill, the session-lifecycle tool, or this documentation | **AIAgentCoreRules** |
| Anything specific to one project — its rules, SystemIndex, Systems or SystemPatterns docs, Runnable tools, project skills | **That project's host layer** (e.g. TripleMatchAiMetaData) |
| Game code | **Game repository** |

The test: would the change be correct on a different Unity project? If yes, it belongs here. If
it names a project type, path or tool, it belongs in the host layer.

When you change a rule, process, skill or tool, update the matching documentation page in the
same commit. The agent does this too when it applies an approved retrospective change.

## Where improvements come from

Most changes start in a [[07_SessionTracking#Retrospectives|retrospective]]. `/end-session` traces each correction to a root cause
and proposes a concrete edit. Apply only the proposals you approve, one file at a time, because
rule files change every future session.

| Root cause | Typical fix |
|---|---|
| missing-rule | Add a rule, or a tag, to the relevant rule file |
| missing-index-entry | Add or extend a Systems / SystemPatterns doc in the host layer and register it in its SystemIndex |
| rule-ignored | Move the rule earlier in the process, or add it to a checklist or `/audit` |
| signature-guessed | Strengthen the Stop and Verify checks, or add the type to a Systems doc |
| scope-misread | Refine the mode triggers or the scope gate |

## Conventions

- **Rule and process files** start with an `apply:` line: `always` (imported by `CLAUDE.md`),
  `on-demand` (loaded through the routing table) or `superseded`. Keep always-on files short —
  they cost context in every session.
- **Structured content** is written as YAML blocks so the agent can follow it step by step.
- **Tags** are defined once in `Rules/CoreTags.md` and referenced everywhere else by label.
- **Lane processes** (Small Task, Bug Fix) end with a *Router check* block listing the files and tools the lane is expected
  to load; `/end-session` compares it with the router trace.
- **Skills** live in `Skills/<name>/SKILL.md` and are linked into each engineer's
  `.claude/skills/`. Tell the team when you add one so they can add the link.
- **Tools** run on stock `python3`, and hooks must always exit 0 so a failure never blocks a
  session.
- **Documentation pages** are written for Obsidian: wikilinks (double square brackets) between pages, a *Source
  files* line and a navigation footer. File-name numbers give the page order.

## Publishing to Confluence

Confluence's Markdown import shows wikilinks as literal text, so export a cleaned copy first:

```bash
python3 Tools/docs-export/export_confluence.py Documentation
```

The script replaces every wikilink with its label and removes the *Source files* lines and the
navigation footers. It writes to `GitIgnoreConfluenceExport/` next to `Documentation/` (ignored
by the global gitignore) and never modifies the source pages. Use `--out <dir>` to write
somewhere else. It works the same on a host layer's `Documentation/` folder.

**Source files:** [[CoreTags]] · [[README]]

---

← [[10_HostProjectLayer|Host Project Layer]] · [[00_Overview|Overview]]
