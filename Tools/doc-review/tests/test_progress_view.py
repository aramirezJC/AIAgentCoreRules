"""Progress tab tests: progress_view.py's model (phases, steps, gate still to pass, task list) built
from a self-made CreateFeature process folder, plus the server's auto-detection of the tab.

    python3 -m unittest discover -s Tools/doc-review/tests -p 'test_*.py'
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parents[1]
if str(TOOL_DIR) not in sys.path:
    sys.path.insert(0, str(TOOL_DIR))

import review_server  # noqa: E402
from progress_view import build_model, find_progress_file, watched_paths  # noqa: E402

INDEX_MD = """# CreateFeature

```yaml
phases:
  1_intake:
    file: ./Phase1_Intake.md
    goal: Intake goal
    gate: Intake gate text

  2_discovery:
    file: ./Phase2_Discovery.md
    goal: Discovery goal
    gate: Discovery gate text

  3_design:
    file: ./Phase3_Design.md
    gate: Design gate text

  4_implementation:
    file: ./Phase4_Implementation.md
    gate: Implementation gate text
```
"""

PHASE_FILES = {
    "Phase1_Intake.md": "## apply: on-demand\n## Sub-phase 1a — GDD Conversion\n### Section: Objective\n"
                        "## Sub-phase 1b — TDD Section-by-Section\n## Gate 1 — Intake Complete\n"
                        "## Router check (used by /end-session)\n",
    "Phase2_Discovery.md": "## Load Rules\n## Explore the Codebase\n## Gate 2 — Discovery Report\n",
    "Phase3_Design.md": "## Step 1 — Design Proposal\n## Step 2 — Architecture Diagrams\n## Gate 3 — Design Approved\n",
    "Phase4_Implementation.md": "## Per-File Checklist\n## Gate 4 — Implementation Complete\n",
}

PROGRESS_MD = """# Demo — Progress

```yaml
feature:        "Demo"
current_phase:  "{current}"
status:         "in_progress"
updated_at:     "2026-10-26T10:00"
```

## Checkpoint

```yaml
checkpoint:
  done:
{done}
  in_flight: "none"
  next: "Do the next thing"
```

## Gates Passed

