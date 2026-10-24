#!/usr/bin/env python3
"""Export a Documentation/ folder as Confluence-ready Markdown.

The pages are written for Obsidian: [[wikilinks]], a "Source files" line and a navigation
footer. Confluence's Markdown import shows wikilinks as literal text and cannot resolve repo
file links, so this writes a cleaned copy:

    [[target|label]] / [[target\\|label]]  ->  label
    [[target#Heading]]                     ->  Heading
    [[target]]                             ->  target (file name only)
    "**Source files:** ..." line           ->  removed
    trailing "---" + navigation footer     ->  removed

Usage:
    python3 export_confluence.py <Documentation dir> [--out <dir>]

--out defaults to <Documentation dir>/../GitIgnoreConfluenceExport. The source pages are never
modified. Exits non-zero if the input folder has no .md files.
"""

import argparse
import os
import re
import sys

WIKILINK = re.compile(r"\[\[([^\]]+)\]\]")
SOURCE_LINE = re.compile(r"^\*\*Source files:\*\*.*$\n?", re.M)
NAV_FOOTER = re.compile(r"\n---\n\n[^\n]*\[\[00_Overview[^\n]*\n*\Z")


def label_for(inner):
    target, sep, label = inner.replace("\\|", "|").partition("|")
    if sep:
        return label
    page, _, heading = target.partition("#")
    return heading or os.path.basename(page)


def clean(text):
    text = NAV_FOOTER.sub("\n", text)
    text = SOURCE_LINE.sub("", text)
    text = WIKILINK.sub(lambda match: label_for(match.group(1)), text)
    return re.sub(r"\n{3,}", "\n\n", text).rstrip() + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("docs")
    parser.add_argument("--out")
    args = parser.parse_args()
    docs = os.path.abspath(args.docs)
    out = os.path.abspath(args.out or os.path.join(os.path.dirname(docs), "GitIgnoreConfluenceExport"))
    pages = sorted(name for name in os.listdir(docs) if name.endswith(".md"))
    if not pages:
        print("No .md files in %s" % docs)
        return 1
    os.makedirs(out, exist_ok=True)
    for name in pages:
        with open(os.path.join(docs, name)) as handle:
            text = clean(handle.read())
        with open(os.path.join(out, name), "w") as handle:
            handle.write(text)
    print("%d pages -> %s" % (len(pages), out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
