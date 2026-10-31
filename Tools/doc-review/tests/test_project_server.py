"""Project preview contracts and request isolation."""
import functools
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import project_server
from review_server import _bind_server


class ProjectPreviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name)
        self.root = self.project / 'Assets/GitIgnoreAssets/Features'
        for name in ('Alpha', 'Beta'):
            directory = self.root / name
            directory.mkdir(parents=True)
            state = project_server.feature_state.create_state(directory, name)
            (directory / 'Design.md').write_text('# Design\nFeature content')
            # Artifact registration uses the public update API in production.
            state['artifact_roles']['tdd'] = 'Design.md'
            (directory / 'state.json').write_text(json.dumps(state))

    def test_fixedTabsAndMissingPlaceholders(self):
        tabs = project_server.project_tabs(self.root, self.root / 'Alpha')
        self.assertEqual([tab['title'] for tab in tabs], list(project_server.TITLES))
        self.assertIn('Beta', tabs[0]['content'])
        self.assertEqual(tabs[2]['file'], 'Design.md')
        self.assertIn('Pending generation', tabs[3]['content'])

    def test_rejectsFeatureAndArtifactTraversal(self):
        with self.assertRaises(ValueError):
            project_server.feature_path(self.root, '../Elsewhere')
        with self.assertRaises(ValueError):
            project_server.artifact_path(self.root / 'Alpha', '../../outside.md')

    def test_commentsAreRequestScopedAndSourceFilesRemainUnchanged(self):
        server = _bind_server(functools.partial(project_server.ProjectHandler, features_root=self.root, project=self.project), None)
        self.addCleanup(server.server_close)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.shutdown)
        url = 'http://127.0.0.1:' + str(server.server_address[1])
        for name in ('Alpha', 'Beta'):
            payload = {'anchor': {'kind': 'text', 'file': 'Design.md', 'quote': 'Feature content'}, 'text': name}
            request = Request(url + '/api/comment?feature=' + name, data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
            with urlopen(request) as response:
                self.assertEqual(json.load(response)['id'], 't1')
        for name in ('Alpha', 'Beta'):
            with urlopen(url + '/api/state?feature=' + name) as response:
                threads = json.load(response)['threads']
            self.assertEqual(len(threads), 1)
            self.assertEqual(threads[0]['replies'][0]['text'], name)
            self.assertEqual((self.root / name / 'Design.md').read_text(), '# Design\nFeature content')
        request = Request(url + '/api/comment', data=b'{}', headers={'Content-Type': 'application/json'})
        with self.assertRaises(HTTPError) as caught:
            urlopen(request)
        self.assertEqual(caught.exception.code, 400)


if __name__ == '__main__':
    unittest.main()
