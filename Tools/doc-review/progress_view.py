"""Build the Progress tab's model: CreateFeature phases, their steps, and where a feature stands.

Stdlib only, no PyYAML -- the progress, task-list and index files are matched line by line, the
same way session_lifecycle.py reads them. Sources:
  - Processes/CreateFeature/index.md      phase keys, files and gate one-liners
  - Processes/CreateFeature/Phase*.md     steps = the "## " headings (minus apply/Gate/Router check)
  - <Name>_Progress.md                    current_phase, status, phase_handoff blocks, checkpoint.done
  - <Name>_TaskList.md (optional)         stages + tasks, nested under the implementation phase
"""
import re
from pathlib import Path
from typing import Dict, List, Optional

CREATE_FEATURE_DIR = Path(__file__).resolve().parents[2] / "Processes" / "CreateFeature"
IMPLEMENTATION_PHASE_KEY = "4_implementation"

PHASE_KEY_LINE = re.compile(r"^  (\d+)_(\w+):\s*$")
PHASE_FIELD_LINE = re.compile(r"^    (file|gate):\s*(.+?)\s*$")
STEP_HEADING = re.compile(r"^## (.+?)\s*$")
SKIPPED_HEADING = re.compile(r"^(apply:|Gate \d|Router check)")
STEP_KEY = re.compile(r"^(?:Sub-phase\s+(\d+[a-z])|(Step\s+\d+|Category\s+\d+))\b")
PHASE_COMPLETED_LINE = re.compile(r'^\s*phase_completed:\s*"Phase\s+(\d+)\b')
TASK_LINE = re.compile(r'^\s*-\s*\{id:\s*([^,]+),\s*status:\s*"\[(.)\]",\s*title:\s*"([^"]*)"')
STAGE_LINE = re.compile(r'^-\s*stage:\s*"([^"]*)"')
DONE_ITEM_LINE = re.compile(r'^\s{4}-\s*"(.*)"\s*$')
TASK_STATUS_BY_MARK = {"x": "done", "~": "partial", " ": "todo"}


def find_progress_file(doc_path: Path) -> Optional[Path]:
    """The first <Name>_Progress.md next to the served doc, or None if it is not a feature doc."""
    matches = sorted(doc_path.resolve().parent.glob("*_Progress.md"))
    return matches[0] if matches else None


def task_list_path(progress_path: Path) -> Path:
    return progress_path.with_name(progress_path.name[: -len("_Progress.md")] + "_TaskList.md")


def watched_paths(progress_path: Path, process_dir: Path = CREATE_FEATURE_DIR) -> List[Path]:
    """Every file the model is built from -- the tab re-renders when any of them changes."""
    candidates = [progress_path, task_list_path(progress_path), process_dir / "index.md"]
    candidates += sorted(process_dir.glob("Phase*.md"))
    return [path for path in candidates if path.is_file()]


def build_model(progress_path: Path, process_dir: Path = CREATE_FEATURE_DIR) -> Dict:
    progress_text = progress_path.read_text()
    current_key = _quoted_field(progress_text, "current_phase") or ""
    completed_numbers = {int(m.group(1)) for m in map(PHASE_COMPLETED_LINE.match, progress_text.splitlines()) if m}
    done_items = _checkpoint_done(progress_text)
    task_list = task_list_path(progress_path)
    stages = _task_stages(task_list.read_text()) if task_list.is_file() else []

    phases = []
    for phase in _index_phases(process_dir):
        completed = phase["number"] in completed_numbers
        is_current = phase["key"] == current_key
        steps = _steps(process_dir / phase["file"])
        for step in steps:
            step["done"] = completed or (is_current and _step_mentioned(step, done_items))
        phases.append(
            {
                "key": phase["key"],
                "number": phase["number"],
                "title": f"Phase {phase['number']} — {phase['name']}",
                "gate": phase["gate"],
                "completed": completed,
                "current": is_current,
                "steps": steps,
                "stages": stages if phase["key"] == IMPLEMENTATION_PHASE_KEY else [],
            }
        )

    return {
        "feature": _quoted_field(progress_text, "feature") or progress_path.stem,
        "status": _quoted_field(progress_text, "status") or "",
        "updated_at": _quoted_field(progress_text, "updated_at") or "",
        "next": _quoted_field(progress_text, "next") or "",
        "current_phase": current_key,
        "next_gate_phase": _next_gate_phase(phases),
        "phases": phases,
    }


