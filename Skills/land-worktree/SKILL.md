---
name: land-worktree
description: Merge an agent's worktree branch into the engineer's current branch in the main checkout, wait for the engineer to test it (e.g. in the Unity Editor), then remove the worktree and branch — or roll the merge back. Use when the engineer runs /land-worktree, asks to bring an agent's worktree work into their branch, or asks to clean up finished worktrees.
argument-hint: "[worktree name | branch] [--squash]"
---

# Land Worktree

Agents work in `.claude/worktrees/<name>`; the engineer tests in the main checkout, which is the
project already open in the editor. This skill moves the work across and cleans up after it.
Paths are relative to the AIAgentCoreRules root (the parent of the `Rules/` folder that holds
MetaRouter.md). Run every git command in the **main checkout**, never inside the worktree.

```bash
python3 <core>/Tools/setup/install.py worktrees          # name, branch, dirty, ahead/behind, from_upstream
python3 <core>/Tools/setup/install.py worktrees --json
```

```yaml
steps:
  - "Record the session as lane other, work type other (Session tracking block). Skip this when /end-session called this skill: the session keeps its lane."
  - "List worktrees with `install.py worktrees`. No argument → show the list and ask which one. A PRUNABLE row → offer `git worktree prune`."
  - "Target branch = the main checkout's current branch. State it and the worktree branch in one line before doing anything."
  - "Preconditions — stop and report, do not fix silently:"
  - "  main checkout has uncommitted changes to tracked files (`git status --porcelain --untracked-files=no`) → ask the engineer to commit or stash"
  - "  worktree is DIRTY → the agent left uncommitted work; show `git -C <worktree> status --short` and ask"
  - "  ahead is 0 → nothing to land; offer cleanup only"
  - "Show `git log --oneline HEAD..<branch>` and `git diff --stat HEAD...<branch>`."
  - "from_upstream > 0 → the worktree branched from the default branch, not from the target. Merging brings those upstream commits too. Offer instead: cherry-pick only the agent's commits (`git log --reverse --format=%H HEAD..<branch> --not <upstream>`). Engineer chooses."
  - "Merge without committing so the engineer tests first: `git merge --no-ff --no-commit <branch>` (or `--squash` when asked). On conflicts: list the files, stop, let the engineer resolve or abort."
  - "If the host project has a compile check (e.g. a typecheck tool in its SystemIndex), run it now and report the result."
  - "Ask the engineer to test, and wait. Do not continue until they answer keep or reject."
  - "keep → `git commit --no-edit` (squash: commit with a message summarising the agent's commits). Then cleanup."
  - "reject → `git merge --abort` (squash: `git reset --merge`). Then ask: keep the worktree for more work, or discard it."
  - "Cleanup (keep, or reject + discard):"
  - "  `git worktree remove <path>` — never add --force on your own; if git refuses, show why and ask"
  - "  keep: `git branch -d <branch>` · discard: `git branch -D <branch>` after the engineer confirms"
  - "  branch exists on the remote (`git ls-remote --heads origin <branch>`) → ask before `git push origin --delete <branch>`"
  - "  `git worktree prune`"
  - "Reply with what landed (commit hash, or 'rolled back'), what was removed, and what is left in `install.py worktrees`."
```

## Rules

```yaml
rules:
  - "Never push the target branch, force-push, or merge into the default branch. Landing is local."
  - "Never commit the merge before the engineer says keep."
  - "Removing a worktree deletes only its folder: symlinked directories (worktree.symlinkDirectories) are links, so the main checkout's copies are untouched."
  - "git refuses to remove a worktree with modified tracked files or untracked, non-ignored files; ignored folders (e.g. Unity Library/) do not block it and are deleted with it. A refusal means real unsaved work — show it before asking about --force."
  - "Several worktrees to land → one at a time, each tested before the next."
```
