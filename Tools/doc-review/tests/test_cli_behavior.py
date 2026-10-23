"""Category 2 (Behavior) tests for LocalDocReview -- U4, U6.

    python3 -m unittest discover -s Tools/doc-review/tests -p 'test_*.py'
"""
import argparse
import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parents[1]
if str(TOOL_DIR) not in sys.path:
    sys.path.insert(0, str(TOOL_DIR))

from doc_review import cmd_comments  # noqa: E402
from sidecar_store import SidecarStore  # noqa: E402

DOC_CONTENT = (
    "# Design\n"
    "\n"
    "The quick brown fox jumps over the lazy dog.\n"
    "\n"
    "## Section Two\n"
    "\n"
    "Another distinct sentence lives here for testing purposes.\n"
)


def run_comments(doc_path: Path, status: str = "all") -> dict:
    args = argparse.Namespace(doc=str(doc_path), status=status, json=True)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        cmd_comments(args)
    return json.loads(out.getvalue())


def line_of(text: str) -> int:
    return DOC_CONTENT.splitlines().index(text) + 1


class CommentsReadyFilterTests(unittest.TestCase):
    """U4: engineer marks threads Ready, agent runs `comments --status ready`."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cli-behavior-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.doc_path = self.tmp / "Design.md"
        self.doc_path.write_text(DOC_CONTENT)
        self.store = SidecarStore(self.doc_path)

    def add(self, quote: str, status: str) -> str:
        thread_id = self.store.add_thread(
            {"kind": "text", "file": self.doc_path.name, "quote": quote}, "engineer", "comment on: " + quote,
        )
        if status != "open":
            self.store.set_status(thread_id, status, "engineer")
        return thread_id

    def test_comments_filteredByReadyStatus_listsOnlyReadyThreadsResolvedToFileLine(self):
        open_quote = "The quick brown fox jumps over the lazy dog."
        ready_quote = "Another distinct sentence lives here for testing purposes."
        resolved_quote = "## Section Two"
        self.add(open_quote, "open")
        ready_id = self.add(ready_quote, "ready")
        self.add(resolved_quote, "resolved")

        result = run_comments(self.doc_path, status="ready")

        self.assertEqual(len(result["threads"]), 1, "only the ready thread must be listed, not open or resolved")
        listed = result["threads"][0]
        self.assertEqual(listed["id"], ready_id)
        self.assertEqual(listed["status"], "ready")
        self.assertEqual(listed["resolution"]["status"], "resolved",
                          "a live quote must resolve to a file:line, not be reported orphaned/ambiguous")
        self.assertEqual(listed["resolution"]["file"], self.doc_path.name)
        self.assertEqual(listed["resolution"]["line"], line_of(ready_quote),
                          "the resolved line must match where the quote actually lives in the doc")

    def test_comments_withStatusAll_listsEveryThreadRegardlessOfStatus(self):
        self.add("The quick brown fox jumps over the lazy dog.", "open")
        self.add("Another distinct sentence lives here for testing purposes.", "ready")
        self.add("## Section Two", "resolved")

        result = run_comments(self.doc_path, status="all")

        self.assertEqual(len(result["threads"]), 3, "--status all must not drop any thread")


class InlineMarkerTests(unittest.TestCase):
    """U6: a quick @CLAUDE note in the source is listed alongside sidecar threads."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cli-behavior-markers-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.doc_path = self.tmp / "Design.md"
        self.diagrams_dir = self.tmp / "Diagrams"
        self.diagrams_dir.mkdir()
        self.diagram_path = self.diagrams_dir / "flow.mmd"

    def test_comments_withInlineMarkersInDocAndDiagram_listsBothAlongsideSidecarThreads(self):
        self.doc_path.write_text(
            "# Design\n\n<!-- @CLAUDE: tighten this paragraph -->\n\nSome body text.\n"
        )
        self.diagram_path.write_text("graph TD\n  A --> B\n%% @CLAUDE: rename node A\n")
        # No sidecar file exists at all yet -- markers must still surface with zero threads.

        result = run_comments(self.doc_path, status="ready")

        self.assertEqual(result["threads"], [], "no threads exist yet -- the ready filter must find none")
        markers_by_file = {m["file"]: m for m in result["inline_markers"]}
        self.assertIn(self.doc_path.name, markers_by_file, "the doc's own inline marker must be discovered")
        self.assertEqual(markers_by_file[self.doc_path.name]["text"], "tighten this paragraph")
        diagram_rel = str(self.diagram_path.relative_to(self.tmp))
        self.assertIn(diagram_rel, markers_by_file,
                      "a diagram under Diagrams/ must be auto-discovered without being a comment anchor")
        self.assertEqual(markers_by_file[diagram_rel]["text"], "rename node A")


if __name__ == "__main__":
    unittest.main()
