"""token_breakdown's doc-review block: preview calls (doc_review.py / mermaid_preview.py) against the
Miro/Confluence estimate, and measured Miro/Confluence MCP calls, from a self-made transcript.

    python3 -m unittest discover -s Tools/session-lifecycle/tests -p 'test_*.py'
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
import token_breakdown  # noqa: E402


def assistant(message_id, tool_uses):
    return {"type": "assistant", "message": {
        "id": message_id, "usage": {"input_tokens": 1000, "output_tokens": 10},
        "content": [{"type": "tool_use", "id": tool_id, "name": name, "input": tool_input}
                    for tool_id, name, tool_input in tool_uses]}}


def result(tool_id, text):
    return {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": tool_id, "content": text}]}}


class DocReviewBreakdownTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.transcript = os.path.join(self.folder, "session.jsonl")

    def tearDown(self):
        shutil.rmtree(self.folder, ignore_errors=True)

    def analyse(self, entries):
        with open(self.transcript, "w") as handle:
            handle.write("\n".join(json.dumps(entry) for entry in entries) + "\n")
        return token_breakdown.analyse(self.transcript, "session", [])

    def test_preview_calls_are_counted_by_command_and_compared(self):
        breakdown = self.analyse([
            assistant("m1", [("t1", "Bash", {"command": "python3 Tools/doc-review/doc_review.py serve a.md --port 9000"}),
                             ("t2", "Bash", {"command": "python3 Tools/mermaid-preview/mermaid_preview.py a.mmd"})]),
            result("t1", "http://127.0.0.1:9000/"), result("t2", "http://127.0.0.1:9001/"),
            assistant("m2", [("t3", "Bash", {"command": "python3 doc_review.py comments a.md && python3 doc_review.py reply a.md th1 'ok'"})]),
            result("t3", "1 open thread"),
            assistant("m3", [("t4", "Bash", {"command": "python3 doc_review.py servers"})]),
            result("t4", "none"),
            assistant("m4", []),
        ])
        doc_review = breakdown["doc_review"]
        self.assertEqual({"serve": 2, "comments": 1, "reply": 1, "servers": 1}, doc_review["commands"])
        self.assertEqual(4, doc_review["count"])
        self.assertEqual(3 + 3 + 2 + 1, doc_review["round_trips"])
        self.assertGreater(doc_review["equivalent"], doc_review["tokens"])
        saving = breakdown["savings"][token_breakdown.DOC_REVIEW_SAVING]
        # The servers call has no Miro/Confluence equivalent: not a saving use, and its cost is left out of it.
        self.assertEqual(3, saving["count"])
        self.assertGreater(saving["tokens"], doc_review["equivalent"] - doc_review["tokens"])
        self.assertLess(saving["tokens"], doc_review["equivalent"])
        self.assertIn("doc_review.py serve", breakdown["assumptions"])

    def test_miro_and_confluence_calls_are_measured_but_jira_is_not(self):
        breakdown = self.analyse([
            assistant("m1", [("t1", "mcp__miro__canvas_update_from_svg", {"svg": "x" * 400}),
                             ("t2", "mcp__plugin_engineering_atlassian__updateConfluencePage", {"body": "y" * 800}),
                             ("t3", "mcp__plugin_engineering_atlassian__getJiraIssue", {"issueIdOrKey": "MM-1"})]),
            result("t1", "ok"), result("t2", "ok"), result("t3", "z" * 4000),
            assistant("m2", []),
        ])
        measured = breakdown["doc_review"]["miro_confluence"]
        self.assertEqual(2, measured["count"])
        self.assertEqual(0, breakdown["doc_review"]["count"])
        self.assertGreater(measured["tokens"], 0)
        self.assertLess(measured["tokens"], 1000)   # the 1K-token Jira result is not counted


if __name__ == "__main__":
    unittest.main()
