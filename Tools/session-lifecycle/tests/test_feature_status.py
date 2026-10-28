"""Which progress-file statuses /active-features shows, and which /reopen-feature can reopen.

/close-feature sets abandoned, superseded, on_hold or complete; the first three are hidden from
the active list and the session-start hint but listed by `features --closed`. complete is final.

    python3 -m unittest discover -s Tools/session-lifecycle/tests -p 'test_*.py'
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
import session_lifecycle  # noqa: E402

STATUSES = ["in_progress", "at_gate", "complete", "abandoned", "superseded", "on_hold"]


class FeatureStatusTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="feature-status-")
        self.addCleanup(shutil.rmtree, self.root, True)
        for index, status in enumerate(STATUSES):
            name = "Feature_%s" % status
            os.makedirs(os.path.join(self.root, name))
            with open(os.path.join(self.root, name, "%s_Progress.md" % name), "w") as handle:
                handle.write('```yaml\nfeature:        "%s"\ncurrent_phase:  "1_intake"\nstatus:         "%s"\n'
                             'updated_at:     "2026-10-%02dT10:00:00"\n```\n' % (name, status, 10 + index))

    def statuses(self, features):
        return sorted(f["status"] for f in features)

    def test_active_list_hides_complete_and_closed(self):
        self.assertEqual(self.statuses(session_lifecycle.active_features(self.root, self.root)),
                         ["at_gate", "in_progress"])

    def test_closed_list_holds_only_reopenable(self):
        self.assertEqual(self.statuses(session_lifecycle.closed_features(self.root, self.root)),
                         ["abandoned", "on_hold", "superseded"])

    def test_start_hint_skips_closed(self):
        os.environ["SESSION_FEATURES_ROOT"] = self.root
        self.addCleanup(os.environ.pop, "SESSION_FEATURES_ROOT", None)
        hint = "\n".join(session_lifecycle.feature_hint(self.root, {}))
        self.assertIn("Feature_in_progress", hint)
        for status in ("complete", "abandoned", "superseded", "on_hold"):
            self.assertNotIn("Feature_%s " % status, hint)


if __name__ == "__main__":
    unittest.main()
