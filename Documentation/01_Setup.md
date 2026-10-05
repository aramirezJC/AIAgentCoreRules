# Setup

How to install the core framework in a local checkout of a Unity project. Everything below is
personal to your machine — none of it is committed to the game repository. The host project's
own documentation adds its project-layer repository and project-specific steps.

## 1. Clone and link the repository

Clone **AIAgentCoreRules** outside the game project, then link it in:

```bash
cd <game project root>
mkdir -p GitIgnoredExternals
ln -s <path to>/AIAgentCoreRules GitIgnoredExternals/AIAgentCoreRules
```

`GitIgnoredExternals/`, `CLAUDE.md`, `.claude/` and `GitIgnoreReports/` must be ignored by
your **global** gitignore (for example the patterns `*GitIgnore*` and `*CLAUDE*`). Never add
them to the game repository's `.gitignore`.

## 2. Create CLAUDE.md

At the project root, import the three always-on core files, followed by the host project's
always-on files:

```markdown
@GitIgnoredExternals/AIAgentCoreRules/Rules/MetaRouter.md
@GitIgnoredExternals/AIAgentCoreRules/Rules/StopAndVerify.md
@GitIgnoredExternals/AIAgentCoreRules/Rules/CoreTags.md
@GitIgnoredExternals/<HostLayer>/Rules/<ProjectRules>.md
@GitIgnoredExternals/<HostLayer>/SystemIndex.md
```

Keep this list short — every always-on file costs context in every session.

## 3. Install the session hooks

In `.claude/settings.json`:

```json
{
  "hooks": {
    "SessionStart": [{ "hooks": [{ "type": "command", "timeout": 30,
      "command": "cd \"$CLAUDE_PROJECT_DIR\" && python3 GitIgnoredExternals/AIAgentCoreRules/Tools/session-lifecycle/session_lifecycle.py hook-start" }] }],
    "SessionEnd":   [{ "hooks": [{ "type": "command", "timeout": 60,
      "command": "cd \"$CLAUDE_PROJECT_DIR\" && python3 GitIgnoredExternals/AIAgentCoreRules/Tools/session-lifecycle/session_lifecycle.py hook-end" }] }],
    "Stop":         [{ "hooks": [{ "type": "command", "timeout": 30, "async": true,
      "command": "cd \"$CLAUDE_PROJECT_DIR\" && python3 GitIgnoredExternals/AIAgentCoreRules/Tools/session-lifecycle/session_lifecycle.py hook-stop" }] }]
  }
}
```

The `Stop` hook keeps metrics current for sessions that never exit. The app can mark an idle
session completed without firing `SessionEnd`.

The hooks never block a session — if tracking fails, Claude Code carries on. Session folders
are written to `GitIgnoreReports/Sessions/`; override with `SESSION_REPORTS_ROOT`.

## 4. Link the core skills (slash commands)

```bash
mkdir -p .claude/skills && cd .claude/skills
for s in audit checkpoint discover end-session feature inaccuracy iteration resume start-session token-usage-reports; do
  ln -s ../../GitIgnoredExternals/AIAgentCoreRules/Skills/$s $s
done
```

Then link the host layer's skills the same way.

## 5. Verify

Start a new Claude Code session in the project. You should see a **Session tracking (started)**
block in the agent's context, and `/feature`, `/end-session` and the other commands should be
available.

## Requirements

- Claude Code (CLI, desktop or IDE extension)
- Stock `python3` — the session-lifecycle tooling needs no third-party packages

**Source files:** [[Tools/session-lifecycle/README|session-lifecycle README]]

---

← [[00_Overview|Overview]] · [[02_WorkModes|Work Modes and Routing]] →
