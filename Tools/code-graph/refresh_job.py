#!/usr/bin/env python3
"""Single-flight background runner for the configured index rebuild command.

The command is fixed when the server starts (--refresh-cmd); an HTTP request can only trigger
it, never change it. One run at a time: start() returns False while a run is in progress.
"""
import shlex
import subprocess
import threading
import time

DEFAULT_TIMEOUT_SECONDS = 15 * 60
LOG_TAIL_LINES = 20


class RefreshJob:
    def __init__(self, command, cwd, log_path, timeout=DEFAULT_TIMEOUT_SECONDS):
        self.argv = shlex.split(command) if isinstance(command, str) else list(command or [])
        self.cwd = str(cwd)
        self.log_path = str(log_path)
        self.timeout = timeout
        self._lock = threading.Lock()
        self._thread = None
        self._state = {'state': 'idle', 'started': None, 'finished': None, 'exit_code': None, 'error': None}

    @property
    def available(self):
        return bool(self.argv)

    def start(self):
        """Start a run in a background thread. False when one is already running."""
        if not self.available:
            raise RuntimeError('no refresh command configured')
        with self._lock:
            if self._state['state'] == 'running':
                return False
            self._state = {'state': 'running', 'started': time.time(), 'finished': None,
                           'exit_code': None, 'error': None}
            self._thread = threading.Thread(target=self._run, name='code-graph-refresh', daemon=True)
            self._thread.start()
        return True

    def _run(self):
        exit_code, error = None, None
        try:
            with open(self.log_path, 'w') as log:
                completed = subprocess.run(self.argv, cwd=self.cwd, stdin=subprocess.DEVNULL, stdout=log,
                                           stderr=subprocess.STDOUT, timeout=self.timeout)
            exit_code = completed.returncode
            if exit_code != 0:
                error = 'exit code %d' % exit_code
        except subprocess.TimeoutExpired:
            error = 'timed out after %d s' % self.timeout
        except OSError as failure:
            error = str(failure)
        with self._lock:
            self._state.update({'state': 'failed' if error else 'done', 'finished': time.time(),
                                'exit_code': exit_code, 'error': error})

    def wait(self, timeout=None):
        thread = self._thread
        if thread is not None:
            thread.join(timeout)

    def log_tail(self, lines=LOG_TAIL_LINES):
        try:
            with open(self.log_path, errors='replace') as log:
                return log.read().splitlines()[-lines:]
        except OSError:
            return []

    def state(self):
        with self._lock:
            state = dict(self._state)
        state['available'] = self.available
        state['command'] = ' '.join(shlex.quote(part) for part in self.argv)
        state['log_tail'] = self.log_tail() if state['state'] in ('running', 'done', 'failed') else []
        return state
