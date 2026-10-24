"""Category 3 (Boundary) tests for LocalDocReview -- E5, E6, E12.

E9 (port in use -> next free port) is already covered by test_server_behavior.py's
test_bindServer_whenPortIsBusy_picksNextFreePortInstead; not duplicated here.

    python3 -m unittest discover -s Tools/doc-review/tests -p 'test_*.py'
"""
import argparse
import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parents[1]
if str(TOOL_DIR) not in sys.path:
    sys.path.insert(0, str(TOOL_DIR))

import doc_review  # noqa: E402 -- note: no review_server import anywhere in this file (E6).
from sidecar_store import SidecarStore  # noqa: E402


class ConcurrentSidecarWriteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="concurrency-boundary-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.doc_path = self.tmp / "Design.md"

    def test_concurrentAddThread_fromManyThreads_appliesEveryWriteWithoutLossOrCorruption(self):
        # E5: the browser and the CLI can both write the sidecar "at the same moment" -- modeled
        # here as many threads racing to mutate the same SidecarStore at once. The fcntl lock in
        # _mutate (locking a side file, re-reading fresh, writing atomically) must mean every
        # write lands, none overwrite each other, and the file is never left half-written.
        store = SidecarStore(self.doc_path)
        write_count = 25

        def add(i: int) -> None:
            store.add_thread({"kind": "text", "file": self.doc_path.name, "quote": f"quote {i}"}, "engineer", f"text {i}")

        threads = [threading.Thread(target=add, args=(i,)) for i in range(write_count)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # A successful load() here already proves the file is valid, complete JSON -- a
        # half-written file from a lost lock would raise json.JSONDecodeError.
        data = store.load()
        self.assertEqual(len(data["threads"]), write_count, "every concurrent write must be applied, none dropped")
        ids = [thread["id"] for thread in data["threads"]]
        self.assertEqual(len(ids), len(set(ids)), "no two concurrent writers may be assigned the same thread id")


class NoServerRunningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="no-server-boundary-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.doc_path = self.tmp / "Design.md"
        self.doc_path.write_text("# Design\n\nOpen question about this part.\n")

    def test_cmdReply_withNoServerProcessRunning_appliesDirectlyToTheSidecarFile(self):
        # E6: the agent runs `reply` with no `serve` process alive. This test never constructs a
        # server or handler at all (this module doesn't even import review_server) -- it proves
        # the CLI path is a pure file read/write with no dependency on a running server.
        store = SidecarStore(self.doc_path)
        thread_id = store.add_thread(
            {"kind": "text", "file": self.doc_path.name, "quote": "Open question about this part."},
            "engineer", "what should happen here?",
        )
        store.set_status(thread_id, "ready", "engineer")

        doc_review.cmd_reply(argparse.Namespace(
            doc=str(self.doc_path), thread_id=thread_id, message="answered in the latest edit", status="addressed",
        ))

        thread = next(t for t in SidecarStore(self.doc_path).load()["threads"] if t["id"] == thread_id)
        self.assertEqual(thread["status"], "addressed", "the CLI must be able to update the sidecar with no server running")
        self.assertEqual(len(thread["replies"]), 2, "the agent's reply must be appended to the existing thread")


class SharedFolderDocsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="shared-folder-boundary-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.gdd_path = self.tmp / "Feature_GDD.md"
        self.tdd_path = self.tmp / "Feature_TDD.md"

    def test_twoDocsInSameFolder_getIndependentSidecarsNamedPerDoc(self):
        # E12: a GDD and a TDD live in the same working folder -- their comment threads must
        # never mix, and each gets its own <doc>.review.json.
        gdd_store = SidecarStore(self.gdd_path)
        tdd_store = SidecarStore(self.tdd_path)

        gdd_store.add_thread({"kind": "text", "file": self.gdd_path.name, "quote": "gdd note"}, "engineer", "gdd comment")
        tdd_store.add_thread({"kind": "text", "file": self.tdd_path.name, "quote": "tdd note"}, "engineer", "tdd comment")

        self.assertTrue((self.tmp / "Feature_GDD.md.review.json").is_file())
        self.assertTrue((self.tmp / "Feature_TDD.md.review.json").is_file())
        gdd_threads = SidecarStore(self.gdd_path).load()["threads"]
        tdd_threads = SidecarStore(self.tdd_path).load()["threads"]
        self.assertEqual(len(gdd_threads), 1, "the GDD's sidecar must only contain its own comment")
        self.assertEqual(len(tdd_threads), 1, "the TDD's sidecar must only contain its own comment")
        self.assertEqual(gdd_threads[0]["replies"][0]["text"], "gdd comment")
        self.assertEqual(tdd_threads[0]["replies"][0]["text"], "tdd comment")


if __name__ == "__main__":
    unittest.main()
