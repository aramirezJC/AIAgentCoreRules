"""retro.md -> retro.html, and proposal status tracking for /end-session retrospectives.

retro.md stays the source of truth. Each proposal's status lives in its "## Applied" section,
one line per proposal, in the shape session_meta_report.py already reads:

    - #1 applied: <file> — <what changed>
    - #2 skipped: <reason>
    - #3 pending: <optional note>

mark() rewrites one of those lines; render() turns the whole retro into a standalone HTML page
(no external assets) with a progress bar and a status badge on every proposal. A page opened
from disk cannot write back, so each open proposal carries a button that copies the command
that marks it.

Dependency-free: imported by session_lifecycle.py.
"""

import html
import json
import os
import re

STATUSES = ["applied", "skipped", "pending"]
APPLIED_LINE = re.compile(r"^\s*[-*]\s*#(\d+)\s+(applied|skipped|pending)\b:?\s*(.*)$", re.I)


# ---------------------------------------------------------------- parse

def split_sections(text):
    """(title, [(heading, body)]) for the '# ' title and each '## ' section, in order."""
    title, sections, heading, body = "", [], None, []
    for line in text.splitlines():
        if line.startswith("# ") and not title and heading is None:
            title = line[2:].strip()
        elif line.startswith("## "):
            if heading is not None:
                sections.append((heading, "\n".join(body).strip("\n")))
            heading, body = line[3:].strip(), []
        elif heading is not None:
            body.append(line)
    if heading is not None:
        sections.append((heading, "\n".join(body).strip("\n")))
    return title, sections


def section(sections, name):
    for heading, body in sections:
        if heading.lower() == name.lower():
            return body
    return None


def split_row(line):
    """Cells of a Markdown table row; a pipe inside `code` does not split."""
    row = line.strip()
    row = row[1:] if row.startswith("|") else row
    row = row[:-1] if row.endswith("|") else row
    cells, current, in_code = [], "", False
    for char in row:
        if char == "`":
            in_code = not in_code
        if char == "|" and not in_code:
            cells.append(current.strip())
            current = ""
        else:
            current += char
    cells.append(current.strip())
    return cells


def is_separator(line):
    return bool(re.match(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$", line))


def proposals(sections):
    """Rows of the Proposed changes table: [{n, file, change, why}]."""
    body = section(sections, "Proposed changes") or ""
    rows = []
    for line in body.splitlines():
        if not line.strip().startswith("|") or is_separator(line):
            continue
        cells = split_row(line)
        number = re.match(r"^#?\s*(\d+)$", cells[0]) if cells else None
        if not number:
            continue   # header row
        cells += [""] * (4 - len(cells))
        rows.append({"n": int(number.group(1)), "file": cells[1], "change": cells[2], "why": cells[3]})
    return rows


def applied(sections):
    """{n: (status, detail)} from the Applied section."""
    result = {}
    for line in (section(sections, "Applied") or "").splitlines():
        match = APPLIED_LINE.match(line)
        if match:
            result[int(match.group(1))] = (match.group(2).lower(), match.group(3).strip())
    return result


def statuses(text):
    """[{n, file, change, why, status, detail}] — a proposal with no Applied line is pending."""
    _title, sections = split_sections(text)
    recorded = applied(sections)
    items = []
    for proposal in proposals(sections):
        status, detail = recorded.get(proposal["n"], ("pending", ""))
        items.append(dict(proposal, status=status, detail=detail))
    return items


# ---------------------------------------------------------------- mark

def mark(text, number, status, detail=None):
    """retro.md text with proposal #number set to status. Creates the Applied section, with a
    pending line for every other proposal, when it is missing. detail=None keeps the old note
    only when the status is unchanged; a note like "awaiting engineer decision" must not survive
    the decision."""
    if status not in STATUSES:
        raise ValueError("status must be one of %s" % ", ".join(STATUSES))
    _title, sections = split_sections(text)
    known = [p["n"] for p in proposals(sections)]
    if number not in known:
        raise ValueError("retro has no proposal #%d (proposals: %s)" % (number, ", ".join("#%d" % n for n in known) or "none"))
    recorded = applied(sections)
    if detail is None:
        old_status, old_detail = recorded.get(number, ("pending", ""))
        detail = old_detail if old_status == status else ""
    new_line = "- #%d %s%s" % (number, status, (": " + detail) if detail else "")

    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if line.strip().lower() == "## applied"), None)
    if start is None:
        while lines and not lines[-1].strip():
            lines.pop()
        lines += ["", "## Applied"]
        lines += [new_line if n == number else "- #%d pending" % n for n in known]
        return "\n".join(lines) + "\n"
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    for i in range(start + 1, end):
        match = APPLIED_LINE.match(lines[i])
        if match and int(match.group(1)) == number:
            lines[i] = new_line
            return "\n".join(lines) + "\n"
    # No line yet for this proposal: insert in number order, after the last numbered line before it.
    insert_at = start + 1
    for i in range(start + 1, end):
        match = APPLIED_LINE.match(lines[i])
        if match and int(match.group(1)) < number:
            insert_at = i + 1
        elif lines[i].strip().lower() == "- none proposed":
            lines[i] = ""
    lines.insert(insert_at, new_line)
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- markdown -> html

