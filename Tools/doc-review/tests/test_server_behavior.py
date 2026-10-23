"""Category 2 (Behavior) tests for LocalDocReview -- U1, U2, U3, U5.

U2/U3's defined solution is the in-page comment UI (popover / diagram-node click) which is V1
scope and not implemented yet (see LocalDocReview_Progress.md). These tests exercise the one
layer of U2/U3 that *is* built in V0: the `/api/comment` handler the future UI will call. U5's
agent half runs through doc_review.cmd_reply exactly as the CLI does; its engineer half runs
through the live `/api/status` endpoint.

    python3 -m unittest discover -s Tools/doc-review/tests -p 'test_*.py'
"""
import argparse
import functools
import http.server
import json
import shutil
import socket
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parents[1]
if str(TOOL_DIR) not in sys.path:
    sys.path.insert(0, str(TOOL_DIR))

import doc_review  # noqa: E402
from review_server import ReviewRequestHandler, _bind_server, build_page  # noqa: E402
from sidecar_store import SidecarStore  # noqa: E402


def _request(method: str, url: str, body: dict = None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                  headers={"Content-Type": "application/json"} if data else {})
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


class LiveServerTestCase(unittest.TestCase):
    """Runs the real ReviewRequestHandler on a background thread, as serve_doc() would."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="server-behavior-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.doc_path = self.tmp / "Doc.md"
        self.doc_path.write_text("# Doc\n\nSome text to comment on.\n")
        self.store = SidecarStore(self.doc_path)

    def start_server(self, doc_paths):
        handler_factory = functools.partial(ReviewRequestHandler, doc_paths=doc_paths, store=self.store)
        httpd = _bind_server(handler_factory, port=None)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        # addCleanup runs LIFO: shutdown() unblocks serve_forever(), then join() waits for the
        # thread to actually exit, then server_close() releases the listening socket.
        self.addCleanup(httpd.server_close)
        self.addCleanup(thread.join, timeout=5)
        self.addCleanup(httpd.shutdown)
        port = httpd.server_address[1]
        return f"http://127.0.0.1:{port}"


class ServeTabsAndPortFallbackTests(LiveServerTestCase):
    def test_serveDoc_withDocAndDiagrams_buildsOneTabPerFile(self):
        diagram_path = self.tmp / "flow.mmd"
        diagram_path.write_text("graph TD\n  A --> B\n")

        page = build_page([self.doc_path, diagram_path], live=True)

        # data-i="N" is unique to each <button class="tab" ...> -- unlike counting 'class="tab'
        # itself, it isn't also matched by the unrelated <div class="tabs"> wrapper.
        self.assertEqual(page.count('data-i="'), 2, "one tab button per input file, doc + diagram")
        self.assertIn(">Doc<", page, "the doc's tab must be titled after its stem")
        self.assertIn(">flow<", page, "the diagram's tab must be titled after its stem")

    def test_bindServer_whenPortIsBusy_picksNextFreePortInstead(self):
        occupied = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.addCleanup(occupied.close)
        occupied.bind(("127.0.0.1", 0))
        occupied.listen(1)
        busy_port = occupied.getsockname()[1]
        handler_factory = functools.partial(ReviewRequestHandler, doc_paths=[self.doc_path], store=self.store)

        httpd = _bind_server(handler_factory, port=busy_port)
        self.addCleanup(httpd.server_close)

        self.assertNotEqual(httpd.server_address[1], busy_port,
                             "a busy port must not be reused -- a free one must be picked instead")


class CommentApiTests(LiveServerTestCase):
    def test_postApiComment_withTextSelection_createsOpenThreadWithTextAnchor(self):
        base_url = self.start_server([self.doc_path])
        anchor = {
            "kind": "text",
            "file": self.doc_path.name,
            "quote": "Some text to comment on.",
            "prefix": "",
            "suffix": "",
            "heading_path": ["Doc"],
        }

        status, body = _request("POST", f"{base_url}/api/comment", {"anchor": anchor, "text": "please expand this"})

        self.assertEqual(status, 200, "a well-formed comment post must succeed")
        self.assertIn("id", body, "the handler must return the new thread's id")
        thread = self.store.load()["threads"][0]
        self.assertEqual(thread["status"], "open", "a freshly created thread must start open")
        self.assertEqual(thread["anchor"], anchor, "the text anchor must be saved exactly as posted")
        self.assertEqual(thread["replies"][0]["text"], "please expand this")

    def test_postApiComment_onDiagramNode_createsThreadWithDiagramAnchor(self):
        diagram_path = self.tmp / "flow.mmd"
        diagram_path.write_text("graph TD\n  A[Start] --> B[End]\n")
        base_url = self.start_server([self.doc_path, diagram_path])
        anchor = {
            "kind": "diagram",
            "file": diagram_path.name,
            "element_id": "A",
            "source_id": "A",
            "label": "Start",
            "point": {"x": 12.5, "y": 48.0},
        }

        status, body = _request("POST", f"{base_url}/api/comment", {"anchor": anchor, "text": "rename this node"})

        self.assertEqual(status, 200)
        thread = self.store.load()["threads"][0]
        self.assertEqual(thread["anchor"]["kind"], "diagram", "a diagram click must save a diagram-kind anchor")
        self.assertEqual(thread["anchor"]["source_id"], "A")
        self.assertEqual(thread["anchor"]["label"], "Start")
        self.assertEqual(thread["anchor"]["point"], {"x": 12.5, "y": 48.0})

    def test_postApiComment_withoutAnchor_returns400AndCreatesNoThread(self):
        base_url = self.start_server([self.doc_path])

        status, body = _request("POST", f"{base_url}/api/comment", {"text": "missing anchor"})

        self.assertEqual(status, 400, "a comment with no anchor must be rejected, not silently accepted")
        self.assertEqual(self.store.load()["threads"], [], "a rejected comment must not create a thread")


class AgentReplyAndEngineerResolveTests(LiveServerTestCase):
    def test_agentReply_setsAddressedThenEngineerResolves_stateReflectsBothTransitions(self):
        anchor = {"kind": "text", "file": self.doc_path.name, "quote": "Some text to comment on."}
        thread_id = self.store.add_thread(anchor, "engineer", "what does this mean?")
        self.store.set_status(thread_id, "ready", "engineer")
        base_url = self.start_server([self.doc_path])

        # Act 1 -- the agent edits the source and replies, exactly as doc_review.py's CLI does.
        doc_review.cmd_reply(argparse.Namespace(
            doc=str(self.doc_path), thread_id=thread_id, message="clarified in the latest edit", status="addressed",
        ))

        status, state = _request("GET", f"{base_url}/api/state")
        self.assertEqual(status, 200)
        thread_after_reply = next(t for t in state["threads"] if t["id"] == thread_id)
        self.assertEqual(thread_after_reply["status"], "addressed",
                          "an agent reply with --status addressed must be visible to the live page")
        self.assertEqual(len(thread_after_reply["replies"]), 2, "the agent's reply must be appended, not replace the thread")

        # Act 2 -- the engineer reviews the reply in the browser and resolves the thread.
        status, body = _request("POST", f"{base_url}/api/status", {"id": thread_id, "status": "resolved"})
        self.assertEqual(status, 200)
        self.assertTrue(body.get("ok"))

        status, state = _request("GET", f"{base_url}/api/state")
        thread_after_resolve = next(t for t in state["threads"] if t["id"] == thread_id)
        self.assertEqual(thread_after_resolve["status"], "resolved",
                          "the engineer's resolve must be reflected in the next state poll")


if __name__ == "__main__":
    unittest.main()
