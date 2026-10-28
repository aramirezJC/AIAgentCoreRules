"""Page contract tests: V0's claimed stdlib/CDN-allowlist Best Practices test never actually
existed (found missing while implementing LocalDocReviewV1's static-serving route) -- this is it,
plus the V1 rule that the live page's module/stylesheet route through /static/ and the static page
stays completely free of any /static/ or /api/ reference (it's meant to render once and be opened
with no server behind it).

    python3 -m unittest discover -s Tools/doc-review/tests -p 'test_*.py'
"""
import ast
import importlib.util
import re
import shutil
import sys
import sysconfig
import tempfile
import unittest
from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parents[1]
if str(TOOL_DIR) not in sys.path:
    sys.path.insert(0, str(TOOL_DIR))

from review_server import MARKED_CDN, MERMAID_CDN, SVG_PAN_ZOOM_CDN, build_page  # noqa: E402

ALLOWED_CDN_HOSTS = ("https://cdnjs.cloudflare.com/", "https://cdn.jsdelivr.net/")
STDLIB_DIR = Path(sysconfig.get_paths()["stdlib"]).resolve()
LOCAL_MODULE_NAMES = {path.stem for path in TOOL_DIR.glob("*.py")}
# Stdlib-only modules of other tools in this repo, shared rather than copied (perf_view.py must find the
# same reports root and category names as session_lifecycle.py). Checked stdlib-only themselves below.
IN_REPO_TOOL_MODULES = {
    "project_root": TOOL_DIR.parent / "setup" / "project_root.py",
    "token_breakdown": TOOL_DIR.parent / "session-lifecycle" / "token_breakdown.py",
}


def _imported_top_level_names(file_path: Path):
    tree = ast.parse(file_path.read_text())
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.append(node.module.split(".")[0])
    return names


def _is_stdlib_or_local(name: str) -> bool:
    if name in LOCAL_MODULE_NAMES or name in IN_REPO_TOOL_MODULES:
        return True
    spec = importlib.util.find_spec(name)
    if spec is None:
        return False
    if spec.origin in (None, "built-in", "frozen"):
        return True
    try:
        origin = Path(spec.origin).resolve()
    except (TypeError, ValueError):
        return False
    return origin == STDLIB_DIR or STDLIB_DIR in origin.parents


class StdlibOnlyImportsTests(unittest.TestCase):
    def test_everyPythonFile_importsOnlyStdlibOrItsOwnSiblingModules(self):
        for file_path in TOOL_DIR.glob("*.py"):
            with self.subTest(file=file_path.name):
                for name in _imported_top_level_names(file_path):
                    self.assertTrue(
                        _is_stdlib_or_local(name),
                        f"{file_path.name} imports {name!r}, which is neither stdlib nor a sibling "
                        "module -- this tool is meant to need no pip install",
                    )

    def test_inRepoToolModules_importOnlyStdlib(self):
        for name, file_path in IN_REPO_TOOL_MODULES.items():
            with self.subTest(module=name):
                for imported in _imported_top_level_names(file_path):
                    self.assertTrue(
                        imported not in IN_REPO_TOOL_MODULES and _is_stdlib_or_local(imported)
                        and imported not in LOCAL_MODULE_NAMES,
                        f"{file_path.name} imports {imported!r}, which is not stdlib",
                    )


class PageContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="page-contract-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.doc_path = self.tmp / "Doc.md"
        self.doc_path.write_text("# Doc\n\ntext\n")

    def test_everyExternalScriptSrc_isOnTheCdnAllowlist(self):
        page = build_page([self.doc_path], live=True)
        srcs = re.findall(r'<script[^>]+src="([^"]+)"', page)
        self.assertTrue(srcs, "the page must reference at least the mermaid/marked/panzoom CDNs")
        for src in srcs:
            if src.startswith("/"):
                continue  # our own /static/ route, not an external CDN
            self.assertTrue(src.startswith(ALLOWED_CDN_HOSTS), f"{src} is not on the cdnjs/jsdelivr allowlist")
        # The CDN constants themselves must actually be on the allowlist, not just whatever
        # currently happens to appear in the template.
        for cdn in (MERMAID_CDN, MARKED_CDN, SVG_PAN_ZOOM_CDN):
            self.assertTrue(cdn.startswith(ALLOWED_CDN_HOSTS), f"{cdn} is not on the cdnjs/jsdelivr allowlist")

    def test_livePage_loadsTheStaticReviewUiModule(self):
        page = build_page([self.doc_path], live=True)
        self.assertIn('<script type="module" src="/static/review_ui.js">', page)
        self.assertIn('<link rel="stylesheet" href="/static/review_ui.css">', page)

    def test_staticPage_hasNoStaticOrApiReference(self):
        page = build_page([self.doc_path], live=False)
        self.assertNotIn("/static/", page, "--static must stay comment-UI-free, with no server behind it")
        self.assertNotIn("/api/", page)


if __name__ == "__main__":
    unittest.main()
