## apply: on-demand — loaded by [[MetaRouter]]

# Bug Fix

From symptom to verified fix with a regression test. Investigation here is a means to a fix,
not a deliverable — for "should we change X" questions with no bug, use InvestigationMode.

Tag definitions: [[CoreTags]]

---

## Steps

```yaml
steps:
  1_symptom:
    - "Restate: expected vs actual, repro steps, frequency, build/platform, first-seen version. Ask only for what is missing."
  2_context:
    - "SystemIndex: Read the Systems/ entry for the suspected system — its common_gotchas first."
    - "Locate the flow: codeindex.py where/members, usages.py for callers (/uses). Breadth → /discover."
  3_hypotheses:
    - "Read the method bodies on the failing path. Every claim carries file:line."
    - "Rank 1–3 hypotheses by evidence. For each: the evidence, what would confirm it, what would rule it out."
    - "Check the cheapest confirming evidence first (one grep, one log line, one breakpoint the engineer can set)."
  4_gate_diagnosis:
    - "Present: root cause (or top hypothesis + confidence), the proposed fix, blast radius (callers affected), and the regression test."
    - "Wait for engineer confirmation. No code before this gate."
  5_fix:
    - "Load rules by what the fix touches: CodingStandards always; ResourceManagementRules for subscriptions/timers/loads; MultyStepOperationsRules for async ordering."
    - "Smallest change that removes the cause. [SURG] — no drive-by refactors; list them as follow-ups instead."
  5b_audit:   # checkpoint — do not start step 6 until it has run
    - "Run /audit on every changed file (fix, repro/debug tooling, and later the test file). Fix or report each violation."
    - "Self-review is not a substitute: /end-session flags a skipped audit as a router miss."
  6_test:
    - "Load TestingRules.md and the host project's testing setup."
    - "Write one regression test that fails without the fix and passes with it. If the bug cannot be unit-tested (timing, platform, Editor-only), write the manual repro steps instead and say why."
  7_verify:
    - "Run typecheck.py."
    - "Ask the engineer to run the test(s) in the Unity Test Runner and the repro steps; report results as given."
  8_close:
    - "Summarise: cause · fix · test · follow-ups. Offer /end-session."
```

Rule for step 3: if verification reverses an earlier hypothesis, lead with the correction
(InvestigationMode IV). A wrong root cause that reaches the fix is the most expensive failure here.

Detours: when the engineer asks for side work mid-bug (for example a repro tool or debug
command), record the lane change with the lifecycle `set --lane small_task` command before
starting it, then `set --lane bug_fix` when you return. That keeps metrics and the router check
accurate. Follow SmallTask.md for the detour, including its own /audit.

## Router check (used by /end-session)

```yaml
expected_loads:
  - "Systems/<suspected system>.md (if it exists)"
  - "Rules/CodingStandards.md"
  - "Rules/TestingRules.md + host testing setup"
  - "plus ResourceManagementRules / MultyStepOperationsRules if the fix touched them"
expected_tools: [usages.py or codeindex.py, typecheck.py, /audit]
```
