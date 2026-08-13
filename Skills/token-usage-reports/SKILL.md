---
name: token-usage-reports
description: Generate sanitized token-usage and session-telemetry reports for Codex, Claude Code, Gemini CLI, or Junie. Use when Codex needs to report current-session, recent-session, or all-session token totals; compare session/category usage; export Markdown or JSON; inspect cache, reasoning, helper, timing, or sub-agent telemetry; or produce an explicitly sensitive report containing prompts, responses, commands, and paths.
---

# Token Usage Reports

Use the bundled runner instead of parsing session files manually.

## Generate A Report

Run from the user's project directory:

```bash
bash <skill-directory>/scripts/generate_token_report.sh \
  --scope last-30 \
  --format markdown \
  --output <output-path>
```

Supported options:

- `--agent codex|claude|gemini|junie`; default comes from project configuration or `codex`.
- `--scope current|last-30|all`; default is `last-30`.
- `--format markdown|json`; default is `markdown`.
- `--output <file-or-directory>`; omit to print the report.
- `--project-config <path>` and `--sessions-root <path>` for explicit routing.
- `--since <ISO timestamp>` to restrict discovered sessions.
- `--include-content` only for Markdown reports when the user explicitly requests prompts, responses, commands, or paths.
- `--per-session` for Markdown output writes the aggregate report plus one file per selected session; it requires `--output` to name a directory.

On macOS, prefer the bundled `report-current.sh`,
`report-recent-summary.sh`, `report-recent-detailed.sh`, or
`report-all-detailed.sh` presets for common Codex reports. Within a Git repository,
presets write beneath its root-level `Reports` directory; otherwise they use the
current directory.

## Privacy Contract

- Generate sanitized reports by default.
- Do not enable `--include-content` unless explicitly requested; it can expose source, paths, identifiers, commands, or secrets.
- Warn the user that sensitive reports must be reviewed before sharing or committing.
- Do not commit generated reports unless the user asks.

## Routing

The runner resolves the portable `session-support` package in this order:

1. `TOKEN_USAGE_SESSION_SUPPORT_ROOT` when set.
2. The skill's packaged `scripts/session_support` link.
3. `Tools/session-support` in the current repository.
4. The sibling Core Rules package relative to this skill's checked-in location.

If none exists, report the missing package and the expected paths. Do not rebuild the report parser ad hoc.

## Verification And Handoff

- Confirm the runner exits successfully and the requested output exists when `--output` is used.
- Report the agent, scope, format, sanitization level, and output path.
- Mention unavailable telemetry as unavailable; do not infer missing token, context-window, reasoning, or sub-agent values.
