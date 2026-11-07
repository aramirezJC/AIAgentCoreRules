"""Portable paths, picker and install persistence contracts."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import project_config as config


class ProjectConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.file = self.root / config.CONFIG_NAME
        self.args = argparse.Namespace(dry_run=False, defaults=False, features_dir=None, design_documents_dir=None)

    def save(self, **paths):
        value = {'schema_version': 1, 'paths': dict(config.DEFAULT_PATHS, **paths), 'custom': {'keep': True}}
        self.file.write_text(json.dumps(value))
        return value

    def test_legacy_defaults_and_initial_creation_without_tty(self):
        self.assertEqual(config.resolve_path(self.root, 'features', environ={}), self.root / config.DEFAULT_PATHS['features'])
        with mock.patch.object(config.sys.stdin, 'isatty', return_value=False):
            value = config.prepare_install(self.args, self.root)
        config.write_install(value, self.root, False, [])
        self.assertEqual(json.loads(self.file.read_text()), {'schema_version': 1, 'paths': config.DEFAULT_PATHS})

    def test_config_precedence_and_relative_overrides(self):
        self.save(features='Assets/Documentation/Features')
        self.assertEqual(config.resolve_path(self.root, 'features', environ={}), self.root / 'Assets/Documentation/Features')
        self.assertEqual(config.resolve_path(self.root, 'features', environ={'SESSION_FEATURES_ROOT': 'Env'}), self.root / 'Env')
        self.assertEqual(config.resolve_path(self.root, 'features', override='Cli', environ={'SESSION_FEATURES_ROOT': 'Env'}), self.root / 'Cli')

    def test_invalid_json_version_and_paths_fail_clearly(self):
        self.file.write_text('{')
        with self.assertRaisesRegex(RuntimeError, 'cannot read'):
            config.load_config(self.root)
        for value in [[], {}, {'schema_version': True, 'paths': {}}, {'schema_version': 2, 'paths': {}}]:
            self.file.write_text(json.dumps(value))
            with self.assertRaises(RuntimeError):
                config.load_config(self.root)
        for path in ['', '.', '..', '../Outside', '/tmp/Outside', 'C:/Outside', 'C:\\Outside', 'A/../../Outside', 'Bad\0Path', 12]:
            self.save(features=path)
            with self.subTest(path=path), self.assertRaises(RuntimeError):
                config.load_config(self.root)

    def test_reject_symlink_escape_and_file_target(self):
        (self.root / 'Escape').symlink_to(self.root.parent, target_is_directory=True)
        self.save(features='Escape/Elsewhere')
        with self.assertRaisesRegex(RuntimeError, 'escapes'):
            config.load_config(self.root)
        (self.root / 'File').write_text('data')
        for value in ['File', 'File/Features']:
            self.save(features=value)
            with self.subTest(value=value), self.assertRaisesRegex(RuntimeError, 'not a directory'):
                config.load_config(self.root)

    def test_existing_config_preserved_and_conflicting_flags_rejected(self):
        self.save(features='Assets/Features')
        before = self.file.read_bytes()
        with mock.patch('builtins.input', side_effect=AssertionError('must not prompt')):
            self.assertIsNone(config.prepare_install(self.args, self.root))
        self.assertEqual(self.file.read_bytes(), before)
        self.args.features_dir = 'Different'
        with self.assertRaisesRegex(RuntimeError, 'already defines'):
            config.prepare_install(self.args, self.root)
        self.assertEqual(self.file.read_bytes(), before)

    def test_dry_run_and_defaults_never_open_picker(self):
        for dry_run, defaults in [(True, False), (False, True)]:
            self.args.dry_run, self.args.defaults = dry_run, defaults
            with mock.patch.object(config.sys.stdin, 'isatty', return_value=True), mock.patch('builtins.input', side_effect=AssertionError('must not prompt')):
                value = config.prepare_install(self.args, self.root)
            config.write_install(value, self.root, True, [])
            self.assertFalse(self.file.exists())

    def test_picker_selection_saved_as_relative_and_cancel_writes_nothing(self):
        chosen = self.root / 'Assets/Documentation'
        chosen.mkdir(parents=True)
        result = subprocess.CompletedProcess([], 0, str(chosen) + '\n', '')
        with mock.patch.object(config.sys, 'platform', 'darwin'), mock.patch.object(config.subprocess, 'run', return_value=result):
            self.assertEqual(config.pick_directory(self.root, 'features'), 'Assets/Documentation')
        with mock.patch.object(config.sys.stdin, 'isatty', return_value=True), mock.patch('builtins.input', side_effect=['2', '1']), mock.patch.object(config, 'pick_directory', return_value='Assets/Documentation'):
            value = config.prepare_install(self.args, self.root)
        self.assertEqual(value['paths']['features'], 'Assets/Documentation')
        self.assertEqual(value['paths']['design_documents'], config.DEFAULT_PATHS['design_documents'])
        with mock.patch.object(config.sys, 'platform', 'darwin'), mock.patch.object(config.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '', '')):
            with self.assertRaisesRegex(RuntimeError, 'cancelled'):
                config.pick_directory(self.root, 'features')
        self.assertFalse(self.file.exists())

    def test_picker_unavailable_and_outside_project_have_actionable_errors(self):
        with mock.patch.object(config.sys, 'platform', 'darwin'), mock.patch.object(config.subprocess, 'run', side_effect=OSError('missing')):
            with self.assertRaisesRegex(RuntimeError, '--features-dir'):
                config.pick_directory(self.root, 'features')
        with mock.patch.object(config.sys, 'platform', 'darwin'), mock.patch.object(config.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, str(self.root.parent), '')):
            with self.assertRaisesRegex(RuntimeError, 'inside the project'):
                config.pick_directory(self.root, 'features')

    def test_resolution_does_not_follow_changed_cwd(self):
        self.save(features='Assets/Documentation/Features')
        nested = self.root / 'Nested'
        nested.mkdir()
        result = subprocess.run([sys.executable, '-B', str(Path(config.__file__)), '--project', str(self.root), 'get', 'features'], cwd=nested, capture_output=True, text=True, env=dict(os.environ, SESSION_FEATURES_ROOT=''))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(self.root / 'Assets/Documentation/Features'))

    def test_worktree_config_is_local_when_cli_discovers_project(self):
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        self.save(features='MainFeatures')
        subprocess.run(['git', 'add', config.CONFIG_NAME], cwd=self.root, check=True)
        subprocess.run(['git', '-c', 'user.name=Config Test', '-c', 'user.email=config@example.test', 'commit', '-q', '-m', 'fixture'], cwd=self.root, check=True)
        worktree = self.root / 'Checkout'
        subprocess.run(['git', 'worktree', 'add', '-q', '-b', 'fixture-checkout', str(worktree)], cwd=self.root, check=True)
        value = json.loads((worktree / config.CONFIG_NAME).read_text())
        value['paths']['features'] = 'WorktreeFeatures'
        (worktree / config.CONFIG_NAME).write_text(json.dumps(value))
        nested = worktree / 'Nested'
        nested.mkdir()
        environment = dict(os.environ, SESSION_FEATURES_ROOT='', PWD=str(nested))
        result = subprocess.run([sys.executable, '-B', str(Path(config.__file__)), 'get', 'features'], cwd=nested, capture_output=True, text=True, env=environment)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(worktree / 'WorktreeFeatures'))
        self.assertEqual(json.loads(self.file.read_text())['paths']['features'], 'MainFeatures')


if __name__ == '__main__':
    unittest.main()
