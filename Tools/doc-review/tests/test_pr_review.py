"""Batch PR replies: pr_notes.pull_threads / push_replies against a fake gh, on a self-made feature folder.

    python3 -m unittest discover -s Tools/doc-review/tests -p 'test_*.py'
"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parents[1]
if str(TOOL_DIR) not in sys.path:
    sys.path.insert(0, str(TOOL_DIR))

import pr_notes  # noqa: E402
from feature_state import create_state, update_state  # noqa: E402  (pr_notes puts feature-state on sys.path)


class PrReviewTests(unittest.TestCase):
    VIEW = {"number": 7, "title": "Add router", "url": "https://gh/pr/7", "state": "OPEN",
            "comments": [{"id": "IC_1", "author": {"login": "ann"}, "createdAt": "2026-10-02T00:00:00Z",
                          "body": "Why a router?", "url": "https://gh/pr/7#c1"}],
            "reviews": [{"id": "PRR_1", "author": {"login": "bob"}, "submittedAt": "2026-10-01T00:00:00Z",
                         "body": "Two nits", "state": "COMMENTED"},
                        {"id": "PRR_2", "author": {"login": "bob"}, "submittedAt": "2026-10-03T00:00:00Z",
                         "body": "", "state": "APPROVED"}]}
    INLINE = [{"id": 11, "user": {"login": "cy"}, "created_at": "2026-10-01T12:00:00Z", "body": "Rename this",
               "html_url": "u11", "path": "A.cs", "line": 12},
              {"id": 12, "in_reply_to_id": 11, "user": {"login": "dee"}, "created_at": "2026-10-01T13:00:00Z",
               "body": "+1", "html_url": "u12", "path": "A.cs", "line": 12}]

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.feature = self.root / "Router"
        self.feature.mkdir()
        create_state(self.feature)
        update_state(self.feature, "pr", {"phase": "V0", "number": 7}, 1)
        self.inline = list(self.INLINE)
        self.posts = []
        self.fail_on_post = None
        self._real_gh_json = pr_notes._gh_json

        def fake_gh_json(args, repo_dir):
            if args[0] == "pr":
                return self.VIEW
            if "--paginate" in args:
                return [self.inline]
            if self.fail_on_post is not None and len(self.posts) == self.fail_on_post:
                raise ValueError("gh api failed: HTTP 422")
            self.posts.append(args)
            return {"html_url": f"https://gh/posted/{len(self.posts)}"}

        pr_notes._gh_json = fake_gh_json

    def tearDown(self):
        pr_notes._gh_json = self._real_gh_json
        shutil.rmtree(self.root)

    def _draft(self):
        return json.loads(pr_notes.draft_path(self.feature, 7).read_text())

    def _set_reply(self, thread_id, reply):
        path = pr_notes.draft_path(self.feature, 7)
        draft = json.loads(path.read_text())
        next(thread for thread in draft["threads"] if thread["id"] == thread_id)["reply"] = reply
        path.write_text(json.dumps(draft))

    def test_pull_groups_inline_replies_under_their_root_and_drops_empty_reviews(self):
        path, counts = pr_notes.pull_threads(7, self.feature)
        self.assertEqual(path.name, "Router_PR7_review.json")
        threads = self._draft()["threads"]
        self.assertEqual([thread["id"] for thread in threads], ["review:PRR_1", "inline:11", "comment:IC_1"])
        self.assertEqual([c["author"] for c in threads[1]["comments"]], ["cy", "dee"])
        self.assertEqual(threads[1]["location"], "A.cs:12")
        self.assertEqual(counts, {"threads": 3, "new": 3, "awaiting": 3, "gone": 0})

    def test_pull_refuses_a_pr_not_recorded_on_the_feature(self):
        with self.assertRaises(ValueError):
            pr_notes.pull_threads(8, self.feature)
        self.assertFalse(pr_notes.draft_path(self.feature, 8).exists())

    def test_repull_keeps_replies_adds_new_threads_and_flags_vanished_ones(self):
        pr_notes.pull_threads(7, self.feature)
        self._set_reply("inline:11", "Renamed")
        self.inline = [dict(self.INLINE[1], id=13, in_reply_to_id=None, path="B.cs", line=3)]
        _, counts = pr_notes.pull_threads(7, self.feature)
        threads = {thread["id"]: thread for thread in self._draft()["threads"]}
        self.assertTrue(threads["inline:11"]["gone"])
        self.assertEqual(threads["inline:11"]["reply"], "Renamed")
        self.assertIn("inline:13", threads)
        self.assertEqual((counts["new"], counts["gone"]), (1, 1))

    def test_dry_run_sends_nothing(self):
        pr_notes.pull_threads(7, self.feature)
        self._set_reply("inline:11", "Renamed")
        pending = pr_notes.push_replies(pr_notes.draft_path(self.feature, 7), confirm=False)
        self.assertEqual([thread["id"] for thread in pending], ["inline:11"])
        self.assertEqual(self.posts, [])
        self.assertIsNone(self._draft()["threads"][1]["posted"])

    def test_confirm_posts_to_the_right_endpoints_and_repush_is_a_no_op(self):
        pr_notes.pull_threads(7, self.feature)
        self._set_reply("inline:11", "Renamed")
        self._set_reply("comment:IC_1", "It decouples the screens.")
        path = pr_notes.draft_path(self.feature, 7)
        pr_notes.push_replies(path, confirm=True)
        self.assertEqual([args[1] for args in self.posts],
                         ["repos/{owner}/{repo}/pulls/7/comments/11/replies", "repos/{owner}/{repo}/issues/7/comments"])
        self.assertEqual(self.posts[0][2:], ["-f", "body=Renamed"])
        self.assertTrue(self.posts[1][3].startswith("body=> @ann: Why a router? (https://gh/pr/7#c1)\n\nIt decouples"))
        self.assertEqual(pr_notes.push_replies(path, confirm=True), [])
        self.assertEqual(len(self.posts), 2)

    def test_first_failure_stops_the_batch_and_keeps_earlier_posts_recorded(self):
        pr_notes.pull_threads(7, self.feature)
        self._set_reply("review:PRR_1", "Fixed both")
        self._set_reply("inline:11", "Renamed")
        self.fail_on_post = 1
        with self.assertRaises(ValueError):
            pr_notes.push_replies(pr_notes.draft_path(self.feature, 7), confirm=True)
        posted = {thread["id"]: thread["posted"] for thread in self._draft()["threads"]}
        self.assertEqual(posted["review:PRR_1"]["url"], "https://gh/posted/1")
        self.assertIsNone(posted["inline:11"])


if __name__ == "__main__":
    unittest.main()
