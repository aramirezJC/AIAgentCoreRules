# Setup

`install.py` wires AIAgentCoreRules (and any host layer next to it) into a host project. Stock
`python3`, no packages. Run it from anywhere inside the project — the project root is the main
checkout of the git repository you are in (`--project <path>` overrides).

```bash
S=GitIgnoredExternals/AIAgentCoreRules/Tools/setup/install.py
python3 $S check                       # what install would change
python3 $S                             # install (same as `install`)
python3 $S worktrees [--json]          # linked worktrees: branch, dirty, ahead/behind, from_upstream
python3 $S prepare-worktree <path>     # add the symlinks to a worktree made by hand
```

## What install does

| Step | Source | Result |
|---|---|---|
| Settings | `settings.core.json`, then each layer's `Setup/settings.host.json` | merged into `.claude/settings.json` (backup: `settings.json.bak`) |
| Skills | every `<layer>/Skills/<name>/SKILL.md` | `.claude/skills/<name>` → `../../GitIgnoredExternals/<layer>/Skills/<name>` |
| CLAUDE.md | — | created with the three core imports if missing; missing imports reported, never edited |

Layers are the entries of `GitIgnoredExternals/`; AIAgentCoreRules is applied first. Merge rules:
objects merge key by key, lists of plain values are unioned, other values are set, and hooks are
matched by command — an existing hook with the same command is left alone. Nothing is deleted:
a skill link that points elsewhere is reported as a conflict and kept.

## Host layer fragment

A host layer adds project-specific settings in `Setup/settings.host.json`, using the same shape
as `settings.json`. For example, a Unity project whose personal assets live in a gitignored
folder under `Assets/`:

```json
{ "worktree": { "symlinkDirectories": ["Assets/GitIgnoreAssets"] } }
```

## Worktree settings

`settings.core.json` sets `worktree.baseRef` to `head`, so agent worktrees branch from the
current branch. It also symlinks `GitIgnoredExternals`, `GitIgnoreReports` and `.claude/skills`
into every worktree Claude Code creates. Removing a worktree removes the links, not what they
point at. `/land-worktree` (`Skills/land-worktree`) merges a worktree back and cleans it up.
