#!/usr/bin/env python3
"""Project-owned preview process management. No shell utilities or external flock required."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from urllib.request import urlopen


def healthy(state, project):
    try:
        with urlopen(state['url'] + 'api/health', timeout=1) as response:
            data = json.load(response)
        return data.get('project') == str(project) and data.get('pid') == state['pid']
    except (OSError, ValueError, KeyError):
        return False


def control(action, project):
    project = project.resolve()
    runtime = project / '.doc-review'
    os.umask(0o077)
    runtime.mkdir(exist_ok=True)
    (runtime / ".gitignore").write_text("*\n")
    with (runtime / 'launcher.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state_path = runtime / 'server.json'
        try:
            state = json.loads(state_path.read_text())
        except (OSError, ValueError):
            state = {}
        running = healthy(state, project)
        if action == 'status':
            print('Running: ' + state['url'] if running else 'Stopped')
            return
        if action == 'stop':
            if running:
                os.kill(state['pid'], signal.SIGTERM)
                for _ in range(40):
                    if not healthy(state, project):
                        break
                    time.sleep(.1)
                else:
                    raise RuntimeError('Preview did not stop; runtime metadata retained')
                state_path.unlink(missing_ok=True)
            print('Stopped' if running else 'No managed preview running')
            return
        if running:
            print(state['url'])
            return
        log_path = runtime / 'server.log'
        with log_path.open('w') as log:
            process = subprocess.Popen([sys.executable, str(Path(__file__).with_name('doc_review.py')), 'serve-project', str(project)], stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        for _ in range(60):
            lines = log_path.read_text().splitlines()
            if lines and lines[0].startswith('http://127.0.0.1:'):
                state = {'pid': process.pid, 'url': lines[0], 'project': str(project)}
                if healthy(state, project):
                    temporary = state_path.with_suffix('.tmp')
                    temporary.write_text(json.dumps(state))
                    temporary.replace(state_path)
                    print(state['url'])
                    return
            if process.poll() is not None:
                break
            time.sleep(.1)
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
        raise RuntimeError('Preview startup failed; see ' + str(log_path))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('start', 'stop', 'status'))
    parser.add_argument('--project', default='.')
    args = parser.parse_args()
    try:
        control(args.action, Path(args.project))
    except (OSError, RuntimeError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
