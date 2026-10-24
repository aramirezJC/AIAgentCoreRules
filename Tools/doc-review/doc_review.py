#!/usr/bin/env python3
"""LocalDocReview CLI -- serve a doc + diagrams for local review, list ready comments, reply.

See LocalDocReview_TDD.md for the full design. Subcommands:
    serve    <doc.md> [<diagram.mmd> ...] [--port N] [--static [--output PATH] [--open]]
    comments <doc.md> [--status open|ready|addressed|resolved|all] [--json]
    reply    <doc.md> <thread_id> "<message>" [--status addressed]
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List

from anchor_resolver import resolve_diagram_anchor, resolve_text_anchor, scan_inline_markers
from review_server import render_static, serve_doc
from sidecar_store import SidecarStore

QUOTE_TRUNCATE_LENGTH = 60
MMDC_VALIDATION_TIMEOUT_SECONDS = 30


class DiagramValidationError(Exception):
    pass


def cmd_serve(args: argparse.Namespace) -> None:
    paths = [Path(args.doc)] + [Path(p) for p in args.diagrams]
    if args.static:
        output_path = Path(args.output) if args.output else None
        render_static(paths, output_path=output_path, open_browser=args.open)
    else:
        serve_doc(paths, port=args.port, open_browser=args.open)


def cmd_comments(args: argparse.Namespace) -> None:
    doc_path = Path(args.doc)
    base_dir = doc_path.parent
    data = SidecarStore(doc_path).load()
    threads = data["threads"]
    if args.status != "all":
        threads = [thread for thread in threads if thread["status"] == args.status]

    resolved = [_resolve_thread(base_dir, thread) for thread in threads]
    markers = scan_inline_markers(base_dir, _marker_candidate_files(doc_path, data["threads"]))

    if args.json:
        print(json.dumps({"threads": resolved, "inline_markers": markers}, indent=2))
    else:
        _print_text(resolved, markers)


def cmd_reply(args: argparse.Namespace) -> None:
    doc_path = Path(args.doc)
    store = SidecarStore(doc_path)
    try:
        if args.status == "addressed":
            _validate_if_diagram(doc_path.parent, store, args.thread_id)
        store.add_reply(args.thread_id, "agent", args.message)
        if args.status:
            store.set_status(args.thread_id, args.status, "agent")
    except (PermissionError, KeyError, DiagramValidationError) as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)

    suffix = f", status={args.status}" if args.status else ""
    print(f"replied to {args.thread_id}{suffix}")


def _validate_if_diagram(base_dir: Path, store: SidecarStore, thread_id: str) -> None:
    # Edge Case E8 / Best Practices: a broken diagram edit must never be marked addressed.
    threads = store.load()["threads"]
    thread = next((t for t in threads if t["id"] == thread_id), None)
    if thread is None:
        raise KeyError(f"no thread {thread_id!r}")
    anchor = thread["anchor"]
    if anchor["kind"] == "diagram":
        _validate_diagram(base_dir / anchor["file"])


def _validate_diagram(file_path: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        try:
            result = subprocess.run(
                ["npx", "--yes", "@mermaid-js/mermaid-cli", "-i", str(file_path), "-o", str(Path(tmp) / "check.svg")],
                capture_output=True,
                text=True,
                timeout=MMDC_VALIDATION_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.TimeoutExpired) as e:
            raise DiagramValidationError(f"could not run mermaid-cli to validate {file_path}: {e}") from e

    if result.returncode != 0:
        raise DiagramValidationError(f"{file_path} failed mermaid validation:\n{result.stderr.strip()}")


def _resolve_thread(base_dir: Path, thread: Dict) -> Dict:
    anchor = thread["anchor"]
    if anchor["kind"] == "text":
        resolution = resolve_text_anchor(base_dir, anchor)
        quote = anchor.get("quote", "")
    else:
        resolution = resolve_diagram_anchor(base_dir, anchor)
        quote = anchor.get("label") or anchor.get("source_id", "")
    return {"id": thread["id"], "status": thread["status"], "quote": quote, "resolution": resolution}


def _marker_candidate_files(doc_path: Path, threads: List[Dict]) -> List[str]:
    # comments takes only <doc>, so marker scanning auto-discovers diagrams via the project's
    # own Diagrams/ convention (ConfluenceDocs.md) rather than requiring them to be re-listed;
    # any other anchored file is picked up once a thread has pointed at it.
    files = {doc_path.name}
    diagrams_dir = doc_path.parent / "Diagrams"
    if diagrams_dir.is_dir():
        files.update(str(p.relative_to(doc_path.parent)) for p in diagrams_dir.glob("*.mmd"))
    files.update(thread["anchor"]["file"] for thread in threads)
    return sorted(files)


def _print_text(resolved: List[Dict], markers: List[Dict]) -> None:
    for item in resolved:
        resolution = item["resolution"]
        quote = _truncate(item["quote"])
        if resolution["status"] == "resolved":
            print(f'{resolution["file"]}:{resolution["line"]} [{item["status"]}] {item["id"]}: {quote}')
        elif resolution["status"] == "ambiguous":
            lines = ", ".join(str(line) for line in resolution["candidate_lines"])
            print(f'AMBIGUOUS {item["id"]} [{item["status"]}] "{quote}" -- candidate lines: {lines}')
        else:
            heading = " > ".join(resolution.get("heading_path") or [])
            suffix = f" (was under: {heading})" if heading else ""
            print(f'ORPHANED {item["id"]} [{item["status"]}] "{quote}"{suffix}')
    for marker in markers:
        print(f'[inline-marker] {marker["file"]}:{marker["line"]}: {marker["text"]}')


def _truncate(text: str, limit: int = QUOTE_TRUNCATE_LENGTH) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def main() -> None:
    parser = argparse.ArgumentParser(prog="doc_review.py", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve_parser = subparsers.add_parser("serve", help="Render a doc + diagrams, live or --static")
    serve_parser.add_argument("doc")
    serve_parser.add_argument("diagrams", nargs="*")
    serve_parser.add_argument("--port", type=int, default=None)
    serve_parser.add_argument("--static", action="store_true")
    serve_parser.add_argument("--output")
    serve_parser.add_argument("--open", action="store_true")
    serve_parser.set_defaults(func=cmd_serve)

    comments_parser = subparsers.add_parser("comments", help="List comment threads resolved to file:line")
    comments_parser.add_argument("doc")
    comments_parser.add_argument("--status", choices=["open", "ready", "addressed", "resolved", "all"], default="all")
    comments_parser.add_argument("--json", action="store_true")
    comments_parser.set_defaults(func=cmd_comments)

    reply_parser = subparsers.add_parser("reply", help="Add an agent reply, optionally setting status")
    reply_parser.add_argument("doc")
    reply_parser.add_argument("thread_id")
    reply_parser.add_argument("message")
    reply_parser.add_argument("--status", choices=["open", "ready", "addressed", "resolved"], default=None)
    reply_parser.set_defaults(func=cmd_reply)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
