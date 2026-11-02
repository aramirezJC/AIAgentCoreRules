"""Discovery reads per-feature JSON without relying on its generated projection."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import session_lifecycle
from feature_state import create_state, update_state


class StructuredFeaturesTest(unittest.TestCase):
    def test_json_wins_and_close_filters_without_progress_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root / 'Example'
            state = create_state(directory)
            progress = directory / 'Example_Progress.md'
            progress.write_text('status: "complete"\nfeature: "Wrong"\n')
            features = session_lifecycle.active_features(root, root)
            self.assertEqual(features[0]['feature'], 'Example')
            self.assertFalse(features[0]['migration_required'])
            state = update_state(directory, 'close', {'status': 'on_hold', 'reason': 'Paused by engineer'}, state['revision'])
            progress.unlink()
            self.assertEqual(session_lifecycle.active_features(root, root), [])
            self.assertEqual(session_lifecycle.closed_features(root, root)[0]['status'], 'on_hold')
