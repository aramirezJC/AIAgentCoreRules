"""Performance tab tests: perf_view.py's model (newest-first sessions, overview statistics, active
session, uncompiled sessions) built from self-made session folders, plus the server's tab wiring.

    python3 -m unittest discover -s Tools/doc-review/tests -p 'test_*.py'
"""
import json
import os
import shutil
import statistics
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

TOOL_DIR = Path(__file__).resolve().parents[1]
if str(TOOL_DIR) not in sys.path:
    sys.path.insert(0, str(TOOL_DIR))

import perf_view  # noqa: E402
import review_server  # noqa: E402


def breakdown(total, ad_hoc, calls=10):
    return {"estimated": True, "total": total, "calls": calls, "standardized": total // 10,
            "categories": {"Runnable tools": total // 10, "Ad-hoc tool calls": ad_hoc,
                           "Conversation & base context": total - total // 10 - ad_hoc}}


class PerfViewTestCase(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp()) / "GitIgnoreReports" / "Sessions"
        self.root.mkdir(parents=True)
        self.doc = self.root.parent.parent / "doc.md"
        self.doc.write_text("# Doc\n")
        self.env = mock.patch.dict(os.environ, {"SESSION_REPORTS_ROOT": str(self.root)})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.root.parent.parent, ignore_errors=True)

    def write_session(self, folder, session_id, started_at, age_seconds=0, **state):
        path = self.root / folder / "session.json"
        path.parent.mkdir()
        path.write_text(json.dumps(dict(session_id=session_id, started_at=started_at, **state)))
        stamp = time.time() - age_seconds
        os.utime(path, (stamp, stamp))
        return path

    def write_three(self):
        self.write_session("2026-10-01_0900_old", "aaaaaaaa1", "2026-10-01T09:00:00-07:00", age_seconds=86400,
                           title="Old", lane="bug_fix", ended_at="2026-10-01T10:00:00-07:00",
                           breakdown=breakdown(1000, 200))
        self.write_session("2026-10-03_0900_live", "cccccccc3", "2026-10-03T09:00:00-07:00",
                           title="Live", lane="small_task", breakdown=breakdown(4000, 1000))
        self.write_session("2026-10-02_0900_none", "bbbbbbbb2", "2026-10-02T09:00:00-07:00", age_seconds=86400,
                           title="Never compiled", breakdown={"error": "no transcript"})


class TestModel(PerfViewTestCase):
    def test_sessions_are_newest_first(self):
        self.write_three()
        model = perf_view.build_model(self.root)
        self.assertEqual(["cccccccc", "bbbbbbbb", "aaaaaaaa"], [s["id"] for s in model["sessions"]])

    def test_active_needs_no_ended_at_and_a_recent_write(self):
        self.write_three()
        self.write_session("2026-09-30_0900_stale", "dddddddd4", "2026-09-30T09:00:00-07:00",
                           age_seconds=perf_view.ACTIVE_WINDOW_SECONDS + 60, breakdown=breakdown(500, 0))
        active = {s["id"]: s["active"] for s in perf_view.build_model(self.root)["sessions"]}
        self.assertEqual({"cccccccc": True, "bbbbbbbb": False, "aaaaaaaa": False, "dddddddd": False}, active)

    def test_overview_skips_uncompiled_sessions(self):
        self.write_three()
        overview = perf_view.build_model(self.root)["overview"]
        self.assertEqual((3, 2, 5000), (overview["sessions"], overview["compiled"], overview["total"]))
        self.assertEqual(2500, overview["mean"])
        self.assertAlmostEqual(statistics.pstdev([1000, 4000]), overview["stdev"])
        self.assertEqual([1000, 4000], sorted(point["total"] for point in overview["totals"]))

    def test_overview_category_totals_and_averages(self):
        self.write_three()
        categories = {c["name"]: c for c in perf_view.build_model(self.root)["overview"]["categories"]}
        self.assertEqual(1200, categories["Ad-hoc tool calls"]["tokens"])
        self.assertEqual(600, categories["Ad-hoc tool calls"]["average"])
        self.assertAlmostEqual(1200 / 5000, categories["Ad-hoc tool calls"]["share"])

    def test_uncompiled_session_keeps_its_error(self):
        self.write_three()
        session = next(s for s in perf_view.build_model(self.root)["sessions"] if s["id"] == "bbbbbbbb")
        self.assertEqual((False, "no transcript", []), (session["compiled"], session["error"], session["categories"]))

    def test_unreadable_session_json_is_skipped(self):
        self.write_three()
        (self.root / "broken").mkdir()
        (self.root / "broken" / "session.json").write_text("{not json")
        self.assertEqual(3, len(perf_view.build_model(self.root)["sessions"]))

    def test_no_compiled_sessions_gives_zero_overview(self):
        self.write_session("x", "eeeeeeee5", "2026-10-01T09:00:00-07:00")
        overview = perf_view.build_model(self.root)["overview"]
        self.assertEqual((0, 0, 0.0, []), (overview["compiled"], overview["total"], overview["mean"], overview["categories"]))


class TestServerTab(PerfViewTestCase):
    def test_no_sessions_means_no_tab(self):
        self.assertIsNone(perf_view.find_reports_root(self.doc))
        self.assertNotIn("perf", [tab["kind"] for tab in review_server._tabs([self.doc])])

    def test_tab_is_added_last(self):
        self.write_three()
        tabs = review_server._tabs([self.doc])
        self.assertEqual(["md", "perf"], [tab["kind"] for tab in tabs])
        self.assertEqual("Performance", tabs[-1]["title"])

    def test_tab_mtime_follows_a_recompiled_session(self):
        self.write_three()
        tab = review_server._tabs([self.doc])[-1]
        before = review_server._tab_mtime(tab)
        path = self.root / "2026-10-01_0900_old" / "session.json"
        os.utime(path, (before + 5, before + 5))
        self.assertEqual(before + 5, review_server._tab_mtime(tab))

    def test_page_renders_the_perf_tab(self):
        self.write_three()
        page = review_server.build_page([self.doc], live=False)
        self.assertIn('class="perf-view"', page)
        self.assertIn("function renderPerf(", page)
        source = json.loads(review_server._collect_sources(review_server._tabs([self.doc]))["d1"])
        self.assertIn("Runnable tools", source["standardized_names"])


if __name__ == "__main__":
    unittest.main()
