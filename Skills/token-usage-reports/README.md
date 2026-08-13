# Token Usage Reports

Run the bundled script from the root of the project whose sessions you want to report on.

For example, generate a sanitized Markdown report for the 30 most recent sessions:

```bash
bash Skills/token-usage-reports/scripts/generate_token_report.sh \
  --agent codex \
  --scope last-30 \
  --format markdown \
  --output token-usage-report.md
```

Generate one aggregate Markdown report plus one Markdown file for each of the
30 most recent sessions:

```bash
bash ~/.codex/skills/token-usage-reports/scripts/generate_token_report.sh \
  --agent codex \
  --scope last-30 \
  --format markdown \
  --per-session \
  --output reports/
```

`--per-session` requires Markdown output and an output directory.
Each session file uses the detailed token-report layout: summary, helper
compliance, composition charts, category breakdown, turn trend, highest-cost
turns, and problem areas. Content columns remain sanitized unless
`--include-content` is explicitly supplied.

## macOS Command Presets

Run these shell scripts from anywhere within the project whose sessions you want
to report. They resolve the Git repository root and write reports beneath its
`Reports` directory. Outside a Git repository, they use the current directory.

| Command | Output |
| --- | --- |
| `~/.codex/skills/token-usage-reports/scripts/report-current.sh` | `Reports/Current`: current-session aggregate and detailed session report |
| `~/.codex/skills/token-usage-reports/scripts/report-recent-summary.sh` | `Reports/Recent`: one aggregate report for the 30 most recent sessions |
| `~/.codex/skills/token-usage-reports/scripts/report-recent-detailed.sh` | `Reports/RecentDetailed`: aggregate plus one detailed report for each of the 30 most recent sessions |
| `~/.codex/skills/token-usage-reports/scripts/report-all-detailed.sh` | `Reports/AllDetailed`: aggregate plus one detailed report for every discovered session |

The presets use Codex telemetry and never enable sensitive content. Use the
main script explicitly when another agent, JSON, date filtering, or sensitive
content is required.

The Core Rules installation also exposes the canonical tool through
`scripts/session_support`, so invoking the installed skill does not depend on
the caller's working directory. If the package is installed elsewhere, provide
its directory explicitly:

```bash
TOKEN_USAGE_SESSION_SUPPORT_ROOT=/path/to/session-support \
  bash /path/to/token-usage-reports/scripts/generate_token_report.sh \
  --scope current
```

Run the script with `--help` to see every supported option. Reports exclude prompts, responses, commands, and paths by default. Only use `--include-content` when sensitive session content is explicitly required and will be reviewed before sharing.