def inline(text):
    """Escape, then render `code`, **bold**, _italic_ / *italic* and [links](url)."""
    # Code spans become placeholders first, so **bold** may wrap `code` and code is never formatted.
    codes = []

    def stash(match):
        codes.append("<code>%s</code>" % html.escape(match.group(1)))
        return "\x00%d\x00" % (len(codes) - 1)

    text = html.escape(re.sub(r"`([^`]*)`", stash, text), quote=False)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", text)
    text = re.sub(r"(?<![\w])_(?!\s)(.+?)(?<!\s)_(?![\w])", r"<em>\1</em>", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2">\1</a>', text)
    return re.sub(r"\x00(\d+)\x00", lambda match: codes[int(match.group(1))], text)


def blocks(body):
    """Minimal Markdown block renderer for retro sections: ### headings, tables, bullet and
    numbered lists (indented lines continue an item), fenced code and paragraphs."""
    out, lines, i = [], body.splitlines(), 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
        elif stripped.startswith("```"):
            code, i = [], i + 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            out.append("<pre><code>%s</code></pre>" % html.escape("\n".join(code)))
            i += 1
        elif stripped.startswith("#"):
            level = min(len(stripped) - len(stripped.lstrip("#")) + 1, 6)
            out.append("<h%d>%s</h%d>" % (level, inline(stripped.lstrip("#").strip()), level))
            i += 1
        elif stripped.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                if not is_separator(lines[i]):
                    rows.append(split_row(lines[i]))
                i += 1
            head, rest = rows[0], rows[1:]
            table = ["<div class=\"scroll\"><table><thead><tr>"]
            table += ["<th>%s</th>" % inline(cell) for cell in head]
            table.append("</tr></thead><tbody>")
            for row in rest:
                table.append("<tr>%s</tr>" % "".join("<td>%s</td>" % inline(cell) for cell in row))
            table.append("</tbody></table></div>")
            out.append("".join(table))
        elif re.match(r"^\s*([-*]|\d+\.)\s+", line):
            ordered = bool(re.match(r"^\s*\d+\.", line))
            items = []
            while i < len(lines):
                item = re.match(r"^\s*([-*]|\d+\.)\s+(.*)$", lines[i])
                if item and (bool(re.match(r"^\s*\d+\.", lines[i])) == ordered):
                    items.append(item.group(2))
                elif items and lines[i].startswith((" ", "\t")) and lines[i].strip():
                    items[-1] += " " + lines[i].strip()
                else:
                    break
                i += 1
            tag = "ol" if ordered else "ul"
            out.append("<%s>%s</%s>" % (tag, "".join("<li>%s</li>" % inline(t) for t in items), tag))
        else:
            para = []
            while i < len(lines) and lines[i].strip() and not re.match(r"^\s*(\||#|```|[-*]\s|\d+\.\s)", lines[i]):
                para.append(lines[i].strip())
                i += 1
            out.append("<p>%s</p>" % inline(" ".join(para)))
    return "\n".join(out)


# ---------------------------------------------------------------- render

def mark_command(script_path, folder, number, status):
    return 'python3 "%s" retro --folder "%s" --mark %d --status %s --note "<what changed>"' % (
        script_path, folder, number, status)


def proposal_cards(items, script_path, folder):
    if not items:
        return "<p class=\"muted\">No proposals.</p>"
    cards = []
    for item in items:
        status = item["status"]
        command = mark_command(script_path, folder, item["n"], "applied")
        actions = ""
        if status == "pending":
            actions = ('<div class="actions"><button type="button" data-copy="%s">Copy “mark applied” command</button>'
                       '<span class="copied" aria-live="polite"></span></div>') % html.escape(command, quote=True)
        detail = ('<p class="detail"><span class="label">%s:</span> %s</p>' % (status.capitalize(), inline(item["detail"]))
                  if item["detail"] else "")
        cards.append(
            '<article class="card %(status)s" data-status="%(status)s">'
            '<header><span class="num">#%(n)d</span><span class="pill %(status)s">%(label)s</span>'
            '<span class="file">%(file)s</span></header>'
            '<p class="change">%(change)s</p>'
            '<p class="why"><span class="label">Why:</span> %(why)s</p>%(detail)s%(actions)s</article>' % {
                "status": status, "n": item["n"], "label": {"applied": "✓ applied", "skipped": "– skipped",
                                                            "pending": "○ open"}[status],
                "file": inline(item["file"]), "change": inline(item["change"]), "why": inline(item["why"]),
                "detail": detail, "actions": actions})
    return "\n".join(cards)


def render(retro_path, script_path, metrics_name="metrics.md"):
    """Write retro.html next to retro.md; returns its path."""
    with open(retro_path, errors="replace") as handle:
        text = handle.read()
    folder = os.path.dirname(os.path.abspath(retro_path))
    title, sections = split_sections(text)
    items = statuses(text)
    counts = {s: sum(1 for item in items if item["status"] == s) for s in STATUSES}
    resolved = counts["applied"] + counts["skipped"]
    percent = int(round(100.0 * resolved / len(items))) if items else 100

    # The tracked proposals go right after Outcome on the page; retro.md keeps its own order.
    proposed = [s for s in sections if s[0].lower() == "proposed changes"]
    others = [s for s in sections if s[0].lower() != "proposed changes"]
    split = 1 if others and others[0][0].lower() == "outcome" else 0
    nav, body = [], []
    for index, (heading, content) in enumerate(others[:split] + proposed + others[split:]):
        anchor = "s%d" % index
        if heading.lower() == "applied":
            continue   # shown as the badges on each proposal
        nav.append('<a href="#%s">%s</a>' % (anchor, html.escape(heading)))
        if heading.lower() == "proposed changes":
            inner = proposal_cards(items, script_path, folder)
        else:
            inner = blocks(content) or "<p class=\"muted\">none</p>"
        body.append('<section id="%s"><h2>%s</h2>%s</section>' % (anchor, inline(heading), inner))

    metrics_link = ('<a href="%s">metrics.md</a>' % metrics_name
                    if os.path.isfile(os.path.join(folder, metrics_name)) else "")
    page = TEMPLATE
    for key, value in {
        "{{TITLE}}": html.escape(title or "Retrospective"),
        "{{HEADING}}": inline(title or "Retrospective"),
        "{{FOLDER}}": html.escape(os.path.basename(folder)),
        "{{METRICS}}": metrics_link,
        "{{PERCENT}}": str(percent),
        "{{SUMMARY}}": ("%d of %d proposals resolved · %d applied · %d skipped · %d open"
                        % (resolved, len(items), counts["applied"], counts["skipped"], counts["pending"])
                        if items else "No proposals"),
        "{{NAV}}": "".join(nav),
        "{{BODY}}": "\n".join(body),
        "{{STATE}}": json.dumps({"open": counts["pending"]}),
    }.items():
        page = page.replace(key, value)
    out_path = os.path.join(folder, "retro.html")
    with open(out_path, "w") as handle:
        handle.write(page)
    return out_path


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{TITLE}}</title>
<style>
:root{--bg:#f7f7f5;--panel:#fff;--text:#1d1d1f;--muted:#6b6b70;--line:#e3e3e0;--code:#f0f0ec;
  --ok:#1f7a4d;--ok-bg:#e3f4ea;--skip:#77767b;--skip-bg:#ececea;--open:#a35a00;--open-bg:#fdf0dc;--accent:#2f5bd3}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#151517;--panel:#1e1e21;--text:#ececef;
  --muted:#9a9aa1;--line:#2e2e33;--code:#2a2a2f;--ok:#5fd394;--ok-bg:#183424;--skip:#a3a3aa;--skip-bg:#2a2a2e;
  --open:#f0b25a;--open-bg:#3a2a12;--accent:#8aa8ff}}
:root[data-theme="dark"]{--bg:#151517;--panel:#1e1e21;--text:#ececef;--muted:#9a9aa1;--line:#2e2e33;--code:#2a2a2f;
  --ok:#5fd394;--ok-bg:#183424;--skip:#a3a3aa;--skip-bg:#2a2a2e;--open:#f0b25a;--open-bg:#3a2a12;--accent:#8aa8ff}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
main{max-width:980px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:1.6rem;margin:0 0 4px}h2{font-size:1.15rem;margin:0 0 12px}h3,h4{font-size:1rem;margin:16px 0 8px}
a{color:var(--accent)}
.meta{color:var(--muted);font-size:.85rem;margin-bottom:16px}
.progress{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin-bottom:16px}
.bar{height:8px;background:var(--line);border-radius:4px;overflow:hidden;margin-top:8px}
.bar span{display:block;height:100%;background:var(--ok)}
nav{display:flex;flex-wrap:wrap;gap:6px 14px;margin-bottom:20px;font-size:.9rem}
section{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px;margin-bottom:16px}
.scroll{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:.9rem}
th,td{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}
th{color:var(--muted);font-weight:600}
code{background:var(--code);padding:1px 4px;border-radius:4px;font-size:.85em;word-break:break-word}
pre{background:var(--code);padding:10px;border-radius:6px;overflow-x:auto}pre code{padding:0}
ul,ol{padding-left:22px}li{margin:4px 0}
.muted{color:var(--muted)}
.toolbar{display:flex;justify-content:flex-end;margin:-4px 0 10px;font-size:.85rem;color:var(--muted)}
.card{border:1px solid var(--line);border-left:4px solid var(--open);border-radius:8px;padding:12px 14px;margin-bottom:10px}
.card.applied{border-left-color:var(--ok)}.card.skipped{border-left-color:var(--skip)}
.card.applied .change,.card.skipped .change{color:var(--muted)}
.card header{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin-bottom:6px}
.num{font-weight:700}
.file{font-size:.85rem;color:var(--muted);word-break:break-word}
.pill{font-size:.75rem;font-weight:600;padding:2px 8px;border-radius:999px;white-space:nowrap}
.pill.applied{background:var(--ok-bg);color:var(--ok)}.pill.skipped{background:var(--skip-bg);color:var(--skip)}
.pill.pending{background:var(--open-bg);color:var(--open)}
.card p{margin:4px 0}.label{font-weight:600}.why,.detail{font-size:.9rem}
.actions{margin-top:8px;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
button{font:inherit;font-size:.8rem;padding:4px 10px;border-radius:6px;border:1px solid var(--line);
  background:var(--bg);color:var(--text);cursor:pointer}
button:hover{border-color:var(--accent)}
.copied{font-size:.8rem;color:var(--ok)}
body.hide-resolved .card.applied,body.hide-resolved .card.skipped{display:none}
</style>
</head>
<body>
<main>
<h1>{{HEADING}}</h1>
<div class="meta">{{FOLDER}} {{METRICS}}</div>
<div class="progress"><strong>{{SUMMARY}}</strong><div class="bar"><span style="width:{{PERCENT}}%"></span></div></div>
<nav>{{NAV}}</nav>
{{BODY}}
<p class="muted">Rendered from retro.md. Mark a proposal with
<code>session_lifecycle.py retro --mark &lt;n&gt; --status applied|skipped|pending</code>; the page re-renders.</p>
</main>
<script>
(function(){
  var state={{STATE}};
  var section=document.querySelector(".card")&&document.querySelector(".card").parentNode;
  if(section){
    var bar=document.createElement("div");bar.className="toolbar";
    var label=document.createElement("label");var box=document.createElement("input");box.type="checkbox";
    label.appendChild(box);label.appendChild(document.createTextNode(" Show open only ("+state.open+")"));
    bar.appendChild(label);section.insertBefore(bar,section.querySelector(".card"));
    try{box.checked=localStorage.getItem("retro-hide-resolved")==="1";}catch(e){}
    var apply=function(){document.body.classList.toggle("hide-resolved",box.checked);
      try{localStorage.setItem("retro-hide-resolved",box.checked?"1":"0");}catch(e){}};
    box.addEventListener("change",apply);apply();
  }
  document.querySelectorAll("button[data-copy]").forEach(function(button){
    button.addEventListener("click",function(){
      var text=button.getAttribute("data-copy"),note=button.parentNode.querySelector(".copied");
      var done=function(ok){note.textContent=ok?"Copied — run it, or ask Claude to":"Copy failed: "+text;};
      if(navigator.clipboard){navigator.clipboard.writeText(text).then(function(){done(true);},function(){done(false);});}
      else{done(false);}
    });
  });
})();
</script>
</body>
</html>
"""
