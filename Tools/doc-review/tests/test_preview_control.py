"""Preview launcher tests: a healthy server counts as stale once any tool module is newer than its
recorded start time (Python never reloads modules), plus a real start → edit → start restart.

    python3 -m unittest discover -s Tools/doc-review/tests -p 'test_*.py'
"""
import io
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

TOOL_DIR = Path(__file__).resolve().parents[1]
if str(TOOL_DIR) not in sys.path:
    sys.path.insert(0, str(TOOL_DIR))

import preview_control  # noqa: E402


class StaleTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)
        self.tools = self.root / 'tools'
        self.tools.mkdir()
        self.module = self.tools / 'view.py'
        self.module.write_text('')
        self.state_path = self.root / 'server.json'
        self.state_path.write_text('{}')

    def set_mtime(self, path, value):
        os.utime(path, (value, value))

    def test_fresh_when_code_older_than_start(self):
        self.set_mtime(self.module, 1000)
        self.assertFalse(preview_control.stale({'started': 2000}, self.state_path, (self.tools,)))

    def test_stale_when_code_newer_than_start(self):
        self.set_mtime(self.module, 3000)
        self.assertTrue(preview_control.stale({'started': 2000}, self.state_path, (self.tools,)))

    def test_legacy_state_falls_back_to_server_json_mtime(self):
        self.set_mtime(self.state_path, 2000)
        self.set_mtime(self.module, 3000)
        self.assertTrue(preview_control.stale({}, self.state_path, (self.tools,)))
        self.set_mtime(self.module, 1000)
        self.assertFalse(preview_control.stale({}, self.state_path, (self.tools,)))

    def test_missing_tool_dir_is_ignored(self):
        self.assertFalse(preview_control.stale({'started': 2000}, self.state_path, (self.root / 'absent',)))


class RestartTests(unittest.TestCase):
    def setUp(self):
        self.project = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.project)
        self.tools = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tools)
        self.module = self.tools / 'view.py'
        self.module.write_text('')
        os.utime(self.module, (1000, 1000))
        self.addCleanup(self.run_control, 'stop')

    def run_control(self, action):
        output = io.StringIO()
        with mock.patch.object(preview_control, 'TOOL_DIRS', (self.tools,)), redirect_stdout(output):
            preview_control.control(action, self.project)
        return output.getvalue().splitlines()

    def test_start_restarts_after_tool_code_changes(self):
        first = self.run_control('start')
        self.assertEqual(first, self.run_control('start'))
        os.utime(self.module, (time.time() + 5, time.time() + 5))
        restarted = self.run_control('start')
        self.assertEqual(restarted[0], 'restarted (tool code changed)')
        state = json.loads((self.project / '.doc-review' / 'server.json').read_text())
        self.assertEqual(restarted[1], state['url'])
        self.assertIn('started', state)


if __name__ == '__main__':
    unittest.main()
