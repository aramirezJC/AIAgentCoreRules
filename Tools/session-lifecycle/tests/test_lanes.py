"""Lane and work-type tables: every lane has a default work type and a fresh-session command, and
the large_task lane (LargeTask.md) defaults to the large_feature work type.

    python3 -m unittest discover -s Tools/session-lifecycle/tests -p 'test_*.py'
"""

import contextlib
import io
import os
import sys
import unittest

sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
import session_lifecycle  # noqa: E402

sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), "..", "..", "session-analysis")))
import session_meta_report  # noqa: E402


class LaneTableTests(unittest.TestCase):
    def test_every_lane_has_a_valid_default_work_type_and_command(self):
        for lane in session_lifecycle.LANES:
            self.assertIn(session_lifecycle.LANE_WORK_TYPE[lane], session_lifecycle.WORK_TYPES, lane)
            self.assertIn(lane, session_lifecycle.LANE_COMMAND)

    def test_meta_report_knows_every_lane(self):
        for lane in session_lifecycle.LANES:
            self.assertIn(lane, session_meta_report.LANES)
            self.assertEqual(session_meta_report.LANE_WORK_TYPE[lane], session_lifecycle.LANE_WORK_TYPE[lane])

    def test_large_task_defaults_to_large_feature(self):
        state = {}
        session_lifecycle.set_work_type(state, session_lifecycle.LANE_WORK_TYPE["large_task"], "lane")
        self.assertEqual((state["work_type"], state["work_type_source"]), ("large_feature", "lane"))

    def test_large_session_switching_to_large_task_is_offered_the_command(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            session_lifecycle.offer_fresh_session({"tokens": {"total_tokens": 41200000}}, "large_task")
        self.assertIn('/new-session "/large-task <ask>"', stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
