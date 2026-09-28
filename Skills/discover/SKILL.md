---
name: discover
description: Survey a system, directory, or feature area in a subagent and return only a compact map (key types, entry points, integration points, gotchas) so the main context stays free for analysis. Use for "where is X / which files / who implements Y" questions and for Phase 2 Discovery.
argument-hint: "<system or area>"
---

# Discover

Breadth goes to a subagent ([DELEGATE]). The main context receives the map, not the file dumps.

```yaml
steps:
  - "If the host project's SystemIndex has a Systems/ entry for the area, Read it first and pass its key interfaces to the agent."
  - "Launch ONE Explore agent (thoroughness: medium; 'very thorough' only if asked). For several independent areas, one agent per area in a single message."
  - "Relay the map. Read method bodies inline only where a conclusion depends on them."
```

Agent brief (fill in the area):

> Map `<area>` in this repository. Prefer the project's Runnable tools when available
> (`codeindex.py where|members|implementers|subclasses`, `usages.py`) over reading whole files.
> Return, each with `file:line`:
> 1. Key types — interfaces, base classes, managers — one line each.
> 2. Entry points — where the flow starts (lifecycle hooks, message handlers, state entries).
> 3. Integration points — factories, registries, manifests, config roots, generators.
> 4. Gotchas — ordering, save mechanics, editor-only steps, anything surprising.
> 5. Negative findings — what you checked and ruled out.
> Do not read `.prefab`, `.asset`, or `.unity` files. Keep the report under 60 lines.

If the area has no Systems/ entry, end the reply by offering to save the map as one (the
SystemIndex asks for this after discovery). Write it only if the engineer agrees.
