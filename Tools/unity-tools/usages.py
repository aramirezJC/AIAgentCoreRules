#!/usr/bin/env python3
"""
Map every use of a type across the project, partitioned by what each site actually does.

Built for interface-segregation work: before splitting an interface you need to know
which call sites only read and which call the members you intend to move out. Answering
that with raw grep takes many passes and returns a lot of lines you have to classify by
hand; this does the classification and prints a compact table.

Usage
  usages.py IEventManager
  usages.py IEventManager --members FetchEvents,FetchEvent,RefreshEventStatus
  usages.py IEventManager --members FetchEvents --full
  usages.py IPrizeManager --assembly Assembly-CSharp

Options
  --members a,b,c  Split call sites into those that invoke one of these members and
                   those that do not. Without this, every site is just listed.
  --full           List every read-only file instead of summarising per assembly.
  --assembly NAME  Restrict to one assembly.
  --project PATH   Unity project root (default: walk up from cwd).

Only files that belong to a generated .csproj are searched, so results are limited to
code that actually compiles. Orphaned project files are ignored.

The buckets are lexical, not semantic: DECLARES matches a type declaration or a base
list, CALLS matches `.Member(` or `Member(` on a line that also mentions the symbol or
a plausible local. Treat it as a fast triage pass, not a compiler-grade reference index.
"""

import argparse
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _unityproj import Project, ProjectError, find_project_root  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("symbol")
    parser.add_argument("--members", default="")
    parser.add_argument("--assembly", default=None)
    parser.add_argument("--project", default=None)
    parser.add_argument("--full", action="store_true")
    args = parser.parse_args()

    try:
        root = os.path.abspath(args.project) if args.project else find_project_root()
        project = Project(root)
    except ProjectError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2

    symbol = args.symbol
    members = [m.strip() for m in args.members.split(",") if m.strip()]

    sym_re = re.compile(r"\b%s\b" % re.escape(symbol))
    decl_re = re.compile(
        r"(\b(?:interface|class|struct)\s+%s\b)|(:\s*[^{\n]*\b%s\b)"
        % (re.escape(symbol), re.escape(symbol)))
    member_res = {m: re.compile(r"\b%s\s*\(" % re.escape(m)) for m in members}

    index = project.file_to_assemblies()
    declares, calls, reads = [], [], []

    for path, asms in index.items():
        asm = asms[0]
        if args.assembly and asm != args.assembly:
            continue
        try:
            with open(path, "r", errors="replace") as handle:
                text = handle.read()
        except OSError:
            continue
        if not sym_re.search(text):
            continue

        rel = os.path.relpath(path, root)
        lines = text.splitlines()

        hits = defaultdict(list)
        for i, line in enumerate(lines, 1):
            for name, pattern in member_res.items():
                if pattern.search(line):
                    hits[name].append(i)

        if decl_re.search(text):
            declares.append((asm, rel))
        elif hits:
            calls.append((asm, rel, hits))
        else:
            reads.append((asm, rel))

    total = len(declares) + len(calls) + len(reads)
    asms_seen = {a for a, *_ in declares + calls + reads}
    print("%s — %d file(s) across %d assembl%s"
          % (symbol, total, len(asms_seen), "y" if len(asms_seen) == 1 else "ies"))
    if not total:
        return 0

    def group(rows):
        out = defaultdict(list)
        for row in rows:
            out[row[0]].append(row)
        return dict(sorted(out.items()))

    if declares:
        print("\nDECLARES / IMPLEMENTS (%d)" % len(declares))
        for asm, rows in group(declares).items():
            print("  %s" % asm)
            for _, rel in sorted(rows):
                print("    %s" % rel)

    if members:
        print("\nCALLS %s (%d)" % ("/".join(members), len(calls)))
        if not calls:
            print("  (none)")
        for asm, rows in group(calls).items():
            print("  %s" % asm)
            for _, rel, hits in sorted(rows, key=lambda r: r[1]):
                detail = "  ".join(
                    "%s:%s" % (m, ",".join(str(n) for n in ns[:4]))
                    for m, ns in sorted(hits.items()))
                print("    %-70s %s" % (rel, detail))

    label = "OTHER REFERENCES" if members else "REFERENCES"
    print("\n%s (%d)" % (label, len(reads)))
    for asm, rows in group(reads).items():
        if args.full:
            print("  %s" % asm)
            for _, rel in sorted(rows):
                print("    %s" % rel)
        else:
            print("  %-55s %d file(s)" % (asm, len(rows)))
    if reads and not args.full:
        print("  (pass --full to list them)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
