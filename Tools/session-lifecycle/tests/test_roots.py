"""Regression tests for where session folders live and when they may be renamed.

MR-20261009-01: the reports root followed the shell's cwd (and, inside a symlinked
GitIgnoredExternals layer, the layer's own git repo), so sessions split into nested folders.
MR-20261009-04: relabelling a closed session renamed the folder that progress files reference.

Each test builds a throwaway host project (git repo + CLAUDE.md) with a layer repo symlinked
into GitIgnoredExternals/, and runs a copy of the tools from inside that layer, so nothing
touches the real project's reports.

    python3 -m unittest discover -s Tools/session-lifecycle/tests -p 'test_*.py'
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

TOOLS = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))
SESSION_ID = "aaaaaaaa-0000-0000-0000-000000000000"
FOLDER = "2026-10-12_1000_investigation_aaaaaaaa"


def git(args, cwd):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t"] + args, cwd=cwd,
                   check=True, capture_output=True)


class RootTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="session-roots-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.host = os.path.join(self.tmp, "Host")
        self.layer_real = os.path.join(self.tmp, "LayerRepo")
        os.makedirs(self.host)
        os.makedirs(self.layer_real)
        for repo in (self.host, self.layer_real):
            git(["init", "-q"], repo)
        open(os.path.join(self.host, "CLAUDE.md"), "w").close()
        git(["commit", "-q", "--allow-empty", "-m", "init"], self.host)   # worktree tests need a commit
        shutil.copytree(os.path.join(TOOLS, "session-lifecycle"), os.path.join(self.layer_real, "Tools", "session-lifecycle"),
                        ignore=shutil.ignore_patterns("tests", "__pycache__"))
        shutil.copytree(os.path.join(TOOLS, "setup"), os.path.join(self.layer_real, "Tools", "setup"),
                        ignore=shutil.ignore_patterns("__pycache__"))
        os.makedirs(os.path.join(self.host, "GitIgnoredExternals"))
        self.layer = os.path.join(self.host, "GitIgnoredExternals", "Layer")
        os.symlink(self.layer_real, self.layer)
        self.sessions = os.path.join(self.host, "GitIgnoreReports", "Sessions")
        os.makedirs(self.sessions)
        self.transcript = os.path.join(self.tmp, SESSION_ID + ".jsonl")
        with open(self.transcript, "w") as handle:
            handle.write(json.dumps({"type": "user", "message": {"content": "hi"}}) + "\n")

    def script(self, via_layer=True):
        base = self.layer if via_layer else self.layer_real
        return os.path.join(base, "Tools", "session-lifecycle", "session_lifecycle.py")

    def run_script(self, args, cwd, stdin=None, via_layer=True):
        env = {k: v for k, v in os.environ.items()
               if k not in ("CLAUDE_PROJECT_DIR", "CLAUDE_CODE_SESSION_ID", "SESSION_REPORTS_ROOT")}
        env["PWD"] = cwd
        return subprocess.run([sys.executable, self.script(via_layer)] + args, cwd=cwd, env=env,
                              input=stdin, capture_output=True, text=True)

    def write_session(self, lane="investigation", closed=False):
        folder = os.path.join(self.sessions, FOLDER)
        os.makedirs(folder)
        state = {"session_id": SESSION_ID, "transcript_path": self.transcript, "project_dir": self.host,
                 "started_at": "2026-10-12T10:00:00-07:00", "tracking_started_at": "2026-10-12T10:00:00-07:00",
                 "name": None, "lane": lane, "work_type": None, "title": None,
                 "inaccuracies": [], "iterations": [], "end_session_run": closed}
        with open(os.path.join(folder, "session.json"), "w") as handle:
            json.dump(state, handle)
        return folder

    def nested(self):
        found = []
        for current, dirs, _ in os.walk(os.path.join(self.host, "GitIgnoreReports")):
            found += [os.path.join(current, d) for d in dirs if d == "GitIgnoreReports"]
        return found

    def session_folders(self):
        return sorted(n for n in os.listdir(self.sessions) if os.path.isdir(os.path.join(self.sessions, n)))


class ReportsRootTests(RootTestCase):
    def test_hook_stop_from_inside_reports_creates_no_nested_folder(self):
        payload = json.dumps({"session_id": SESSION_ID, "transcript_path": self.transcript, "cwd": self.sessions})
        result = self.run_script(["hook-stop"], cwd=self.sessions, stdin=payload)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.nested(), [])
        self.assertEqual(len(self.session_folders()), 1)
        self.assertTrue(self.session_folders()[0].endswith("_aaaaaaaa"))

    def test_commands_resolve_host_from_any_cwd(self):
        folder = self.write_session()
        cwds = {"reports": self.sessions, "layer": self.layer, "layer real path": self.layer_real,
                "host": self.host}
        for label, cwd in cwds.items():
            for via_layer in (True, False):
                with self.subTest(cwd=label, script_via_layer=via_layer):
                    if not via_layer and label == "layer real path":
                        continue   # no logical path anywhere: documented limit, nothing to resolve from
                    result = self.run_script(["path", "--session-id", SESSION_ID], cwd=cwd, via_layer=via_layer)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout.strip(), folder)
        self.assertEqual(self.nested(), [])

    def test_nested_reports_root_is_refused(self):
        nested_root = os.path.join(self.sessions, "GitIgnoreReports", "Sessions")
        result = self.run_script(["--reports-root", nested_root, "set", "--session-id", SESSION_ID,
                                  "--title", "x"], cwd=self.host)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("nested reports root", result.stderr)
        self.assertFalse(os.path.exists(nested_root))


class ProjectRootTests(RootTestCase):
    def setUp(self):
        super().setUp()
        sys.path.insert(0, os.path.join(TOOLS, "setup"))
        self.addCleanup(sys.path.remove, os.path.join(TOOLS, "setup"))
        import project_root
        self.project_root = project_root

    def test_layer_path_resolves_to_host(self):
        self.assertEqual(self.project_root.find_project_root(self.layer), self.host)
        self.assertEqual(self.project_root.find_working_root(os.path.join(self.layer, "Tools")), self.host)

    def test_worktree_resolves_to_main_checkout(self):
        worktree = os.path.join(self.tmp, "wt")
        git(["worktree", "add", "-q", worktree], self.host)
        self.assertEqual(self.project_root.find_project_root(worktree), self.host)
        self.assertEqual(self.project_root.find_working_root(worktree), worktree)

    def test_marker_fallback_without_git(self):
        plain = os.path.join(self.tmp, "Plain")
        os.makedirs(os.path.join(plain, "a", "b"))
        open(os.path.join(plain, "CLAUDE.md"), "w").close()
        self.assertEqual(self.project_root.find_project_root(os.path.join(plain, "a", "b")), plain)

    def test_logical_cwd_keeps_symlinked_spelling(self):
        previous, previous_pwd = os.getcwd(), os.environ.get("PWD")
        try:
            os.chdir(self.layer)
            os.environ["PWD"] = self.layer
            self.assertEqual(self.project_root.logical_cwd(), self.layer)
        finally:
            os.chdir(previous)
            if previous_pwd is None:
                os.environ.pop("PWD", None)
            else:
                os.environ["PWD"] = previous_pwd


class ClosedSessionTests(RootTestCase):
    def test_closed_session_refuses_lane_change_and_keeps_name(self):
        self.write_session(closed=True)
        result = self.run_script(["set", "--session-id", SESSION_ID, "--lane", "other"], cwd=self.host)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("start a fresh session", result.stderr)
        self.assertEqual(self.session_folders(), [FOLDER])

    def test_closed_session_saves_name_without_renaming(self):
        folder = self.write_session(closed=True)
        result = self.run_script(["set", "--session-id", SESSION_ID, "--name", "later name", "--title", "t"],
                                 cwd=self.host)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.session_folders(), [FOLDER])
        with open(os.path.join(folder, "session.json")) as handle:
            self.assertEqual(json.load(handle)["name"], "later name")

    def test_open_session_lane_change_renames_and_keeps_history(self):
        self.write_session(closed=False)
        result = self.run_script(["set", "--session-id", SESSION_ID, "--lane", "bug_fix"], cwd=self.host)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.session_folders(), ["2026-10-12_1000_bug-fix_aaaaaaaa"])
        with open(os.path.join(self.sessions, self.session_folders()[0], "session.json")) as handle:
            history = json.load(handle)["lane_history"]
        self.assertEqual((history[0]["from"], history[0]["to"]), ("investigation", "bug_fix"))


if __name__ == "__main__":
    unittest.main()
