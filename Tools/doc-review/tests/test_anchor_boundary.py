"""Category 3 (Boundary) tests for LocalDocReview -- E1, E2, E3, E4, E11.

Assertions focus on the guard the TDD promises: a changed source must never crash the resolver
or silently mis-point a comment -- it must resolve, or clearly report ambiguous/orphaned.

Two implementation gaps were found against LocalDocReviewComments / the UseCases solutions while
writing these tests and were resolved with the engineer before the tests below were written:
  - E1: resolve_text_anchor's orphaned result was missing `heading_path` (anchor_resolver.py) --
    fixed to echo the anchor's own heading_path, and surfaced in the CLI's text output
    (doc_review.py _print_text). Tested here.
  - E11: the documented "fuzzy fallback" after tag-stripping does not exist -- only an exact
    match on the stripped text. Logged as a TaskList follow-up (fuzzy matching, task 21, is its
    own design decision) and still not implemented: a quote that differs from the source by
    actual wording still orphans (tested below). A *whitespace* difference no longer needs that
    fallback, though -- V1's Q1/G3 Markdown-normalization (anchor_resolver._normalize_markdown)
    collapses whitespace as part of matching against the rendered (tag- and syntax-free) text the
    browser's selection quote is captured from, so the old "double space vs. single space"
    near-miss now resolves. That is deterministic normalization, not fuzzy matching, so it was
    updated below rather than carved out as a gap.

V1 additions (LocalDocReviewV1_Architecture.md Q1-Q3): Markdown-syntax-normalized text matching
(G3), diagram edge anchors (G1), and sequence-message occurrence_index restricted to message
lines, not Notes/participants/aliases (G2).

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

    def test_resolveTextAnchor_withInlineHtmlAndExtraInnerWhitespace_resolvesViaWhitespaceCollapse(self):
        # G3/Q1: a double space inside a tag-stripped span is a whitespace difference, which V1's
        # Markdown normalization now collapses on both sides of the comparison -- this used to
        # orphan (no fuzzy fallback existed yet) but is deterministic normalization, not fuzzy
        # matching, so it now resolves.
        self.doc_path.write_text(
            '# Design\n\nThe <span class="NEW">quick  brown</span> fox jumps over the lazy dog.\n'
        )
        anchor = {"file": self.doc_path.name, "quote": "The quick brown fox jumps over the lazy dog."}

        resolution = resolve_text_anchor(self.tmp, anchor)

        self.assertEqual(resolution["status"], "resolved",
                          "a whitespace-only difference must resolve after Markdown normalization")
        self.assertEqual(resolution["line"], 3)

    def test_resolveTextAnchor_withGenuinelyDifferentWording_reportsOrphanedNotFuzzyMatched(self):
        # E11 gap, still open (task 21): normalization handles Markdown syntax and whitespace, not
        # approximate text similarity. A quote that differs by actual wording must still orphan.
        self.doc_path.write_text("# Design\n\nThe quick brown fox jumps over the lazy dog.\n")
        anchor = {"file": self.doc_path.name, "quote": "The quick brown fox leaps over the lazy dog."}

        resolution = resolve_text_anchor(self.tmp, anchor)

        self.assertEqual(resolution["status"], "orphaned",
                          "without a fuzzy fallback, different wording must orphan, not guess")

    def test_resolveTextAnchor_quoteWritesMarkdownSyntaxInSource_resolvesAgainstNormalizedView(self):
        # G3/Q1: the quote is captured from the browser's rendered (syntax-free) text; the source
        # carries bold/italic/code emphasis, a link, a heading marker, and a list marker.
        self.doc_path.write_text(
            "# Design\n\n"
            "- The **quick** _brown_ `fox` jumps over the [lazy dog](https://example.com/dog).\n"
        )
        anchor = {"file": self.doc_path.name, "quote": "The quick brown fox jumps over the lazy dog."}

        resolution = resolve_text_anchor(self.tmp, anchor)

        self.assertEqual(resolution["status"], "resolved",
                          "Markdown emphasis/link/list syntax must be normalized away before matching")
        self.assertEqual(resolution["line"], 3)

    def test_resolveTextAnchor_quoteMatchesTableCellText_resolvesWithPipesStripped(self):
        # G3/Q1: a table row's rendered cell text has no pipes; the source does.
        self.doc_path.write_text("# Design\n\n| Risk | Owner |\n| --- | --- |\n| Data loss | Andi |\n")
        anchor = {"file": self.doc_path.name, "quote": "Data loss Andi"}

        resolution = resolve_text_anchor(self.tmp, anchor)

        self.assertEqual(resolution["status"], "resolved")
        self.assertEqual(resolution["line"], 5)


class DiagramAnchorBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="anchor-boundary-diagram-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.diagram_path = self.tmp / "flow.mmd"

    def test_resolveDiagramAnchor_emptySpacePin_resolvesWithNoLineRatherThanOrphaning(self):
        # U3: a click on empty diagram space creates a point-only pin, with nothing textual or
        # structural to re-resolve against. It never referred to source content, so it should
        # never be reported orphaned just because it carries no element_id/source_id/label.
        self.diagram_path.write_text("graph TD\n  A --> B\n")
        anchor = {"file": self.diagram_path.name, "point": {"x": 12.0, "y": 34.0}}

        resolution = resolve_diagram_anchor(self.tmp, anchor)

        self.assertEqual(resolution, {"status": "resolved", "file": self.diagram_path.name, "line": None})

    def test_resolveDiagramAnchor_emptySpacePinWhenFileMissing_stillOrphans(self):
        # E20: the file itself not being served at all is a real orphan, point-only or not.
        anchor = {"file": "missing.mmd", "point": {"x": 1.0, "y": 2.0}}

        resolution = resolve_diagram_anchor(self.tmp, anchor)

        self.assertEqual(resolution["status"], "orphaned")

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

    def test_resolveDiagramAnchor_sequenceMessageLabelAlsoAppearsInNoteAndAlias_countsMessageLinesOnly(self):
        # G2: "ping" also appears in a Note and a participant alias; neither is a message, so
        # occurrence_index 1 must still land on the second actual A->>B: ping message, not the
        # Note or the alias line.
        self.diagram_path.write_text(
            "sequenceDiagram\n"
            "  participant A as pinger\n"
            "  A->>B: ping\n"
            "  Note over A,B: ping was sent\n"
            "  B->>A: pong\n"
            "  A->>B: ping\n"
        )
        anchor_second = {"file": self.diagram_path.name, "label": "ping", "occurrence_index": 1}

        resolution = resolve_diagram_anchor(self.tmp, anchor_second)

        self.assertEqual(resolution["status"], "resolved")
        self.assertEqual(resolution["line"], 6, "the Note and the alias must not count as 'ping' messages")

    def test_resolveDiagramAnchor_withEdgeFromToAndIndex_resolvesTheIndexthMatchingEdgeLine(self):
        # G1: edge anchors have no stable source_id (mermaid's L_A_B_0 never appears in source);
        # the resolver instead finds the line containing both node ids and an arrow.
        self.diagram_path.write_text(
            "graph TD\n"
            "  A[Start] --> B[Middle]\n"
            "  B[Middle] --> C[End]\n"
            "  A[Start] --> B[Middle]\n"
        )
        anchor_first = {"file": self.diagram_path.name, "edge": {"from": "A", "to": "B", "index": 0}}
        anchor_second = {"file": self.diagram_path.name, "edge": {"from": "A", "to": "B", "index": 1}}

        first = resolve_diagram_anchor(self.tmp, anchor_first)
        second = resolve_diagram_anchor(self.tmp, anchor_second)

        self.assertEqual(first["status"], "resolved")
        self.assertEqual(first["line"], 2, "index 0 must pick the first A->B edge line")
        self.assertEqual(second["status"], "resolved")
        self.assertEqual(second["line"], 4, "index 1 must pick the second A->B edge line, not the first")

    def test_resolveDiagramAnchor_withEdgeWhereNodesOnlyCoOccurWithoutAnArrow_orphans(self):
        # G1: a line can mention both node ids without being an edge between them (e.g. both
        # appear inside an unrelated node's label) -- that must not be mistaken for the edge.
        self.diagram_path.write_text(
            "graph TD\n"
            "  A[Start] --> C[End]\n"
            "  N[mentions A and B but is not an edge]\n"
        )
        anchor = {"file": self.diagram_path.name, "edge": {"from": "A", "to": "B", "index": 0}}

        resolution = resolve_diagram_anchor(self.tmp, anchor)

        self.assertEqual(resolution["status"], "orphaned",
                          "both ids co-occurring without an arrow between them must not resolve")


if __name__ == "__main__":
    unittest.main()
