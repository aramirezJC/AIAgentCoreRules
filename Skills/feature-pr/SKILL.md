---
name: feature-pr
description: Tie a pull request to a CreateFeature feature and one of its TDD V-phases - record it in the feature's <FeatureName>_Progress.md (pull_requests block, sessions list), read its comments and review notes with gh, and record each addressed note in that feature's Checkpoint so the work lands in the right feature and session. Use when the engineer runs /feature-pr <PR> [FeatureName] [V-phase], opens a PR during Phase 4, or asks to read or address the review comments on a feature's PR.
argument-hint: "<PR number or URL> [FeatureName] [V-phase]"
---

# Feature PR

## Authoritative feature state

Read `Processes/FeatureState.md` for the shared tool contract. `state.json` is authoritative;
Progress Markdown is generated. All legacy references below to editing progress mean tool
operations, never direct Markdown/JSON edits. Use focused `get`, revision-checked mutations,
and explicit migration for legacy features. Preserve engineer approval gates.


Record PRs through `pr`; record acknowledged review work through `checkpoint`.


Paths are relative to the AIAgentCoreRules root (the parent of the `Rules/` folder that holds
MetaRouter.md). Run commands from the project root.

```yaml
paths:
  features_root: "Run python3 <core>/Tools/setup/project_config.py --project <project-root> get features (CLI/env/config/legacy precedence)"
  progress_file: "<features_root>/<FeatureName>/<FeatureName>_Progress.md"
  tdd:           "<features_root>/<FeatureName>/<FeatureName>_TDD.md"
  cli:           "Tools/doc-review/doc_review.py"

steps:
  - "PR: the first argument, a number or a GitHub PR URL (take the number). None → ask and stop."
  - "Feature: the second argument; else the feature whose progress file lists this session's id8 under `sessions`; else the session title (feature lane); else list the folders with a progress file, ask and stop. Never guess a close name match."
  - "V-phase: the third argument (V0, V1, …); else the PR already listed under `pull_requests` in the progress file; else match the PR's title and branch (gh pr view <PR> --json title,headRefName) against the TDD's '### V<n> — …' headings under '## Development plan'. More than one candidate, or none → list the V-phases, ask and stop."
  - "Record, in the progress file's header yaml block: add the PR under `pull_requests:` → `  V<n>: [<PR>, …]` (create the block after sources_of_truth if missing; no duplicates); add the session folder name (Session tracking block) to `sessions` if no entry ends in the same id8; set updated_at."
  - "Read: python3 <cli> pr-notes <PR> --repo-dir <feature folder>. Show the notes grouped by file, one line each, and mark the ones the Checkpoint already lists as addressed. Do not paste the raw output twice."
  - "Then wait. The engineer picks which notes to address; this skill does not change code on its own."
  - "Addressing a note: follow the lane the feature is in (Phase 4 per-file checklist, /audit, typecheck). After the engineer acknowledges each fix, add to the Checkpoint `done` list: \"PR #<PR> <file:line or 'review'>: <note gist> — addressed (<what changed>)\". A note left as is goes in context_notes with the reason."
  - "Reply on GitHub only when the engineer asks; never resolve review threads."
  - "Batch replies: python3 <cli> pr-pull <PR> --feature-dir <feature folder> writes <FeatureName>_PR<PR>_review.json (one thread per inline root, conversation comment or review body; a re-pull keeps drafted replies and flags vanished threads `gone`). Fill each thread's `reply` field — subagents may research threads in parallel, the main session writes the file. Show the engineer python3 <cli> pr-push <draft> (a dry run listing every reply); post with --confirm only after the engineer approves that list. Posted replies are recorded in the draft, so a re-push never repeats one. Only PRs under the feature's pull_requests are accepted."
  - "End with one line: the progress file path, the V-phase, and how many notes are open vs addressed. The doc-review Progress tab shows the notes under that V-phase (refreshed every 5 minutes)."
```

## Rules

```yaml
rules:
  - "Write only to the progress file of the feature chosen above — that is the point of this skill."
  - "Never edit a block under 'Gates Passed'."
  - "A PR touching two V-phases is listed under each; ask the engineer before adding the second."
  - "gh failing (not logged in, wrong repo) → report its error line and stop; suggest `! gh auth login`."
  - "Batch PRs (Phase 4 batched publishing) are created and recorded by /publish-batch; this skill reads and addresses their notes. Fixes are pushed to the batch's own branch, so the same PR updates."
```
