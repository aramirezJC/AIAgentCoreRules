import os
import sys
import tempfile
import unittest
from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOL_DIR))

from refresh_job import RefreshJob  # noqa: E402


def python_command(code):
    return [sys.executable, '-c', code]


class RefreshJobTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.log = os.path.join(self.tmp, 'refresh.log')

    def job(self, command, timeout=30):
        return RefreshJob(command, self.tmp, self.log, timeout=timeout)

    def test_unconfigured_job_is_unavailable(self):
        job = self.job(None)
        self.assertFalse(job.available)
        self.assertEqual(job.state()['state'], 'idle')
        with self.assertRaises(RuntimeError):
            job.start()

    def test_string_command_is_split_not_run_through_a_shell(self):
        job = self.job('%s -c "print(1)" ; echo injected' % sys.executable)
        self.assertEqual(job.argv[-3:], [';', 'echo', 'injected'])

    def test_success_records_done_and_log_tail(self):
        job = self.job(python_command("print('indexed 3 files')"))
        self.assertTrue(job.start())
        job.wait(10)
        state = job.state()
        self.assertEqual((state['state'], state['exit_code'], state['error']), ('done', 0, None))
        self.assertEqual(state['log_tail'], ['indexed 3 files'])
        self.assertIsNotNone(state['finished'])

    def test_runs_in_the_configured_cwd(self):
        job = self.job(python_command('import os; print(os.getcwd())'))
        job.start()
        job.wait(10)
        self.assertEqual(os.path.realpath(job.state()['log_tail'][0]), os.path.realpath(self.tmp))

    def test_failure_records_exit_code(self):
        job = self.job(python_command("import sys; print('boom'); sys.exit(3)"))
        job.start()
        job.wait(10)
        state = job.state()
        self.assertEqual((state['state'], state['exit_code'], state['error']), ('failed', 3, 'exit code 3'))
        self.assertEqual(state['log_tail'], ['boom'])

    def test_single_flight(self):
        job = self.job(python_command('import time; time.sleep(1)'))
        self.assertTrue(job.start())
        self.assertFalse(job.start())
        self.assertEqual(job.state()['state'], 'running')
        job.wait(10)
        self.assertTrue(job.start())
        job.wait(10)

    def test_timeout(self):
        job = self.job(python_command('import time; time.sleep(5)'), timeout=0.3)
        job.start()
        job.wait(10)
        state = job.state()
        self.assertEqual(state['state'], 'failed')
        self.assertIn('timed out', state['error'])

    def test_missing_binary(self):
        job = self.job(['/nonexistent/code-graph-binary'])
        job.start()
        job.wait(10)
        self.assertEqual(job.state()['state'], 'failed')


if __name__ == '__main__':
    unittest.main()
