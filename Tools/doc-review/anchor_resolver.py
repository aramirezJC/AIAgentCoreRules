"""Resolve comment anchors (text or diagram) against the current source files.

An anchor stored in the sidecar may point at text or a diagram element the agent has since
edited, moved, or renamed. These functions re-find the anchor in the live sources and report it
as a line number, or as orphaned/ambiguous when it can no longer be pinned down confidently.
See LocalDocReview_TDD.md Edge Cases E1-E4 and E11, and LocalDocReviewV1_Architecture.md Q1-Q3
(Markdown-normalized text matching, edge anchors, sequence-message occurrence_index).
"""
import re
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

INLINE_MARKER_PATTERNS = {
    ".md": re.compile(r"<!--\s*@CLAUDE:\s*(.*?)-->", re.DOTALL),
    ".mmd": re.compile(r"%%\s*@CLAUDE:\s*(.*)"),
}

TAG_PATTERN = re.compile(r"<[^>\n]+>")
HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.*)$")
LINK_PATTERN = re.compile(r"\[([^\]\n]*)\]\([^)\n]*\)")
BLOCK_MARKER_PATTERN = re.compile(r"(?m)^(?:#{1,6}[ \t]+|(?:[-*+]|\d+[.)])[ \t]+)")
EMPHASIS_AND_TABLE_CHARS_PATTERN = re.compile(r"[*_`|]")
WHITESPACE_RUN_PATTERN = re.compile(r"\s+")
# Mermaid sequence-message syntax only: "A->>B: text" / "A--xB: text" / etc. Deliberately excludes
# Note/participant/alias lines, which share no arrow token with an actual message.
SEQUENCE_MESSAGE_PATTERN = re.compile(r"^\s*\S+\s*[-=]{1,2}[>x)]{1,2}\s*\S+\s*:\s*(.*)$")
EDGE_ARROW_PATTERN = re.compile(r"[-=.]{2,}[>ox]?")


def resolve_text_anchor(base_dir: Path, anchor: Dict) -> Dict:
    """Re-find a text anchor (quote/prefix/suffix/heading_path) against a Markdown-normalized
    view of the source: inline syntax (emphasis, links, headings, lists, table pipes, HTML tags)
    stripped and whitespace collapsed, matching how the browser's rendered (tag-free) text looks.
    An offset map keeps each normalized position traceable back to its source line."""
    file_path = base_dir / anchor["file"]
    quote = anchor.get("quote", "")
    heading_path = anchor.get("heading_path", [])
    if not file_path.is_file():
        return {"status": "orphaned", "quote": quote, "heading_path": heading_path}

    source = file_path.read_text()
    normalized, offsets = _normalize_markdown(source)
    normalized_quote = _normalize_whitespace(quote)
    positions = _find_all(normalized, normalized_quote)

    if not positions:
        return {"status": "orphaned", "quote": quote, "heading_path": heading_path}

    if len(positions) > 1:
        positions = _filter_by_context(
            normalized, positions, normalized_quote,
            _normalize_whitespace(anchor.get("prefix", "")), _normalize_whitespace(anchor.get("suffix", "")),
        )

    if len(positions) > 1:
        positions = _filter_by_heading(source, offsets, positions, heading_path)

    if len(positions) == 1:
        return {"status": "resolved", "file": anchor["file"], "line": _line_at(source, offsets[positions[0]])}

    return {
        "status": "ambiguous",
        "file": anchor["file"],
        "candidate_lines": [_line_at(source, offsets[pos]) for pos in positions],
    }


def resolve_diagram_anchor(base_dir: Path, anchor: Dict) -> Dict:
    """Re-find a diagram anchor: edge (from/to/index), else source_id, else label
    (+ occurrence_index for a sequence message, counted over message lines only), else orphan."""
    file_path = base_dir / anchor["file"]
    label = anchor.get("label")
    source_id = anchor.get("source_id")
    edge = anchor.get("edge")
    if not file_path.is_file():
        return {"status": "orphaned", "quote": label or source_id or ""}

    lines = file_path.read_text().splitlines()

    if edge:
        line = _resolve_edge(lines, edge)
        if line is not None:
            return {"status": "resolved", "file": anchor["file"], "line": line}

    if source_id:
        pattern = re.compile(r"\b" + re.escape(source_id) + r"\b")
        hits = [i + 1 for i, line in enumerate(lines) if pattern.search(line)]
        if hits:
            return {"status": "resolved", "file": anchor["file"], "line": hits[0]}

    if label:
        occurrence_index = anchor.get("occurrence_index")
        if occurrence_index is not None:
            matches = _message_lines_matching(lines, label)
            if 0 <= occurrence_index < len(matches):
                return {"status": "resolved", "file": anchor["file"], "line": matches[occurrence_index]}
        else:
            hits = [i + 1 for i, line in enumerate(lines) if label in line]
            if hits:
                return {"status": "resolved", "file": anchor["file"], "line": hits[0]}

    if edge is None and source_id is None and label is None:
        # An empty-space pin (U3): a point in diagram coordinates only, nothing textual or
        # structural to re-resolve against. It never referred to source content, so it has
        # nothing to go stale -- trivially resolved as long as the diagram file still exists.
        return {"status": "resolved", "file": anchor["file"], "line": None}

    return {"status": "orphaned", "quote": label or source_id or ""}


