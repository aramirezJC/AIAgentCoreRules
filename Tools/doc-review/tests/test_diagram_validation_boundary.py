"""Category 3 (Boundary) test for LocalDocReview -- E8.

"Agent edit breaks a diagram (parse error)": the tab shows the mermaid error (browser-side --
see LocalDocReviewV1's tests/smoke/review_ui_smoke.js for that half, E17), the CLI must still
list its comments regardless, and the agent's `reply` must refuse to mark a thread addressed
until mermaid-cli validates the edited diagram.

subprocess.run (the actual `npx @mermaid-js/mermaid-cli` call) is mocked -- this is a unit test
for doc_review.py's validation gate, not an integration test of mermaid-cli/npm/node, which
would be slow and need network/npm available.

    python3 -m unittest discover -s Tools/doc-review/tests -p 'test_*.py'
"""
import argparse
import contextlib
import io
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

TOOL_DIR = Path(__file__).resolve().parents[1]
if str(TOOL_DIR) not in sys.path:
    sys.path.insert(0, str(TOOL_DIR))

import doc_review  # noqa: E402
from sidecar_store import SidecarStore  # noqa: E402


def mmdc_result(returncode: int, stderr: str = "") -> Mock:
    return Mock(returncode=returncode, stdout="", stderr=stderr)


class DiagramValidationGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="diagram-validation-boundary-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.diagram_path = self.tmp / "flow.mmd"
        self.diagram_path.write_text("graph TD\n  A[Start] --> B[End]\n")
        self.store = SidecarStore(self.diagram_path)
        anchor = {"kind": "diagram", "file": self.diagram_path.name, "source_id": "A", "label": "Start"}
        self.thread_id = self.store.add_thread(anchor, "engineer", "rename this node")
        self.store.set_status(self.thread_id, "ready", "engineer")

    def reply_args(self) -> argparse.Namespace:
        return argparse.Namespace(
            doc=str(self.diagram_path), thread_id=self.thread_id, message="renamed as requested", status="addressed",
        )

    def test_cmdReply_whenMermaidValidationFails_blocksAddressedAndExits(self):
        with patch("doc_review.subprocess.run", return_value=mmdc_result(1, "Parse error on line 2")):
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as ctx:
                    doc_review.cmd_reply(self.reply_args())

        self.assertEqual(ctx.exception.code, 1, "a failed validation must exit non-zero, not silently continue")
        self.assertIn("failed mermaid validation", stderr.getvalue())
        thread = self.store.load()["threads"][0]
        self.assertEqual(thread["status"], "ready", "status must stay unchanged when validation blocks the reply")
        self.assertEqual(len(thread["replies"]), 1, "no reply may be appended when validation blocks the transition")

    def test_cmdReply_whenMermaidValidationFailsToRun_blocksAddressedAndExits(self):
        # mmdc itself could not be launched (e.g. npx/node missing) -- must still block, not crash
        # with an unrelated traceback.
        with patch("doc_review.subprocess.run", side_effect=OSError("npx not found")):
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as ctx:
                    doc_review.cmd_reply(self.reply_args())

        self.assertEqual(ctx.exception.code, 1)
        self.assertIn("could not run mermaid-cli", stderr.getvalue())
        thread = self.store.load()["threads"][0]
        self.assertEqual(thread["status"], "ready")

    def test_cmdReply_whenMermaidValidationPasses_appliesReplyAndSetsAddressed(self):
        with patch("doc_review.subprocess.run", return_value=mmdc_result(0)):
            doc_review.cmd_reply(self.reply_args())

        thread = self.store.load()["threads"][0]
        self.assertEqual(thread["status"], "addressed", "a passing validation must allow the addressed transition")
        self.assertEqual(len(thread["replies"]), 2)

    def test_cmdComments_withUnparsableDiagram_stillListsItsThreadResolvedToFileLine(self):
        # The diagram is broken mermaid syntax (unterminated bracket) -- but comments listing
        # only greps the live text for source_id/label, it never invokes mermaid-cli, so a
        # broken diagram must not stop the thread from being listed.
        self.diagram_path.write_text("graph TD\n  A[Unterminated --> B[End]\n")

        result = self._run_comments()

        self.assertEqual(len(result["threads"]), 1, "comments must still list the thread despite the broken diagram")
        listed = result["threads"][0]
        self.assertEqual(listed["resolution"]["status"], "resolved")
        self.assertEqual(listed["resolution"]["line"], 2)

    def _run_comments(self) -> dict:
        import json
        args = argparse.Namespace(doc=str(self.diagram_path), status="all", json=True)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            doc_review.cmd_comments(args)
        return json.loads(out.getvalue())


if __name__ == "__main__":
    unittest.main()
