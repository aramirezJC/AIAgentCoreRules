---
name: kill-server
description: Stop a running doc-review preview server (started by /start-preview-server or doc_review.py serve) - lists the live servers with pid, port, doc and folder, and stops the one chosen, or all of them. Use when the engineer runs /kill-server [port|pid|all] or asks to stop, kill or shut down the preview / doc-review server.
argument-hint: "[port | pid <n> | all]"
---

# Kill Server

Resolve `<tools>` to AIAgentCoreRules/Tools and run from the project root.

- No arguments: use `bash <tools>/doc-review/preview-control.sh status --project <project-root>`
  then `stop --project <project-root>`. Stop only the current project's launcher-managed server.
- Explicit port, PID, or all: list `python3 <tools>/doc-review/doc_review.py servers` first,
  then use `stop --port <n>`, `stop --pid <n>`, or `stop --all` respectively. An ambiguous
  target requires the engineer's choice. Retain support for standalone document servers.
- Verify and report the resulting status. Do not kill unrelated processes or use a bare
  lsof/kill-by-port command; launcher and CLI verify their supported targets.
- Servers are persistent across LLM sessions. Never stop merely because a session ends.
