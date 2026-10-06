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

## 3. Run the installer

```bash
python3 GitIgnoredExternals/AIAgentCoreRules/Tools/setup/install.py check   # preview
python3 GitIgnoredExternals/AIAgentCoreRules/Tools/setup/install.py         # apply
```

It merges `Tools/setup/settings.core.json` into `.claude/settings.json` (session hooks and the
worktree settings below), then each host layer's `Setup/settings.host.json`; links every layer's
skills into `.claude/skills/`; and creates `CLAUDE.md` with the core imports if it is missing.
It only adds or updates what the fragments define, backs `settings.json` up to
`settings.json.bak` before changing it, and is safe to re-run — run it again after pulling
AIAgentCoreRules or the host layer. Details: [[Tools/setup/README|setup README]].

The session hooks never block a session — if tracking fails, Claude Code carries on. Session
folders are written to `GitIgnoreReports/Sessions/`; override with `SESSION_REPORTS_ROOT`. The
`Stop` hook keeps metrics current for sessions that never exit.

## 4. Agent worktrees

Background agents work in git worktrees under `.claude/worktrees/`. The installer sets:

- `worktree.baseRef: "head"` — a new worktree branches from your current branch, not from the
  default branch, so its work merges back cleanly.
- `worktree.symlinkDirectories` — `GitIgnoredExternals`, `GitIgnoreReports`, `.claude/skills`,
  plus whatever the host layer adds. A worktree then has the rules, tools and skills, and its
  session reports land in the main checkout instead of being deleted with the worktree.

Test agent work in the project you already have open, not by opening the worktree: run
`/land-worktree` to merge the branch, test it, then remove the worktree and branch. For a
worktree made by hand with `git worktree add`, run `install.py prepare-worktree <path>` to add
the symlinks.

## 5. Verify

Start a new Claude Code session in the project. You should see a **Session tracking (started)**
block in the agent's context, and `/feature`, `/end-session` and the other commands should be
available.

## Requirements

- Claude Code (CLI, desktop or IDE extension)
- Stock `python3` — the session-lifecycle tooling needs no third-party packages

**Source files:** [[Tools/setup/README|setup README]] · [[Tools/session-lifecycle/README|session-lifecycle README]] · [[Skills/land-worktree/SKILL|/land-worktree]]

---

← [[00_Overview|Overview]] · [[02_WorkModes|Work Modes and Routing]] →
