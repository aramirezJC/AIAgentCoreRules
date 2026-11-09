---
name: uses
description: Find who uses a type and which sites call specific members, using the core unity-tools usages.py and codeindex.py instead of manual grepping. Use for "who calls / who uses / find all callers of X" and before splitting an interface.
argument-hint: "<Type> [Member1,Member2,...]"
---

# Uses

Runnable tools live in `GitIgnoredExternals/AIAgentCoreRules/Tools/unity-tools/` (Tools/unity-tools/ in this repo).

```yaml
steps:
  - "Run: python3 <Runnable>/usages.py <Type> [--members <Members>]"
  - "Run: python3 <Runnable>/codeindex.py implementers <Type>   # when <Type> is an interface"
  - "Report the three buckets: DECLARES/IMPLEMENTS, CALLS <members> (with lines), everything else (per assembly)."
```

Blind spots — check these before reporting a zero:

```yaml
blind_spots:
  events:   "CALLS matches `Member(`. Event members are used as `Member +=` / `Member -=` and never match. For events, grep `\\bMember\\s*[+-]=` instead."
  lexical:  "Buckets are lexical — a local method with the same name is a false positive. Confirm with typecheck.py, which is authoritative."
  scope:    "Only files in generated .csproj projects are searched — code not compiled for the current build target is invisible."
```

A zero result is a claim too: state which query produced it and why that query could have found
a use if one existed.
