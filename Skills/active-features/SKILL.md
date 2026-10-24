---
name: active-features
description: List every CreateFeature feature that is not complete - its phase, status, last update, where work stopped and the command that resumes it in a fresh session. Use when the engineer runs /active-features or asks which features are in progress, what to pick up next, or where a feature stands.
---

# Active Features

Lifecycle script (path from the Session tracking block, else):
`GitIgnoredExternals/AIAgentCoreRules/Tools/session-lifecycle/session_lifecycle.py`

```yaml
steps:
  - "Run from the project root: python3 <script> features"
  - "Show the result as a table: Feature · Phase · Status · Updated · Next. Under it, list each feature's resume command exactly as printed (it carries the phase's recommended model)."
  - "If a feature's status is at_gate, say the gate is waiting on the engineer's confirmation."
  - "If the list is empty, say no features are in progress and offer /feature <Name>."
  - "Do not open progress files or resume anything. Resuming is the engineer's call: /resume-work <FeatureName>, ideally in a fresh session."
```

The same list, shortened, appears in the Session tracking block at the start of every session
that does not already belong to a feature.