def _next_gate_phase(phases: List[Dict]) -> Optional[str]:
    # The gate still to pass: the current phase's own gate, or -- when that block is already
    # written (status at_gate after the handoff, or a skipped phase) -- the first later phase
    # without one.
    start = next((i for i, phase in enumerate(phases) if phase["current"]), 0)
    pending = next((phase for phase in phases[start:] if not phase["completed"]), None)
    return pending["key"] if pending else None


def _index_phases(process_dir: Path) -> List[Dict]:
    phases: List[Dict] = []
    for line in (process_dir / "index.md").read_text().splitlines():
        key_match = PHASE_KEY_LINE.match(line)
        if key_match:
            name = key_match.group(2).replace("_", " ").title()
            phases.append({"key": f"{key_match.group(1)}_{key_match.group(2)}", "number": int(key_match.group(1)),
                           "name": name, "file": "", "gate": ""})
            continue
        field_match = PHASE_FIELD_LINE.match(line)
        if field_match and phases:
            value = field_match.group(2)
            phases[-1][field_match.group(1)] = value[2:] if value.startswith("./") else value
    return phases


def _steps(phase_path: Path) -> List[Dict]:
    if not phase_path.is_file():
        return []
    steps = []
    for line in phase_path.read_text().splitlines():
        heading = STEP_HEADING.match(line)
        if heading and not SKIPPED_HEADING.match(heading.group(1)):
            title = heading.group(1)
            key_match = STEP_KEY.match(title)
            key = (key_match.group(1) or key_match.group(2)) if key_match else ""
            steps.append({"title": title, "key": key})
    return steps


def _step_mentioned(step: Dict, done_items: List[str]) -> bool:
    # Approximate by design: checkpoint.done is free text, so a step counts as done when an item
    # names its key ("1a", "Step 3") or its full title after the dash.
    needles = []
    if step["key"]:
        needles.append(re.compile(r"\b" + re.escape(step["key"]) + r"\b", re.IGNORECASE))
    name = step["title"].split(" — ", 1)[-1]
    needles.append(re.compile(re.escape(name), re.IGNORECASE))
    return any(needle.search(item) for item in done_items for needle in needles)


def _checkpoint_done(progress_text: str) -> List[str]:
    items: List[str] = []
    in_done = False
    for line in progress_text.splitlines():
        if re.match(r"^\s{2}done:\s*\[\s*\]\s*$", line):
            return []
        if re.match(r"^\s{2}done:\s*$", line):
            in_done = True
            continue
        if in_done:
            item = DONE_ITEM_LINE.match(line)
            if not item:
                break
            items.append(item.group(1))
    return items


def _task_stages(task_list_text: str) -> List[Dict]:
    stages: List[Dict] = []
    for line in task_list_text.splitlines():
        stage = STAGE_LINE.match(line)
        if stage:
            stages.append({"title": stage.group(1).strip(), "tasks": []})
            continue
        task = TASK_LINE.match(line)
        if task and stages:
            stages[-1]["tasks"].append(
                {"id": task.group(1).strip(), "title": task.group(3).strip(),
                 "status": TASK_STATUS_BY_MARK.get(task.group(2), "todo")}
            )
    return stages


def _quoted_field(text: str, field: str) -> Optional[str]:
    match = re.search(r'^\s*' + re.escape(field) + r':\s*"([^"]*)"', text, re.MULTILINE)
    return match.group(1) if match else None