def resolve_thread(base_dir: Path, thread: Dict) -> Dict:
    """Re-resolve a sidecar thread's anchor against the live sources. Shared by doc_review.py's
    CLI output and review_server.py's /api/state 'resolution' field, so neither imports the other."""
    anchor = thread["anchor"]
    if anchor["kind"] == "text":
        return resolve_text_anchor(base_dir, anchor)
    return resolve_diagram_anchor(base_dir, anchor)


def scan_inline_markers(base_dir: Path, files: List[str]) -> List[Dict]:
    """Scan the given files for inline @CLAUDE markers (.md HTML comments, .mmd %% comments)."""
    markers = []
    for rel_path in files:
        file_path = base_dir / rel_path
        pattern = INLINE_MARKER_PATTERNS.get(file_path.suffix)
        if not pattern or not file_path.is_file():
            continue
        text = file_path.read_text()
        for match in pattern.finditer(text):
            markers.append({"file": rel_path, "line": _line_at(text, match.start()), "text": match.group(1).strip()})
    return markers


def _resolve_edge(lines: List[str], edge: Dict) -> Optional[int]:
    from_id, to_id, index = edge.get("from"), edge.get("to"), edge.get("index", 0)
    if not from_id or not to_id:
        return None
    from_pattern = re.compile(r"\b" + re.escape(from_id) + r"\b")
    to_pattern = re.compile(r"\b" + re.escape(to_id) + r"\b")
    hits = [
        i + 1
        for i, line in enumerate(lines)
        if from_pattern.search(line) and to_pattern.search(line) and EDGE_ARROW_PATTERN.search(line)
    ]
    return hits[index] if 0 <= index < len(hits) else None


def _message_lines_matching(lines: List[str], label: str) -> List[int]:
    matches = []
    for i, line in enumerate(lines):
        message = SEQUENCE_MESSAGE_PATTERN.match(line)
        if message and message.group(1).strip() == label:
            matches.append(i + 1)
    return matches


def _normalize_markdown(source: str) -> Tuple[str, List[int]]:
    text, offsets = source, list(range(len(source)))
    text, offsets = _remap(text, offsets, LINK_PATTERN, lambda m: (m.group(1), list(range(m.start(1), m.end(1)))))
    text, offsets = _remap(text, offsets, TAG_PATTERN, lambda m: ("", []))
    text, offsets = _remap(text, offsets, BLOCK_MARKER_PATTERN, lambda m: ("", []))
    text, offsets = _remap(text, offsets, EMPHASIS_AND_TABLE_CHARS_PATTERN, lambda m: ("", []))
    text, offsets = _remap(text, offsets, WHITESPACE_RUN_PATTERN, lambda m: (" ", [m.start()]))
    return text, offsets


def _normalize_whitespace(text: str) -> str:
    return WHITESPACE_RUN_PATTERN.sub(" ", text)


def _remap(
    text: str,
    offsets: List[int],
    pattern: "re.Pattern[str]",
    build_replacement: Callable[["re.Match[str]"], Tuple[str, List[int]]],
) -> Tuple[str, List[int]]:
    """Apply `pattern` to `text` like .sub(), but keep `offsets` (source offset per char) aligned.
    `build_replacement` returns (replacement_text, replacement_indices), where the indices are
    positions in the CURRENT `text`/`offsets` -- `_normalize_markdown` chains several of these,
    each re-indexing into the previous step's output, not the original source."""
    out_chars: List[str] = []
    out_offsets: List[int] = []
    last_end = 0
    for match in pattern.finditer(text):
        out_chars.append(text[last_end:match.start()])
        out_offsets.extend(offsets[last_end:match.start()])
        replacement_text, replacement_indices = build_replacement(match)
        out_chars.append(replacement_text)
        out_offsets.extend(offsets[i] for i in replacement_indices)
        last_end = match.end()
    out_chars.append(text[last_end:])
    out_offsets.extend(offsets[last_end:])
    return "".join(out_chars), out_offsets


def _line_at(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _find_all(haystack: str, needle: str) -> List[int]:
    if not needle:
        return []
    positions = []
    start = 0
    while True:
        idx = haystack.find(needle, start)
        if idx == -1:
            break
        positions.append(idx)
        start = idx + 1
    return positions


def _filter_by_context(text: str, positions: List[int], quote: str, prefix: str, suffix: str) -> List[int]:
    if not prefix and not suffix:
        return positions
    matches = []
    for pos in positions:
        before = text[max(0, pos - len(prefix)):pos]
        after = text[pos + len(quote):pos + len(quote) + len(suffix)]
        if (not prefix or before.endswith(prefix)) and (not suffix or after.startswith(suffix)):
            matches.append(pos)
    return matches or positions


def _filter_by_heading(source: str, offsets: List[int], positions: List[int], heading_path: List[str]) -> List[int]:
    if not heading_path:
        return positions
    lines = source.splitlines()
    matches = [pos for pos in positions if _heading_path_at(lines, _line_at(source, offsets[pos])) == heading_path]
    return matches or positions


def _heading_path_at(lines: List[str], line_no: int) -> List[str]:
    path: List[str] = []
    depth = None
    for i in range(line_no - 1, -1, -1):
        match = HEADING_PATTERN.match(lines[i])
        if not match:
            continue
        level = len(match.group(1))
        if depth is not None and level >= depth:
            continue
        path.insert(0, match.group(2).strip())
        depth = level
        if level == 1:
            break
    return path
