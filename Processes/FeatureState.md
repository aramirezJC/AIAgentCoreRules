# Shared feature-state protocol

## Authoritative feature state

`<feature-directory>/state.json` is authoritative. `<Name>_Progress.md` is a generated
human-readable projection, never an agent editing target. Any references below to editing
progress, its header, checkpoint, or gate blocks mean updating those logical fields through
the tool, not editing Markdown or JSON directly. This storage protocol supersedes legacy
Markdown-writing instructions and examples below.

Run the shared CLI from the project root, resolving `<state-tool>` to
`Tools/feature-state/feature_state.py` under AIAgentCoreRules:

- Read only the needed data: `python3 <state-tool> get <feature-directory> --section checkpoint`
  (omit `--section` for operational state; `legacy_notes` are excluded by default).
  Use `--section legacy_notes` or `--include-legacy` only when historical raw text is needed.
  Read the current `revision`
  before each mutation.
- Write an exact JSON payload to a temporary file, then run
  `python3 <state-tool> <operation> <feature-directory> --payload <file> --revision <N>`.
  A revision conflict means reread and reconcile; never blindly retry old values.
- Existing Markdown without state: report migration required. Run `migrate <feature-directory>`
  for a dry run; apply explicitly with `--apply` only within an authorized migration.
  Never silently convert or recreate an existing feature.
- Session membership is a `sessions` list update through `checkpoint`; preserve existing
  entries and deduplicate by session id8. Do not invent unavailable session metrics.
- Ordinary checkpoint updates may include `checkpoint`, `step_status`, `tdd_sections`,
  `artifacts`, `sources_of_truth`, `sessions`, and active `status`. Preserve fields not being
  changed. Checkpoint content follows the process and engineer acknowledgments below.
- Gates use `gate` with `phase_completed`, `gate_confirmed_by`, `next_phase` and the handoff
  details. `phase_completed` must match the current phase; `next_phase` must be the exact
  next numbered phase. Phase 8 omits `next_phase` and completes the feature.
  Call only after explicit engineer approval; never rewrite or duplicate prior gates.
- PR linkage uses `pr` with `{"phase":"V0","number":123}`. Batch updates use `batch` with
  `{"task_id":"T1","value":{...}}`; preserve the complete existing batch value.
- Task status uses `task` with `id` and `status` (`todo`, `partial`, `done`), retaining task
  metadata. The payload may also include `title` (and other task fields); it is merged into the
  existing entry by `id`, never replacing the whole task list. There is no delete: retiring a
  task-list row means repurposing its id for new work (new `title`/`status`), not removing it.
  Artifact roles use `artifact` with `role` and a feature-relative `path`.
- Each successful mutation regenerates Progress Markdown. Do not parse it back into state.

Lifecycle skills retain all engineer approvals. Pass payloads as JSON objects, never inline shell substitutions.