{gates}
"""

TASK_LIST_MD = """```yaml
- stage: "V1 — Stage one"
  tasks:
    - {id: 1, status: "[x]", title: "First",  task: "a"}
    - {id: 2, status: "[~]", title: "Second", task: "b"}
    - {id: 3, status: "[ ]", title: "Third",  task: "c"}
```
"""


def _gate_block(label):
    return f'```yaml\nphase_handoff:\n  phase_completed:   "{label}"\n  open_items: []\n```\n'


class ProgressViewTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.process_dir = self.tmp / "CreateFeature"
        self.process_dir.mkdir()
        (self.process_dir / "index.md").write_text(INDEX_MD)
        for name, text in PHASE_FILES.items():
            (self.process_dir / name).write_text(text)
        self.feature_dir = self.tmp / "Demo"
        self.feature_dir.mkdir()
        self.doc_path = self.feature_dir / "Demo_TDD.md"
        self.doc_path.write_text("# Demo TDD\n")
        self.progress_path = self.feature_dir / "Demo_Progress.md"

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def write_progress(self, current, done=(), gates=()):
        done_text = "\n".join(f'    - "{item}"' for item in done)
        text = PROGRESS_MD.format(current=current, done=done_text, gates="\n".join(_gate_block(g) for g in gates))
        text = text.replace("  done:\n\n", "  done: []\n")  # no items -> the template's "done: []" form
        self.progress_path.write_text(text)

    def model(self):
        return build_model(self.progress_path, self.process_dir)

    def phase(self, model, key):
        return next(phase for phase in model["phases"] if phase["key"] == key)


class BuildModelTests(ProgressViewTestBase):
    def test_phases_come_from_index_with_their_gates(self):
        self.write_progress("1_intake")
        model = self.model()
        self.assertEqual([p["key"] for p in model["phases"]], ["1_intake", "2_discovery", "3_design", "4_implementation"])
        self.assertEqual(self.phase(model, "2_discovery")["title"], "Phase 2 — Discovery")
        self.assertEqual(self.phase(model, "2_discovery")["gate"], "Discovery gate text")

    def test_steps_skip_apply_gate_router_and_subsections(self):
        self.write_progress("1_intake")
        titles = [s["title"] for s in self.phase(self.model(), "1_intake")["steps"]]
        self.assertEqual(titles, ["Sub-phase 1a — GDD Conversion", "Sub-phase 1b — TDD Section-by-Section"])

    def test_completed_phases_are_those_with_a_handoff_block_and_all_their_steps_are_done(self):
        self.write_progress("3_design", gates=["Phase 1 — Intake", "Phase 2 — Discovery"])
        model = self.model()
        self.assertTrue(self.phase(model, "1_intake")["completed"])
        self.assertTrue(all(s["done"] for s in self.phase(model, "2_discovery")["steps"]))
        self.assertFalse(self.phase(model, "3_design")["completed"])
        self.assertTrue(self.phase(model, "3_design")["current"])

    def test_current_phase_steps_are_checked_from_checkpoint_done_by_key_or_name(self):
        self.write_progress("3_design", done=["Step 1 drafted and approved"])
        steps = self.phase(self.model(), "3_design")["steps"]
        self.assertEqual([s["done"] for s in steps], [True, False])
        self.write_progress("3_design", done=["Architecture diagrams rendered"])
        steps = self.phase(self.model(), "3_design")["steps"]
        self.assertEqual([s["done"] for s in steps], [False, True])

    def test_checkpoint_done_does_not_check_steps_of_other_unfinished_phases(self):
        self.write_progress("1_intake", done=["Step 1 of something"])
        self.assertFalse(any(s["done"] for s in self.phase(self.model(), "3_design")["steps"]))

    def test_empty_done_list_checks_nothing(self):
        self.write_progress("1_intake")
        self.assertFalse(any(s["done"] for s in self.phase(self.model(), "1_intake")["steps"]))

    def test_next_gate_is_the_current_phase_until_its_handoff_is_written(self):
        self.write_progress("2_discovery", gates=["Phase 1 — Intake"])
        self.assertEqual(self.model()["next_gate_phase"], "2_discovery")
        self.write_progress("2_discovery", gates=["Phase 1 — Intake", "Phase 2 — Discovery"])
        self.assertEqual(self.model()["next_gate_phase"], "3_design")

    def test_next_gate_is_none_when_every_phase_is_complete(self):
        self.write_progress("4_implementation", gates=[f"Phase {n} — X" for n in range(1, 5)])
        self.assertIsNone(self.model()["next_gate_phase"])

    def test_task_list_is_nested_under_implementation_only(self):
        self.write_progress("1_intake")
        (self.feature_dir / "Demo_TaskList.md").write_text(TASK_LIST_MD)
        model = self.model()
        stages = self.phase(model, "4_implementation")["stages"]
        self.assertEqual(stages[0]["title"], "V1 — Stage one")
        self.assertEqual([t["status"] for t in stages[0]["tasks"]], ["done", "partial", "todo"])
        self.assertEqual(self.phase(model, "1_intake")["stages"], [])

    def test_header_fields(self):
        self.write_progress("1_intake")
        model = self.model()
        self.assertEqual((model["feature"], model["status"], model["next"]), ("Demo", "in_progress", "Do the next thing"))


class DetectionTests(ProgressViewTestBase):
    def test_find_progress_file_next_to_the_doc(self):
        self.assertIsNone(find_progress_file(self.doc_path))
        self.write_progress("1_intake")
        self.assertEqual(find_progress_file(self.doc_path), self.progress_path.resolve())

    def test_watched_paths_include_task_list_and_process_files(self):
        self.write_progress("1_intake")
        (self.feature_dir / "Demo_TaskList.md").write_text(TASK_LIST_MD)
        names = {path.name for path in watched_paths(self.progress_path, self.process_dir)}
        self.assertTrue({"Demo_Progress.md", "Demo_TaskList.md", "index.md", "Phase3_Design.md"} <= names)


class ServerTabTests(ProgressViewTestBase):
    def test_no_progress_tab_without_a_progress_file(self):
        tabs = review_server._tabs([self.doc_path])
        self.assertEqual([t["kind"] for t in tabs], ["md"])

    def test_progress_tab_is_first_with_a_json_source_and_its_own_mtime_key(self):
        self.write_progress("1_intake")
        tabs = review_server._tabs([self.doc_path, self.progress_path])
        self.assertEqual([t["kind"] for t in tabs], ["progress", "md", "md"])
        self.assertEqual([t["id"] for t in tabs], ["d0", "d1", "d2"])
        mtimes = review_server._collect_mtimes(tabs)
        self.assertEqual(len(mtimes), 3)  # the md tab of Progress.md and the Progress tab do not collide
        source = json.loads(review_server._collect_sources(tabs)[tabs[0]["id"]])
        self.assertEqual(source["feature"], "Demo")

    def test_progress_tab_file_key_does_not_shadow_the_progress_md_tab(self):
        self.write_progress("1_intake")
        tabs = review_server._tabs([self.doc_path, self.progress_path])
        # static/*.js resolve anchor.file with find(), so the first tab with a matching file wins.
        first_match = next(t for t in tabs if t["file"] == tabs[2]["file"])
        self.assertEqual(first_match["kind"], "md")

    def test_progress_tab_mtime_follows_the_newest_watched_file(self):
        self.write_progress("1_intake")
        tab = review_server._tabs([self.doc_path])[0]
        task_list = self.feature_dir / "Demo_TaskList.md"
        task_list.write_text(TASK_LIST_MD)
        future = self.progress_path.stat().st_mtime + 100
        os.utime(task_list, (future, future))
        self.assertEqual(review_server._tab_mtime(tab), future)

    def test_page_has_progress_panel(self):
        self.write_progress("1_intake")
        page = review_server.build_page([self.doc_path], live=False)
        self.assertIn('class="progress-view"', page)
        self.assertIn(">Progress</button>", page)


if __name__ == "__main__":
    unittest.main()
