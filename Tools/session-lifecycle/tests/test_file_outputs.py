"""Regression tests for filing outputs written outside the reports tree.

MR-20261016-06: a background session cannot Write into GitIgnoreReports/ once /end-session has
removed its worktree, so it writes retro.md (or meta-review outputs) to its job tmp dir and files
them with `retro --from` / `file --to MetaReviews`.

    python3 -m unittest discover -s Tools/session-lifecycle/tests -p 'test_*.py'
"""

import os
import unittest

from test_roots import FOLDER, SESSION_ID, RootTestCase

RETRO = """# Retro

## Proposed changes

| # | File | Change | Why |
|---|---|---|---|
| 1 | Rules/A.md | add a line | missed it |
| 2 | Rules/B.md | drop a line | noise |
"""


class RetroFromTests(RootTestCase):
    def setUp(self):
        super().setUp()
        self.folder = self.write_session()
        self.source = os.path.join(self.tmp, "job-tmp-retro.md")
        with open(self.source, "w") as handle:
            handle.write(RETRO)

    def test_retro_from_files_retro_and_renders_page(self):
        result = self.run_script(["retro", "--folder", FOLDER, "--from", self.source], cwd=self.host)
        self.assertEqual(result.returncode, 0, result.stderr)
        with open(os.path.join(self.folder, "retro.md")) as handle:
            self.assertEqual(handle.read(), RETRO)
        self.assertTrue(os.path.isfile(os.path.join(self.folder, "retro.html")))
        self.assertIn("filed " + os.path.join(self.folder, "retro.md"), result.stdout)
        self.assertNotIn("add a line", result.stdout)   # paths only, never the contents

    def test_retro_from_with_mark_in_one_call(self):
        result = self.run_script(["retro", "--session-id", SESSION_ID, "--from", self.source,
                                  "--mark", "2", "--status", "skipped", "--note", "not worth it"], cwd=self.host)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("#2 skipped", result.stdout)
        self.assertIn("#1 pending", result.stdout)

    def test_retro_from_missing_file_fails_clearly(self):
        missing = os.path.join(self.tmp, "nope.md")
        result = self.run_script(["retro", "--folder", FOLDER, "--from", missing], cwd=self.host)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--from file not found: " + missing, result.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.folder, "retro.md")))

    def test_retro_from_empty_file_fails_clearly(self):
        open(self.source, "w").close()
        result = self.run_script(["retro", "--folder", FOLDER, "--from", self.source], cwd=self.host)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--from file is empty", result.stderr)


class FileToTests(RootTestCase):
    def test_file_to_meta_reviews_copies_every_file(self):
        sources = []
        for name in ("2026-10-16_MetaReview.html", "2026-10-16_Tickets.md"):
            sources.append(os.path.join(self.tmp, name))
            with open(sources[-1], "w") as handle:
                handle.write(name)
        result = self.run_script(["file", "--to", "MetaReviews"] + sources, cwd=self.host)
        self.assertEqual(result.returncode, 0, result.stderr)
        target = os.path.join(self.host, "GitIgnoreReports", "MetaReviews")
        self.assertEqual(sorted(os.listdir(target)), ["2026-10-16_MetaReview.html", "2026-10-16_Tickets.md"])
        self.assertEqual(self.nested(), [])

    def test_file_with_a_missing_source_copies_nothing(self):
        present = os.path.join(self.tmp, "2026-10-16_Tickets.md")
        with open(present, "w") as handle:
            handle.write("x")
        result = self.run_script(["file", "--to", "MetaReviews", present, os.path.join(self.tmp, "nope.html")],
                                 cwd=self.host)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(os.path.exists(os.path.join(self.host, "GitIgnoreReports", "MetaReviews")))


if __name__ == "__main__":
    unittest.main()
