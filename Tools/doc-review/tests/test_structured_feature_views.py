"""Authoritative JSON drives views even when generated Markdown is stale or absent."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import progress_view
import perf_view
from feature_state import create_state, update_state


class StructuredFeatureViewsTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name) / 'Example'
        self.state = create_state(self.folder)
        self.folder = self.folder.resolve()
        self.progress = self.folder / 'Example_Progress.md'

    def test_json_wins_over_stale_projection(self):
        state = update_state(self.folder, 'checkpoint', {
            'checkpoint': {'done': [], 'next': 'Review JSON', 'in_flight': 'drafting'},
            'step_status': {'1a': 'done'}, 'tdd_sections': {'Objective': 'approved'},
            'sessions': ['2026-10-31_1200_feature_1234abcd']}, self.state['revision'])
        self.progress.write_text('feature: "Wrong"\ncurrent_phase: "8_retrospective"\n')
        model = progress_view.build_model(self.progress)
        self.assertEqual(model['feature'], 'Example')
        self.assertEqual(model['next'], 'Review JSON')
        self.assertEqual(model['current_phase'], state['current_phase'])
        self.assertEqual(perf_view.feature_filter(self.progress), ('Example', {'1234abcd'}))
        self.assertIn(self.folder / 'state.json', progress_view.watched_paths(self.progress))

    def test_missing_projection_does_not_hide_state(self):
        self.progress.unlink()
        self.assertEqual(progress_view.find_progress_file(self.folder), self.progress)
        self.assertEqual(progress_view.build_model(self.progress)['feature'], 'Example')
        self.assertEqual(perf_view.feature_filter(self.progress), ('Example', set()))

    def test_json_only_tasks_are_visible_and_unregistered_markdown_status_is_not_authority(self):
        (self.folder / 'Example_TDD.md').write_text(
            '## Development plan\n### V0 — Tool\n| # | Title | Status |\n|---|---|---|\n| T1 | Document task | [x] |\n')
        update_state(self.folder, 'task', {'id': 'T2', 'title': 'JSON task', 'status': 'partial'}, self.state['revision'])
        model = progress_view.build_model(self.progress)
        implementation = next(phase for phase in model['phases'] if phase['key'] == '4_implementation')
        tasks = {task['id']: task for stage in implementation['dev_phases'] for task in stage['tasks']}
        self.assertEqual(tasks['T1']['status'], 'todo')
        self.assertEqual(tasks['T2']['status'], 'partial')
        self.assertEqual(tasks['T2']['title'], 'JSON task')

    def test_numeric_document_ids_match_migrated_t_ids(self):
        (self.folder / 'Example_TDD.md').write_text(
            '## Development plan\n### V0 — Tool\n| # | Title | Status |\n|---|---|---|\n| 1 | Document task | [ ] |\n')
        update_state(self.folder, 'task', {'id': 'T1', 'title': 'Document task', 'status': 'done'}, self.state['revision'])
        model = progress_view.build_model(self.progress)
        implementation = next(phase for phase in model['phases'] if phase['key'] == '4_implementation')
        tasks = [task for stage in implementation['dev_phases'] for task in stage['tasks']]
        self.assertEqual([(task['id'], task['status']) for task in tasks], [('1', 'done')])

    def test_json_batch_plan_and_numbers_render(self):
        result = progress_view._batch_view({'plan': ['one', 'two'], 'merged': 1, 'open_pr': 8}, self.folder, lambda number, root: str(number))
        self.assertEqual(result['current'], 2)
        self.assertEqual(result['total'], 2)
        self.assertEqual(result['title'], 'two')
        self.assertEqual(result['open_pr'], 8)
        completed = progress_view._batch_view({'plan': ['one'], 'merged': 1, 'open_pr': None}, self.folder, lambda number, root: str(number))
        self.assertTrue(completed['done'])
        self.assertIsNone(completed['open_pr'])
