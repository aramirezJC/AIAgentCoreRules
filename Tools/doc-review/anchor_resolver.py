"""Resolve comment anchors (text or diagram) against the current source files.

An anchor stored in the sidecar may point at text or a diagram element the agent has since
edited, moved, or renamed. These functions re-find the anchor in the live sources and report it
as a line number, or as orphaned/ambiguous when it can no longer be pinned down confidently.
See LocalDocReview_TDD.md, Edge Cases E1-E4 and E11.
"""
import re
from pathlib import Path
from typing import Dict, List

INLINE_MARKER_PATTERNS = {
    ".md": re.compile(r"<!--\s*@CLAUDE:\s*(.*?)-->", re.DOTALL),
    ".mmd": re.compile(r"%%\s*@CLAUDE:\s*(.*)"),
}

TAG_PATTERN = re.compile(r"<[^>\n]+>")
HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.*)$")


def resolve_text_anchor(base_dir: Path, anchor: Dict) -> Dict:
    """Re-find a text anchor (quote/prefix/suffix/heading_path) in its source file."""
    file_path = base_dir / anchor["file"]
    quote = anchor.get("quote", "")
    heading_path = anchor.get("heading_path", [])
    if not file_path.is_file():
        return {"status": "orphaned", "quote": quote, "heading_path": heading_path}

    text = file_path.read_text()
    positions = _find_all(text, quote)
    if not positions:
        stripped = _strip_tags(text)
        positions = _find_all(stripped, quote)
        text = stripped if positions else text

    if not positions:
        return {"status": "orphaned", "quote": quote, "heading_path": heading_path}

    if len(positions) > 1:
        positions = _filter_by_context(text, positions, quote, anchor.get("prefix", ""), anchor.get("suffix", ""))

    if len(positions) > 1:
        positions = _filter_by_heading(text, positions, anchor.get("heading_path", []))

    if len(positions) == 1:
        return {"status": "resolved", "file": anchor["file"], "line": _line_at(text, positions[0])}

    return {
        "status": "ambiguous",
        "file": anchor["file"],
        "candidate_lines": [_line_at(text, pos) for pos in positions],
    }


def resolve_diagram_anchor(base_dir: Path, anchor: Dict) -> Dict:
    """Re-find a diagram anchor: source_id, else label (+ occurrence_index), else orphan."""
    file_path = base_dir / anchor["file"]
    label = anchor.get("label")
    source_id = anchor.get("source_id")
    if not file_path.is_file():
        return {"status": "orphaned", "quote": label or source_id or ""}

    lines = file_path.read_text().splitlines()

    source_id = anchor.get("source_id")
    if source_id:
        pattern = re.compile(r"\b" + re.escape(source_id) + r"\b")
        hits = [i + 1 for i, line in enumerate(lines) if pattern.search(line)]
        if hits:
            return {"status": "resolved", "file": anchor["file"], "line": hits[0]}

    if label:
        hits = [i + 1 for i, line in enumerate(lines) if label in line]
        occurrence_index = anchor.get("occurrence_index")
        if occurrence_index is not None:
            if 0 <= occurrence_index < len(hits):
                return {"status": "resolved", "file": anchor["file"], "line": hits[occurrence_index]}
        elif hits:
            return {"status": "resolved", "file": anchor["file"], "line": hits[0]}

    return {"status": "orphaned", "quote": label or source_id or ""}


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


def _strip_tags(text: str) -> str:
    return TAG_PATTERN.sub("", text)


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


def _filter_by_heading(text: str, positions: List[int], heading_path: List[str]) -> List[int]:
    if not heading_path:
        return positions
    lines = text.splitlines()
    matches = [pos for pos in positions if _heading_path_at(lines, _line_at(text, pos)) == heading_path]
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
