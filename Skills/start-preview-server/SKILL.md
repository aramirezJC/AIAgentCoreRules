---
name: start-preview-server
description: Open a CreateFeature feature's documentation in the local doc-review preview server - a Progress tab (current phase, steps, tasks, next gate) first, then the TDD (or GDD when there is no TDD) and the architecture diagrams. Use when the engineer runs /start-preview-server [Name] or asks to see, open or preview a feature's plan status, TDD or diagrams.
---

# Start Preview Server

Open the persistent project preview without editing feature documents or migrating data.
Resolve all paths from the project root; `<tools>` is AIAgentCoreRules/Tools.

1. Run `bash <tools>/doc-review/preview-control.sh start --project <project-root>`.
   It reuses the managed server if already healthy and prints its URL. If any
   `Tools/doc-review/*.py` or `Tools/feature-state/*.py` file changed since that server started,
   it restarts it instead and prints `restarted (tool code changed)` before the new URL — the
   port may change, so report the new URL. The server is independent of this LLM session; do
   not stop it at session end.
2. No name: open the returned Home URL. A name: use the exact feature directory under
   `$SESSION_FEATURES_ROOT`, otherwise `Assets/GitIgnoreAssets/Features`.
   If no match exists, list the available feature names and ask; never guess.
3. Open the returned URL with `?feature=<URL-encoded-name>` when a feature was supplied.
   Use available browser-opening tools, reporting failures without claiming it opened.
4. Report the URL and fixed tabs: Home, Plan, TDD, GDD, Class Diagram, Flow Diagram,
   LLM Performance. Missing content shows a placeholder. Legacy features display migration
   required; starting the preview never implicitly migrates them.
5. Feature comments live in `<feature-directory>/review.json`, independent of the current
   tab or first document. Read with `doc_review.py comments <feature-directory>`. When working
   a batch of them, follow `Processes/ExternalDocPass.md` → "Comment research": subagents research
   and propose edits, the main session applies them in order and replies.
6. To explicitly stop this project's managed server use `$kill-server` or
   `bash <tools>/doc-review/preview-control.sh stop --project <project-root>`.

## Mermaid syntax and validation

When preparing diagrams for this preview, avoid literal semicolons in sequence-diagram
message text: Mermaid treats them as statement separators. Use commas, or encode an
intentional semicolon as `#59;`. Validate diagrams with an available Mermaid renderer before
claiming they render successfully. If renderer tooling or browser inspection is unavailable,
report that limitation explicitly and request an engineer rendering check.
