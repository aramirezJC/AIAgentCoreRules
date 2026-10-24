#!/usr/bin/env python3
"""Thin alias: render local .mmd Mermaid sources via doc_review.py's static mode.

Usage:
    python3 mermaid_preview.py <file1.mmd> [file2.mmd ...] [--output PATH] [--open]

Superseded by doc_review.py (Tools/doc-review/), which adds a live server, markdown tabs, and a
comment sidecar on top of the same tabbed-diagram preview. This script forwards to its static
mode so the original CLI keeps working for any existing caller. See LocalDocReview_TDD.md,
"Supersedes mermaid_preview.py".
"""
import argparse
import subprocess
import sys
from pathlib import Path

DOC_REVIEW = Path(__file__).resolve().parent.parent / "doc-review" / "doc_review.py"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("files", nargs="+", help="One or more .mmd files to render as tabs")
    parser.add_argument("--output", help="Output .html path (default: alongside the first input file)")
    parser.add_argument("--open", action="store_true", help="Open the result in the default browser")
    args = parser.parse_args()

    output_path = args.output or str(Path(args.files[0]).parent / "_mermaid_preview.html")
    command = [sys.executable, str(DOC_REVIEW), "serve", *args.files, "--static", "--output", output_path]
    if args.open:
        command.append("--open")
    sys.exit(subprocess.run(command).returncode)


if __name__ == "__main__":
    main()
