## apply: on-demand — loaded by [[CreateFeature/index]]

# Phase 1 — Intake

Goal: Convert the GDD into a complete TDD and supporting documents. Work section by section with the engineer. Do not skip or summarize — each TDD section must be explicitly addressed before moving to the next.

Output files produced by this phase:
```yaml
outputs:
  - "[FeatureName]_TDD.md        — filled from Templates/TDD_Template.md"
  - "[FeatureName]_TaskList.md   — ordered actionable items from the Development Plan"
  - "[FeatureName]_UseCases.md   — use cases and edge cases table"
  - "[FeatureName]_GDD.md        — AI-friendly version of the source GDD (if provided)"
```

---

## Sub-phase 1a — GDD Conversion

If the engineer provides a GDD (PDF or document):

```yaml
gdd_conversion:
  - Read the full document.
  - Convert to clean Markdown preserving all section headings, intent, and detail.
  - Do not summarize, condense, or omit any section.
  - Save as [FeatureName]_GDD.md in the feature's working folder.
  - Confirm the conversion with the engineer before proceeding.
```

If no GDD exists, skip to 1b and gather information through direct questions.

---

## Sub-phase 1b — TDD Section-by-Section

Work through each TDD section with the engineer. Do not proceed to the next section until the current one is agreed upon. Fill the TDD as you go.

---

### Section: Objective

Ask:
> "Describe the feature in 2–3 sentences. What problem does it solve and what triggers it?"

```yaml
objective_checks:
  - Is the goal clear and measurable?
  - Does it describe what the feature does, not how?
  - Would a new engineer understand what this feature is from this alone?
```

---

### Section: Architecture

Ask:
> "Do you have an architecture diagram? If not, describe the high-level components and how they interact."

```yaml
architecture_checks:
  - Are the main classes/systems named?
  - Are the data flow and ownership clear?
  - Note: detailed class design happens in Phase 3 — capture intent here, not implementation.
```

---

### Section: Related Documentation

Ask:
> "Are there Jira tickets, Confluence pages, GDDs, or prior TDDs to link here?"

Collect all links. Leave blank if none — do not skip the section.

---

### Section: Development Plan — Stage Levels

Ask:
> "What are the development stages for this feature? (e.g. V0 = core loop, V1 = polish, V2 = monetisation)"

For each stage, collect:

```yaml
per_stage:
  name:              "e.g. V0 — Core Loop"
  level_of_effort:   "T-shirt size (S/M/L/XL) + estimated days"
  tasks:             []   # list of concrete tasks for this stage
  assignee:          "Name of engineer responsible"
```

Populate the task table. Each task row: Task | Assignee | Status (unchecked `[ ]` by default).

Add as many stages as needed. The "Final Touches" stage is always included — see below.

---

### Section: Development Plan — Final Touches

This stage is **mandatory** for every feature. The following tasks are always included:

```yaml
final_touches_standard_tasks:
  - Implement and validate data reconciliation strategy
  - Implement CS Gifting Strategy
  - Add BI calls
  - Add Unit Tests
  - Implement design and support tools
  - Implement QA Debug functionality
  - Backport Systems to RST
```

Ask the engineer for the assignee and level of effort estimate (default: at least 5 days).

---

### Section: Design and Support Tools

Ask:
> "What tools or mechanisms will this feature need long term? Consider: Airtable imports, JCL vs Local testing, Disney snapshot routing, Unity asset configuration, debug menus."

Collect as a bullet list.

---

### Section: Risks

Ask:
> "What could go wrong during development or at runtime? For each risk, what is the resolution, amortization, or workaround?"

```yaml
risk_format:
  - risk: "description"
    mitigation: "resolution or workaround"
```

At minimum identify: timeline risk, integration risk, and data integrity risk.

---

### Section: Data Reconciliation Strategy

Ask:
> "How will this feature handle offline/online state conflicts? What wins — local or server data? Is there a merge strategy?"

**This section cannot be left blank.** If the strategy is not yet decided, explicitly mark it as `TBD` and log it as an open item in Gate 1.

---

### Section: CS Strategy

Ask:
> "How will Customer Support gift or reset this feature for affected players?"

**This section cannot be left blank.** If the strategy is not yet decided, mark as `TBD` and log as an open item.

---

### Section: Edge Cases

Work through the GDD and development stages to surface edge cases. Use this as a starting set and expand with the engineer:

```yaml
edge_case_prompts:
  - "What happens if the feature expires while the player is mid-action?"
  - "What happens if the player closes the game during a progress save point?"
  - "What happens if the server returns an unexpected state on boot?"
  - "What happens if two conflicting events are active simultaneously?"
  - "What happens if a reward has already been claimed but the flag is missing?"
```

For each edge case identified, fill a table row: `# | Description | Solution`.

If the solution is unknown, mark it `TBD` and log as an open item.

---

### Section: Other Notes

Ask:
> "Is there anything important that doesn't fit cleanly into the other sections?"

Optional — leave blank if nothing applies.

---

### Section: Future Work

Ask:
> "What could be added to this system in future iterations that is explicitly out of scope now?"

Capture as a bullet list. This sets expectations and prevents scope creep during implementation.

---

## Sub-phase 1c — Consistency and Gap Review

After completing all TDD sections, evaluate the feature against the existing project:

```yaml
consistency_checks:
  - Does this feature conflict with or duplicate any existing system?
  - Are there dependencies on systems that do not yet exist?
  - Is the Data Reconciliation Strategy consistent with how similar features handle it?
  - Is the CS Strategy consistent with the project's gifting patterns?
  - Are the Final Touches tasks achievable within the scope of the development plan?
  - Are all edge cases in the table given a solution (or explicitly TBD)?
  - Are the BI calls for this feature identified, even if not yet implemented?
```

Present findings as a numbered list. Discuss each gap with the engineer until resolved or explicitly deferred with an owner and follow-up date.

---

## Sub-phase 1d — Document Generation

With all TDD sections complete and reviewed, produce the output documents:

**`[FeatureName]_TDD.md`** — fill `Templates/TDD_Template.md` with all gathered content. Set version to `1.0.0`.

**`[FeatureName]_TaskList.md`** — extract all tasks from all Development Plan stages in order:

```yaml
task_list_format:
  - stage: "V0 — Core Loop"
    tasks:
      - task: "Task description"
        assignee: "Name"
        status: "[ ]"
```

**`[FeatureName]_UseCases.md`** — compile all edge cases from the TDD plus any additional scenarios identified during 1b/1c:

```yaml
use_case_format:
  - id: 1
    description: "Scenario description"
    solution: "How it is handled (or TBD)"
```

---

## Gate 1 — Intake Complete

Present the following summary to the engineer:

```yaml
gate_1_summary:
  feature_name:          ""
  owning_system:         ""
  tdd_location:          ""
  task_count:            0
  stage_count:           0
  use_case_count:        0
  tbd_items:             []   # sections or edge cases marked TBD — must have owners
  open_items:            []   # unresolved gaps from 1c
```

**Wait for engineer confirmation before loading Phase 2.**
All `tbd_items` must have an owner before the gate is cleared — unowned TBDs block progression.
