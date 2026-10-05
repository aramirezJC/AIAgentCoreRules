# [FeatureName] — Progress

Resume state for the CreateFeature process. Written at every gate and by `/checkpoint`; read by
`/resume [FeatureName]`. Keep it short — it is reloaded at the start of every session.

```yaml
feature:        "[FeatureName]"
current_phase:  "1_intake"          # phase key from CreateFeature/index.md
status:         "in_progress"       # in_progress | at_gate | complete
updated_at:     ""                  # ISO timestamp of the last write
artifacts:      []                  # files in this folder the next phase needs, e.g. [FeatureName]_TDD.md
sessions:       []                  # session folder names that worked on this feature — Phase 8 reads these
sources_of_truth: []                # documents edited outside this folder, with the version last read, e.g.
                                    #   - {kind: confluence, id: "4787830785", title: "<Feature> TDD", version: 14}
                                    # /resume compares versions; update the version at every /checkpoint and gate
```

---

## Checkpoint

Where work stopped inside the current phase. Replaced (not appended) on every `/checkpoint`;
cleared when the phase's gate passes.

```yaml
checkpoint:
  saved_at:          ""
  done:              []   # steps / files completed and engineer-acknowledged this phase
  in_flight:         ""   # the step or file being worked on, and how far it got
  next:              ""   # the very next action on resume
  pending_decisions: []   # questions waiting on the engineer
  context_notes:     []   # facts learned this phase that are not yet in any artifact
```

---

## Gates Passed

One `phase_handoff` block per gate, appended in order. Never edit a past block — record a
reversal as a new note in the current checkpoint.

<!-- gate blocks are appended below this line -->
