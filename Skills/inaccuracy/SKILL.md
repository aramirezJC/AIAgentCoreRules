---
name: inaccuracy
description: Log an agent mistake the engineer just corrected into the session metrics. Run by the engineer as /inaccuracy <reason>.
argument-hint: "<what was wrong>"
disable-model-invocation: true
---

# Log Inaccuracy

Lifecycle script (path from the Session tracking block, else):
`GitIgnoredExternals/AIAgentCoreRules/Tools/session-lifecycle/session_lifecycle.py`

```yaml
steps:
  - "If $ARGUMENTS is empty, ask for a one-line reason and stop."
  - "Run: python3 <script> note --kind inaccuracy \"$ARGUMENTS\""
  - "Reply with one line: the logged count. No apology, no re-litigating — then continue with the corrected approach."
```
