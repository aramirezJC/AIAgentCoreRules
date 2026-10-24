"""Category 3 (Boundary) tests for LocalDocReview -- E1, E2, E3, E4, E11.

Assertions focus on the guard the TDD promises: a changed source must never crash the resolver
or silently mis-point a comment -- it must resolve, or clearly report ambiguous/orphaned.

Two implementation gaps were found against LocalDocReviewComments / the UseCases solutions while
writing these tests and were resolved with the engineer before the tests below were written:
  - E1: resolve_text_anchor's orphaned result was missing `heading_path` (anchor_resolver.py) --
    fixed to echo the anchor's own heading_path, and surfaced in the CLI's text output
    (doc_review.py _print_text). Tested here.
  - E11: the documented "fuzzy fallback" after tag-stripping does not exist -- only an exact
    match on the stripped text. Left as-is and logged as a TaskList follow-up (fuzzy matching is
    its own design decision); the test below covers the exact-match-after-strip behavior that
    actually exists, not the fuzzy fallback.

    python3 -m unittest discover -s Tools/doc-review/tests -p 'test_*.py'
"""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parents[1]
if str(TOOL_DIR) not in sys.path:
    sys.path.insert(0, str(TOOL_DIR))

from anchor_resolver import resolve_diagram_anchor, resolve_text_anchor  # noqa: E402


class TextAnchorBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="anchor-boundary-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.doc_path = self.tmp / "Design.md"

    def test_resolveTextAnchor_whenCommentedTextWasDeleted_reportsOrphanedWithQuoteAndHeadingPath(self):
        # E1: the engineer's quote once lived under "Design" > "Risks"; the sentence is gone now.
        self.doc_path.write_text("# Design\n\n## Risks\n\nSomething else entirely.\n")
        anchor = {
            "file": self.doc_path.name,
            "quote": "This sentence no longer exists.",
            "heading_path": ["Design", "Risks"],
        }

        resolution = resolve_text_anchor(self.tmp, anchor)

        self.assertEqual(resolution["status"], "orphaned",
                          "a deleted quote must be reported orphaned, not crash or silently vanish")
        self.assertEqual(resolution["quote"], anchor["quote"], "the original quote must be preserved for the engineer")
        self.assertEqual(resolution["heading_path"], ["Design", "Risks"],
                          "the original heading path must be preserved so the engineer can relocate the comment")

    def test_resolveTextAnchor_whenQuoteAppearsTwice_disambiguatesByPrefixSuffixThenHeadingPath(self):
        # E2: the same sentence appears under two different headings; prefix/suffix alone can't
        # tell them apart (identical on both sides), so heading_path must break the tie.
        self.doc_path.write_text(
            "# Design\n\n"
            "## Section A\n\n"
            "Intro. Repeated sentence. Outro.\n\n"
            "## Section B\n\n"
            "Intro. Repeated sentence. Outro.\n"
        )
        anchor = {
            "file": self.doc_path.name,
            "quote": "Repeated sentence.",
            "prefix": "Intro. ",
            "suffix": " Outro.",
            "heading_path": ["Design", "Section B"],
        }

        resolution = resolve_text_anchor(self.tmp, anchor)

        self.assertEqual(resolution["status"], "resolved",
                          "heading_path must break the tie left by identical prefix/suffix on both occurrences")
        content_lines = self.doc_path.read_text().splitlines()
        first_occurrence = content_lines.index("Intro. Repeated sentence. Outro.")
        second_occurrence = content_lines.index("Intro. Repeated sentence. Outro.", first_occurrence + 1)
        expected_line = second_occurrence + 1
        self.assertEqual(resolution["line"], expected_line, "must resolve to the Section B occurrence, not Section A")

    def test_resolveTextAnchor_whenQuoteAppearsTwiceWithNoDisambiguator_reportsAmbiguousWithEveryCandidateLine(self):
        # E2 fallback: no prefix/suffix/heading_path at all -- every candidate line must be listed.
        self.doc_path.write_text("Same line text.\n\nSame line text.\n")
        anchor = {"file": self.doc_path.name, "quote": "Same line text."}

        resolution = resolve_text_anchor(self.tmp, anchor)

        self.assertEqual(resolution["status"], "ambiguous")
        self.assertEqual(resolution["candidate_lines"], [1, 3], "every occurrence's line must be listed, none dropped")

    def test_resolveTextAnchor_withInlineHtmlSpansAroundQuote_resolvesAgainstTagStrippedSource(self):
        # E11: the quote was captured from the rendered (tag-free) text; the live source wraps
        # part of the sentence in a <span class="NEW">...</span> highlight.
        self.doc_path.write_text(
            '# Design\n\nThe <span class="NEW">quick brown fox</span> jumps over the lazy dog.\n'
        )
        anchor = {"file": self.doc_path.name, "quote": "The quick brown fox jumps over the lazy dog."}

        resolution = resolve_text_anchor(self.tmp, anchor)

        self.assertEqual(resolution["status"], "resolved",
                          "an exact match against the tag-stripped source must still resolve")
        self.assertEqual(resolution["line"], 3)

    def test_resolveTextAnchor_withInlineHtmlAndNoExactStrippedMatch_reportsOrphanedNotFuzzyMatched(self):
        # E11 gap (logged as a follow-up, not fixed here): stripping tags still leaves an exact
        # substring search. A quote that only matches after tags are stripped AND collapsed
        # whitespace is restored has no fuzzy fallback today, so it must orphan, not false-match.
        self.doc_path.write_text(
            '# Design\n\nThe <span class="NEW">quick  brown</span> fox jumps over the lazy dog.\n'
        )
        # Two spaces survive the tag strip where the quote below has one -- no fuzzy pass exists
        # to absorb that, so this must orphan rather than silently matching the wrong text.
        anchor = {"file": self.doc_path.name, "quote": "The quick brown fox jumps over the lazy dog."}

        resolution = resolve_text_anchor(self.tmp, anchor)

        self.assertEqual(resolution["status"], "orphaned",
                          "without a fuzzy fallback, a near-miss after tag-stripping must orphan, not guess")


class DiagramAnchorBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="anchor-boundary-diagram-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.diagram_path = self.tmp / "flow.mmd"

    def test_resolveDiagramAnchor_whenSourceIdRenamed_fallsBackToLabelThenOrphans(self):
        # E3: the node the comment was anchored to (old_id) was renamed to new_id in the diagram.
        self.diagram_path.write_text("graph TD\n  new_id[Start Node] --> B[End]\n")
        anchor_with_matching_label = {"file": self.diagram_path.name, "source_id": "old_id", "label": "Start Node"}
        anchor_with_no_match = {"file": self.diagram_path.name, "source_id": "old_id", "label": "Nonexistent Label"}

        fallback = resolve_diagram_anchor(self.tmp, anchor_with_matching_label)
        orphaned = resolve_diagram_anchor(self.tmp, anchor_with_no_match)

        self.assertEqual(fallback["status"], "resolved",
                          "a renamed source_id must fall back to matching by label text")
        self.assertEqual(fallback["line"], 2)
        self.assertEqual(orphaned["status"], "orphaned",
                          "when neither the old source_id nor the label match, it must orphan, not crash")

    def test_resolveDiagramAnchor_sequenceMessageWithNoElementId_anchorsOnLabelAndOccurrenceIndex(self):
        # E4: a sequence-diagram message has no element id, so the anchor is label + which
        # occurrence of that label (e.g. the second "ping" message in the sequence).
        self.diagram_path.write_text(
            "sequenceDiagram\n"
            "  A->>B: ping\n"
            "  B->>A: pong\n"
            "  A->>B: ping\n"
        )
        anchor_first = {"file": self.diagram_path.name, "label": "ping", "occurrence_index": 0}
        anchor_second = {"file": self.diagram_path.name, "label": "ping", "occurrence_index": 1}

        first = resolve_diagram_anchor(self.tmp, anchor_first)
        second = resolve_diagram_anchor(self.tmp, anchor_second)

        self.assertEqual(first["status"], "resolved")
        self.assertEqual(first["line"], 2, "occurrence_index 0 must pick the first 'ping' line")
        self.assertEqual(second["status"], "resolved")
        self.assertEqual(second["line"], 4, "occurrence_index 1 must pick the second 'ping' line, not the first")


if __name__ == "__main__":
    unittest.main()
