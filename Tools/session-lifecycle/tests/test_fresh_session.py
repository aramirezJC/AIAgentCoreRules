"""Regression tests for the fresh-session offers.

MR-20261016-02: a session switched lane at ~150M tokens and was resumed after idle gaps with no
offer to start fresh, so cold-cache turns re-read the whole context.

    python3 -m unittest discover -s Tools/session-lifecycle/tests -p 'test_*.py'
"""

import argparse
import contextlib
import datetime
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
import session_lifecycle  # noqa: E402


class LaneChangeOfferTests(unittest.TestCase):
    def offer(self, total):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            session_lifecycle.offer_fresh_session({"tokens": {"total_tokens": total}}, "bug_fix")
        return stderr.getvalue()

    def test_large_session_gets_the_offer(self):
        self.assertIn('/new-session "/bug-fix <symptom>"', self.offer(41200000))

    def test_small_session_stays_silent(self):
        self.assertEqual(self.offer(5000000), "")


class IdleGapTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="idle-gap-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.transcript = os.path.join(self.tmp, "s.jsonl")
        patcher = mock.patch.dict(os.environ, {"SESSION_REPORTS_ROOT": os.path.join(self.tmp, "Sessions")})
        patcher.start()
        self.addCleanup(patcher.stop)

    def hook(self, minutes_ago, context):
        stamp = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=minutes_ago)
        with open(self.transcript, "w") as handle:
            handle.write(json.dumps({"type": "assistant", "timestamp": stamp.isoformat().replace("+00:00", "Z"),
                                     "message": {"usage": {"input_tokens": 10, "cache_read_input_tokens": context}}}) + "\n")
            handle.write(json.dumps({"type": "user", "message": {"content": "next"}}) + "\n")
        stdout = io.StringIO()
        payload = io.StringIO(json.dumps({"session_id": "s", "transcript_path": self.transcript}))
        with mock.patch.object(sys, "stdin", payload), contextlib.redirect_stdout(stdout):
            self.assertEqual(session_lifecycle.cmd_hook_prompt(argparse.Namespace(reports_root=None)), 0)
        return stdout.getvalue()

    def test_gap_past_cache_ttl_on_large_context_is_noted(self):
        output = self.hook(130, 400000)
        self.assertIn("2h 10m", output)
        self.assertIn("/new-session", output)

    def test_short_gap_is_silent(self):
        self.assertEqual(self.hook(5, 400000), "")

    def test_small_context_is_silent(self):
        self.assertEqual(self.hook(130, 20000), "")


class ShellRuleReadTests(unittest.TestCase):
    """MR-20261016-05: rule and process files read via cat/sed only reach the router trace by inference."""

    def hook(self, command):
        stdout = io.StringIO()
        payload = io.StringIO(json.dumps({"tool_name": "Bash", "tool_input": {"command": command}}))
        with mock.patch.object(sys, "stdin", payload), contextlib.redirect_stdout(stdout):
            self.assertEqual(session_lifecycle.cmd_hook_bash(argparse.Namespace(reports_root=None)), 0)
        return stdout.getvalue()

    def test_sed_of_a_process_file_gets_the_reminder(self):
        output = json.loads(self.hook("sed -n 1,5p GitIgnoredExternals/AIAgentCoreRules/Processes/BugFix.md"))
        self.assertEqual(output["hookSpecificOutput"]["hookEventName"], "PreToolUse")
        self.assertIn("Processes/BugFix.md", output["hookSpecificOutput"]["additionalContext"])

    def test_grep_and_non_rule_reads_are_silent(self):
        for command in ("grep -n hypothesis Rules/StopAndVerify.md", "cat Documentation/04_BugFix.md",
                        "head -5 Tools/session-lifecycle/session_lifecycle.py", "git status | tail -3"):
            with self.subTest(command=command):
                self.assertEqual(self.hook(command), "")

    def test_quoted_or_heredoc_mentions_are_silent(self):
        """Retro 000c8ff2 #4: a heredoc that only quoted a sed command fired the reminder."""
        for command in ("python3 t.py note \"ran `sed -n 1,5p Processes/BugFix.md`\"",
                        "echo 'cat Rules/CodingStandards.md'",
                        "cat > t.md <<'EOF'\nsed -n 1,5p Processes/BugFix.md\nEOF\npython3 t.py"):
            with self.subTest(command=command):
                self.assertEqual(self.hook(command), "")

    def test_reads_after_a_separator_or_quoted_path_still_warn(self):
        for command in ("cd x && cat Rules/CodingStandards.md", "ls; head -5 Processes/SmallTask.md | grep x",
                        "cat \"Rules/CodingStandards.md\""):
            with self.subTest(command=command):
                self.assertNotEqual(self.hook(command), "")


if __name__ == "__main__":
    unittest.main()
