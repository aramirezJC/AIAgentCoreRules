"""Render a doc + its diagrams as a tabbed page, live (HTTP server) or once (--static).

Live mode binds to 127.0.0.1 only (hard-coded, no flag can change it) and serves the comment
API the browser UI will use (V1). Static mode is what mermaid_preview.py's thin alias calls --
same rendering, no server, no comments. See LocalDocReview_TDD.md Architecture and Best Practices.
"""
import functools
import html
import http.server
import json
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Dict, List, Optional

from anchor_resolver import resolve_thread
from progress_view import build_model, find_progress_file, pr_refresh_stamp, watched_paths
from sidecar_store import SidecarStore

MERMAID_CDN = "https://cdnjs.cloudflare.com/ajax/libs/mermaid/11.15.0/mermaid.min.js"
MARKED_CDN = "https://cdnjs.cloudflare.com/ajax/libs/marked/18.1.1/lib/marked.umd.min.js"
SVG_PAN_ZOOM_CDN = "https://cdn.jsdelivr.net/npm/svg-pan-zoom@3.6.1/dist/svg-pan-zoom.min.js"
STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_CONTENT_TYPE_BY_SUFFIX = {".js": "text/javascript", ".css": "text/css"}
POLL_INTERVAL_MS = 1000

PAGE_TEMPLATE = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Doc review{live_suffix}</title>
<script src="{marked_cdn}"></script>
<script src="{mermaid_cdn}"></script>
<script src="{panzoom_cdn}"></script>
{live_head_extra}
<style>
  /* Deliberately dark-only: color-scheme: light dark previously let the browser apply its own
     dark-mode default TEXT color to marked's unstyled output while this CSS kept light-mode
     BACKGROUNDS, producing white-on-white. Declaring dark only, with every color explicit below,
     removes that mismatch instead of fighting it. */
  :root {{ color-scheme: dark; }}
  html, body {{ height: 100%; margin: 0; }}
  body {{ font-family: -apple-system, system-ui, sans-serif; background: #15171c; color: #e4e6eb;
          display: flex; flex-direction: column; }}
  header {{ padding: 12px 16px; background: #1f2430; color: #eee; font-size: 14px; flex: none; }}
  header .hint {{ color: #9aa3b5; margin-left: 10px; }}
  .content-row {{ display: flex; flex: 1; min-height: 0; }}
  .main-column {{ display: flex; flex-direction: column; flex: 1; min-width: 0; }}
  .tabs {{ display: flex; gap: 4px; padding: 8px 16px 0; background: #1f2430; flex: none; }}
  .tab {{ background: #2a3040; color: #ccc; border: none; padding: 8px 14px; border-radius: 6px 6px 0 0;
          cursor: pointer; font-size: 13px; }}
  .tab.active {{ background: #20242e; color: #fff; font-weight: 600; }}
  .panel {{ display: none; flex: 1; min-height: 0; padding: 16px; box-sizing: border-box; overflow: auto; }}
  .panel.active {{ display: block; }}
  .diagram {{ background: #20242e; width: 100%; height: 100%; border-radius: 8px; box-shadow: 0 1px 4px rgba(0,0,0,.4);
              box-sizing: border-box; overflow: hidden; }}
  .diagram svg {{ width: 100%; height: 100%; }}
  .markdown {{ background: #20242e; color: #e4e6eb; max-width: 900px; margin: 0 auto; padding: 24px 32px;
               border-radius: 8px; box-shadow: 0 1px 4px rgba(0,0,0,.4); box-sizing: border-box; line-height: 1.55; }}
  .markdown h1, .markdown h2, .markdown h3, .markdown h4 {{ color: #fff; border-bottom: 1px solid #333944; padding-bottom: 6px; }}
  .markdown a {{ color: #6cb6ff; }}
  .markdown code {{ background: #2a303c; color: #f0c674; padding: 2px 5px; border-radius: 4px; font-size: 0.9em; }}
  .markdown pre {{ background: #181b22; padding: 12px 16px; border-radius: 6px; overflow-x: auto; }}
  .markdown pre code {{ background: none; padding: 0; color: #e4e6eb; }}
  .markdown table {{ border-collapse: collapse; width: 100%; margin: 12px 0; }}
  .markdown th, .markdown td {{ border: 1px solid #333944; padding: 6px 10px; text-align: left; }}
  .markdown th {{ background: #262b35; }}
  .markdown blockquote {{ border-left: 3px solid #4a5468; margin: 0; padding: 4px 16px; color: #b7bcc7; }}
  .markdown hr {{ border: none; border-top: 1px solid #333944; }}
  .error {{ color: #ff6b6b; font-family: monospace; white-space: pre-wrap; padding: 16px; }}
  /* Progress tab: green = done (same --ok green as retro_page.py's dark theme), red = gate still to pass. */
  .progress-view {{ --ok: #5fd394; --gate: #ff6b6b; --current: #6cb6ff; background: #20242e; color: #e4e6eb;
                    max-width: 900px; margin: 0 auto; padding: 24px 32px; border-radius: 8px;
                    box-shadow: 0 1px 4px rgba(0,0,0,.4); box-sizing: border-box; line-height: 1.5; }}
  .progress-view h1 {{ margin: 0 0 4px; font-size: 22px; color: #fff; }}
  .progress-view .meta {{ color: #9aa3b5; font-size: 13px; margin-bottom: 18px; }}
  .phase {{ border: 1px solid #333944; border-left: 4px solid #333944; border-radius: 6px; padding: 10px 14px; margin: 10px 0; }}
  .phase.completed {{ border-left-color: var(--ok); }}
  .phase.current {{ border-color: var(--current); border-left-color: var(--current); background: #23304a; }}
  .phase h2 {{ margin: 0; font-size: 16px; color: #fff; display: flex; align-items: center; gap: 8px; }}
  .phase .pill {{ font-size: 11px; font-weight: 600; padding: 1px 8px; border-radius: 10px; }}
  .phase .pill.current {{ background: var(--current); color: #10141c; }}
  .mark {{ display: inline-block; width: 1.2em; text-align: center; color: #5c6577; }}
  .mark.done {{ color: var(--ok); font-weight: 700; }}
  .mark.partial {{ color: #f0c674; }}
  .phase ul {{ list-style: none; margin: 6px 0 0; padding-left: 4px; font-size: 14px; }}
  .phase li.done {{ color: #b7bcc7; }}
  .phase .stage {{ margin: 8px 0 0 4px; font-size: 13px; color: #9aa3b5; font-weight: 600; }}
  .phase .stage + ul {{ padding-left: 16px; }}
  .gate {{ margin-top: 8px; font-size: 13px; color: #9aa3b5; }}
  .gate.pending {{ color: var(--gate); font-weight: 600; }}
  /* Implementation V-phases from the TDD: a Tasks and a PR notes collapsible each. */
  .dev-phase details {{ margin: 4px 0 0 20px; font-size: 13px; }}
  .dev-phase summary {{ cursor: pointer; color: #b7bcc7; }}
  .dev-phase .pr {{ margin: 6px 0 0 4px; }}
  .dev-phase .pr a {{ color: #6cb6ff; }}
  .dev-phase .pill.pr-state {{ background: #333944; color: #e4e6eb; }}
  .dev-phase .note {{ border-left: 2px solid #333944; margin: 6px 0 0 8px; padding: 2px 10px; }}
  .dev-phase .note-meta {{ color: #9aa3b5; font-size: 12px; }}
  .dev-phase .note-meta a {{ color: #9aa3b5; }}
  .dev-phase .note-body {{ white-space: pre-wrap; color: #e4e6eb; }}
  .dev-phase .empty {{ color: #5c6577; margin: 4px 0 0 4px; }}
</style>
</head>
<body>
<header>{header_text}
  <span class="hint">scroll/pinch to zoom on diagrams &middot; drag to pan &middot; bottom-left icons to reset</span>
</header>
<div class="content-row">
<div class="main-column">
<div class="tabs">
{tab_buttons}
</div>
{panels}
</div>
{live_sidebar_slot}
</div>
<script>
  mermaid.initialize({{ startOnLoad: false, theme: "dark" }});
  const tabKinds = {tab_kinds_js};
  const sources = {sources_js};
  const panZoomInstances = {{}};
  window.panZoomInstances = panZoomInstances; // read by static/diagram_anchors.js (live mode only)
  const renderedSourceFor = {{}};

  function renderMarkdown(id, src) {{
    const target = document.getElementById(id);
    try {{
      target.innerHTML = marked.parse(src);
    }} catch (err) {{
      // A failure here must not stop renderAll()'s forEach from reaching the other tabs.
      target.innerHTML = '<div class="error">' + (err && err.message ? err.message : err) + '</div>';
    }}
    document.dispatchEvent(new CustomEvent("docreview:rendered", {{ detail: {{ tabId: id }} }}));
  }}

  async function renderDiagram(id, src) {{
    const target = document.getElementById(id);
    const existing = panZoomInstances[id];
    const savedPan = existing ? existing.getPan() : null;
    const savedZoom = existing ? existing.getZoom() : null;
    const bodyChildrenBefore = new Set(document.body.children);
    try {{
      const {{ svg }} = await mermaid.render(id + "-svg", src);
      target.innerHTML = svg;
      const svgEl = target.querySelector("svg");
      svgEl.removeAttribute("width");
      svgEl.removeAttribute("height");
      const instance = svgPanZoom(svgEl, {{
        zoomEnabled: true, panEnabled: true, controlIconsEnabled: true,
        fit: true, center: true, minZoom: 0.2, maxZoom: 20,
      }});
      if (savedPan && savedZoom) {{
        instance.zoom(savedZoom);
        instance.pan(savedPan);
      }}
      panZoomInstances[id] = instance;
    }} catch (err) {{
      target.innerHTML = '<div class="error">' + (err && err.message ? err.message : err) + '</div>';
      delete panZoomInstances[id];
      // mermaid.render() can leave its own temporary rendering container behind in <body> when it
      // throws partway through (observed directly: a stray "d<id>-svg" div, duplicating the error
      // message outside this panel and -- worse -- stealing flex height from .content-row). Clean
      // up whatever appeared as a side effect of this call rather than guessing mermaid's naming.
      Array.from(document.body.children).forEach((el) => {{
        if (!bodyChildrenBefore.has(el)) {{
          el.remove();
        }}
      }});
    }}
    document.dispatchEvent(new CustomEvent("docreview:rendered", {{ detail: {{ tabId: id }} }}));
  }}

  function escapeHtml(text) {{
    const div = document.createElement("div");
    div.textContent = text == null ? "" : String(text);
    return div.innerHTML;
  }}

  function markHtml(state) {{
    const glyph = state === "done" ? "✓" : state === "partial" ? "~" : "○";
    return '<span class="mark ' + state + '">' + glyph + '</span>';
  }}

  function devPhaseHtml(dev) {{
    const done = dev.tasks.filter((task) => task.status === "done").length;
    const allDone = dev.tasks.length > 0 && done === dev.tasks.length;
    const parts = ['<div class="dev-phase"><div class="stage">' + markHtml(allDone ? "done" : "todo") + escapeHtml(dev.title) + '</div>',
      '<details data-key="' + escapeHtml(dev.key) + ':tasks"' + (dev.open ? ' open' : '') + '><summary>Tasks ('
        + done + '/' + dev.tasks.length + ')</summary><ul>'];
    dev.tasks.forEach((task) => {{
      parts.push('<li class="' + task.status + '">' + markHtml(task.status) + escapeHtml((task.id ? task.id + ' · ' : '') + task.title) + '</li>');
    }});
    const prs = dev.pull_requests || [];
    const noteCount = prs.reduce((sum, pr) => sum + pr.notes.length, 0);
    parts.push('</ul></details><details data-key="' + escapeHtml(dev.key) + ':prs"><summary>PR notes ('
      + prs.length + ' PR' + (prs.length === 1 ? '' : 's') + ', ' + noteCount + ' note' + (noteCount === 1 ? '' : 's') + ')</summary>');
    if (!prs.length) {{
      parts.push('<div class="empty">No PRs linked. Add <code>' + escapeHtml(dev.key) + ': [1234]</code> under <code>pull_requests:</code> in the progress file.</div>');
    }}
    prs.forEach((pr) => {{
      parts.push('<div class="pr"><a href="' + escapeHtml(pr.url) + '" target="_blank" rel="noopener">#' + escapeHtml(pr.number)
        + (pr.title ? ' ' + escapeHtml(pr.title) : '') + '</a>' + (pr.state ? ' <span class="pill pr-state">' + escapeHtml(pr.state) + '</span>' : ''));
      if (pr.error) parts.push('<div class="error">' + escapeHtml(pr.error) + '</div>');
      if (!pr.error && !pr.notes.length) parts.push('<div class="empty">No comments yet.</div>');
      pr.notes.forEach((note) => {{
        const where = note.location || note.kind + (note.state ? ' ' + note.state.toLowerCase() : '');
        const whereHtml = note.url ? '<a href="' + escapeHtml(note.url) + '" target="_blank" rel="noopener">' + escapeHtml(where) + '</a>' : escapeHtml(where);
        parts.push('<div class="note"><div class="note-meta">' + escapeHtml(note.author) + ' &middot; ' + escapeHtml(note.created_at.slice(0, 10))
          + ' &middot; ' + whereHtml + '</div><div class="note-body">' + escapeHtml(note.body) + '</div></div>');
      }});
      parts.push('</div>');
    }});
    parts.push('</details></div>');
    return parts.join("");
  }}

  function renderProgress(id, src) {{
    const target = document.getElementById(id);
    try {{
      const model = JSON.parse(src);
      const parts = ['<h1>' + escapeHtml(model.feature) + '</h1>',
        '<div class="meta">status: ' + escapeHtml(model.status) + ' &middot; updated ' + escapeHtml(model.updated_at)
          + (model.next ? '<br>next: ' + escapeHtml(model.next) : '') + '</div>'];
      model.phases.forEach((phase) => {{
        const classes = ["phase"];
        if (phase.completed) classes.push("completed");
        if (phase.current) classes.push("current");
        parts.push('<section class="' + classes.join(" ") + '"><h2>' + markHtml(phase.completed ? "done" : "todo")
          + escapeHtml(phase.title) + (phase.current ? ' <span class="pill current">current</span>' : '') + '</h2><ul>');
        phase.steps.forEach((step) => {{
          const state = step.done ? "done" : "todo";
          parts.push('<li class="' + state + '">' + markHtml(state) + escapeHtml(step.title) + '</li>');
        }});
        parts.push('</ul>');
        // The TDD's V-phases replace the task list when the TDD has them.
        const devPhases = phase.dev_phases || [];
        (devPhases.length ? [] : phase.stages).forEach((stage) => {{
          parts.push('<div class="stage">' + escapeHtml(stage.title) + '</div><ul>');
          stage.tasks.forEach((task) => {{
            parts.push('<li class="' + task.status + '">' + markHtml(task.status) + escapeHtml(task.id + ' · ' + task.title) + '</li>');
          }});
          parts.push('</ul>');
        }});
        devPhases.forEach((dev) => parts.push(devPhaseHtml(dev)));
        const pending = phase.key === model.next_gate_phase;
        parts.push('<div class="gate' + (pending ? ' pending' : '') + '">Gate' + (pending ? ' to pass next' : '')
          + ': ' + escapeHtml(phase.gate) + '</div></section>');
      }});
      // A refresh rebuilds the tab; keep the collapsibles the engineer opened or closed by hand.
      const openState = {{}};
      target.querySelectorAll("details[data-key]").forEach((el) => {{ openState[el.dataset.key] = el.open; }});
      target.innerHTML = parts.join("");
      target.querySelectorAll("details[data-key]").forEach((el) => {{
        if (el.dataset.key in openState) el.open = openState[el.dataset.key];
      }});
    }} catch (err) {{
      target.innerHTML = '<div class="error">' + escapeHtml(err && err.message ? err.message : err) + '</div>';
    }}
  }}

  function renderTab(id) {{
    if (tabKinds[id] === "md") {{
      renderMarkdown(id, sources[id]);
    }} else if (tabKinds[id] === "progress") {{
      renderProgress(id, sources[id]);
    }} else {{
      renderedSourceFor[id] = sources[id];
      renderDiagram(id, sources[id]);
    }}
  }}

  function isActiveTabId(id) {{
    const active = document.querySelector(".tab.active");
    return !!active && active.dataset.i === id.slice(1);
  }}

  function renderAll() {{
    // Diagrams render lazily, on first activation: mermaid.render() measures text via
    // getBBox(), which returns a degenerate (zero-size) result for an element still inside a
    // display:none ancestor, so a diagram rendered here for a not-yet-selected tab comes out
    // blank even though svgPanZoom reports success. Markdown has no such measurement step, so
    // it stays eager.
    Object.keys(sources).forEach((id) => {{
      if (tabKinds[id] !== "mmd") {{
        renderTab(id);
      }}
    }});
  }}

  function activate(idx) {{
    document.querySelectorAll(".tab").forEach((el, i) => el.classList.toggle("active", i === idx));
    document.querySelectorAll(".panel").forEach((el, i) => el.classList.toggle("active", i === idx));
    const id = "d" + idx;
    if (tabKinds[id] !== "mmd") {{
      return;
    }}
    if (renderedSourceFor[id] !== sources[id]) {{
      renderTab(id);  // first view of this diagram, or its source changed while it was hidden
      return;
    }}
    const inst = panZoomInstances[id];
    if (inst) {{
      inst.resize();
      inst.fit();
      inst.center();
    }}
  }}
  document.querySelectorAll(".tab").forEach((el, i) => el.addEventListener("click", () => activate(i)));
  activate(0);
  renderAll();
  window.addEventListener("resize", () => {{
    const activeIdx = [...document.querySelectorAll(".tab")].findIndex(el => el.classList.contains("active"));
    if (activeIdx >= 0) activate(activeIdx);
  }});
  {live_script}
</script>
{live_module_script}
</body>
</html>
"""

LIVE_SCRIPT_TEMPLATE = """
  let knownMtimes = {{}};
  async function pollState() {{
    try {{
      const res = await fetch("/api/state");
      const state = await res.json();
      document.dispatchEvent(new CustomEvent("docreview:state", {{ detail: {{ threads: state.threads }} }}));
      const changedIds = [];
      for (const [id, path] of Object.entries(tabPaths)) {{
        const mtime = state.mtimes[path];
        if (knownMtimes[id] !== undefined && mtime !== knownMtimes[id]) {{
          changedIds.push(id);
        }}
        knownMtimes[id] = mtime;
      }}
      if (changedIds.length > 0) {{
        const freshSources = await (await fetch("/api/sources")).json();
        changedIds.forEach((id) => {{
          sources[id] = freshSources[id];
          // Markdown is always safe to redraw. A hidden diagram tab is left with its cache
          // just updated -- activate() renders it fresh, correctly, once it's actually selected.
          if (tabKinds[id] !== "mmd" || isActiveTabId(id)) {{
            renderTab(id);
          }}
        }});
      }}
    }} catch (err) {{
      // server unreachable mid-poll (e.g. shutting down) -- skip this round, try again next tick
    }}
  }}
  setInterval(pollState, {poll_interval_ms});
  pollState();
"""


def serve_doc(paths: List[Path], port: Optional[int] = None, open_browser: bool = False) -> None:
    store = SidecarStore(paths[0])
    handler_factory = functools.partial(ReviewRequestHandler, doc_paths=paths, store=store)
    httpd = _bind_server(handler_factory, port)
    url = f"http://127.0.0.1:{httpd.server_address[1]}/"
    print(url, flush=True)
    if open_browser:
        _open_url(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


def render_static(paths: List[Path], output_path: Optional[Path] = None, open_browser: bool = False) -> Path:
    out_path = output_path or (paths[0].parent / "_doc_review_preview.html")
    out_path.write_text(build_page(paths, live=False))
    print(str(out_path))
    if open_browser:
        if sys.platform == "darwin":
            subprocess.run(["open", str(out_path)], check=False)
        else:
            webbrowser.open(out_path.resolve().as_uri())
    return out_path


class ReviewRequestHandler(http.server.BaseHTTPRequestHandler):
    def __init__(self, *args, doc_paths: List[Path], store: SidecarStore, static_dir: Path = STATIC_DIR, **kwargs):
        # Set before super().__init__: BaseHTTPRequestHandler.__init__ handles the request
        # immediately, so these must already be in place -- same pattern SimpleHTTPRequestHandler
        # uses for its `directory` argument.
        self._doc_paths = doc_paths
        self._store = store
        self._static_files = _static_allowlist(static_dir)
        super().__init__(*args, **kwargs)

    def do_GET(self):
        if self.path in ("/", ""):
            self._send_html(build_page(self._doc_paths, live=True))
        elif self.path == "/api/state":
            self._send_json(self._state())
        elif self.path == "/api/sources":
            self._send_json(_collect_sources(_tabs(self._doc_paths)))
        elif self.path.startswith("/static/"):
            self._handle_static(self.path[len("/static/"):])
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == "/api/comment":
            self._handle_comment()
        elif self.path == "/api/status":
            self._handle_status()
        elif self.path == "/api/reply":
            self._handle_reply()
        else:
            self.send_error(404)

    def log_message(self, format_string, *args):  # noqa: A002 - matches BaseHTTPRequestHandler's signature
        pass  # stdout is reserved for the server URL the engineer scripts against

    def _state(self) -> Dict:
        base_dir = self._doc_paths[0].parent
        threads = self._store.load()["threads"]
        for thread in threads:
            thread["resolution"] = resolve_thread(base_dir, thread)
        return {"mtimes": _collect_mtimes(_tabs(self._doc_paths)), "threads": threads}

    def _handle_comment(self):
        body = self._read_json_body()
        if body is None:
            return
        anchor = body.get("anchor")
        if not anchor:
            self._send_json({"error": "missing anchor"}, status=400)
            return
        thread_id = self._store.add_thread(anchor, "engineer", body.get("text", ""))
        self._send_json({"id": thread_id})

    def _handle_status(self):
        body = self._read_json_body()
        if body is None:
            return
        thread_id, status = body.get("id"), body.get("status")
        if not thread_id or not status:
            self._send_json({"error": "missing id or status"}, status=400)
            return
        try:
            self._store.set_status(thread_id, status, "engineer")
            self._send_json({"ok": True})
        except PermissionError as e:
            self._send_json({"error": str(e)}, status=403)
        except KeyError as e:
            self._send_json({"error": str(e)}, status=404)

    def _handle_reply(self):
        body = self._read_json_body()
        if body is None:
            return
        thread_id, text = body.get("id"), body.get("text")
        if not thread_id or not text:
            self._send_json({"error": "missing id or text"}, status=400)
            return
        try:
            self._store.add_reply(thread_id, "engineer", text)
            self._send_json({"ok": True})
        except KeyError as e:
            self._send_json({"error": str(e)}, status=404)

    def _handle_static(self, name: str):
        # name is looked up in an allowlist keyed by plain filename, built once from static_dir's
        # actual contents -- "../../etc/passwd" is simply not a key in that dict, so this is
        # traversal-safe by construction, with no path-component validation needed.
        file_path = self._static_files.get(name)
        if file_path is None:
            self.send_error(404)
            return
        content_type = STATIC_CONTENT_TYPE_BY_SUFFIX.get(file_path.suffix, "application/octet-stream")
        self._send_bytes(file_path.read_bytes(), content_type, 200)

    def _read_json_body(self) -> Optional[Dict]:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b""
        try:
            return json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            self._send_json({"error": "invalid JSON body"}, status=400)
            return None

    def _send_html(self, body: str, status: int = 200):
        self._send_bytes(body.encode("utf-8"), "text/html; charset=utf-8", status)

    def _send_json(self, data: Dict, status: int = 200):
        self._send_bytes(json.dumps(data).encode("utf-8"), "application/json", status)

    def _send_bytes(self, payload: bytes, content_type: str, status: int):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def build_page(paths: List[Path], live: bool) -> str:
    tabs = _tabs(paths)
    tab_buttons = "\n".join(
        f'<button class="tab{" active" if i == 0 else ""}" data-i="{i}">{html.escape(tab["title"])}</button>'
        for i, tab in enumerate(tabs)
    )
    panels = "\n".join(_panel_html(i, tab) for i, tab in enumerate(tabs))
    tab_paths_js = json.dumps({tab["id"]: _mtime_key(tab) for tab in tabs})
    doc_review_js = json.dumps({"tabs": [{"id": tab["id"], "file": tab["file"], "kind": tab["kind"]} for tab in tabs]})

    live_script = ""
    live_head_extra = ""
    live_module_script = ""
    live_sidebar_slot = ""
    if live:
        live_script = (
            f"const tabPaths = {tab_paths_js};\n"
            f"window.docReview = {doc_review_js};\n"
            + LIVE_SCRIPT_TEMPLATE.format(poll_interval_ms=POLL_INTERVAL_MS)
        )
        live_head_extra = '<link rel="stylesheet" href="/static/review_ui.css">'
        live_module_script = '<script type="module" src="/static/review_ui.js"></script>'
        live_sidebar_slot = '<aside id="docreview-panel"></aside>'

    return PAGE_TEMPLATE.format(
        live_suffix=" (live)" if live else "",
        marked_cdn=MARKED_CDN,
        mermaid_cdn=MERMAID_CDN,
        panzoom_cdn=SVG_PAN_ZOOM_CDN,
        header_text="LocalDocReview -- live server, not published anywhere"
        if live
        else "LocalDocReview -- static preview, not published anywhere",
        tab_buttons=tab_buttons,
        panels=panels,
        tab_kinds_js=json.dumps({tab["id"]: tab["kind"] for tab in tabs}),
        sources_js=json.dumps(_collect_sources(tabs)),
        live_script=live_script,
        live_head_extra=live_head_extra,
        live_module_script=live_module_script,
        live_sidebar_slot=live_sidebar_slot,
    )


def _tabs(paths: List[Path]) -> List[Dict]:
    base_dir = paths[0].parent
    tabs = [
        {
            "title": path.stem,
            "kind": "md" if path.suffix == ".md" else "mmd",
            "path": path,
            "file": _relative_to_doc_folder(path, base_dir),
        }
        for path in paths
    ]
    progress_path = find_progress_file(paths[0])
    if progress_path is not None:
        # Auto-added first for a feature doc: phases/steps/gates from CreateFeature, state from Progress.md.
        # Its file key carries "#progress" because the static/*.js tab lookups match anchor.file with
        # find(): a thread anchored in a Progress.md md tab must not resolve to this tab, which precedes it.
        tabs.insert(
            0,
            {
                "title": "Progress",
                "kind": "progress",
                "path": progress_path,
                "file": _relative_to_doc_folder(progress_path, base_dir) + "#progress",
            },
        )
    for i, tab in enumerate(tabs):
        tab["id"] = f"d{i}"
    return tabs


def _static_allowlist(static_dir: Path) -> Dict[str, Path]:
    if not static_dir.is_dir():
        return {}
    return {entry.name: entry for entry in static_dir.iterdir() if entry.is_file()}


def _relative_to_doc_folder(path: Path, base_dir: Path) -> str:
    # anchor.file (anchor_resolver.py) is always relative to the doc's own folder; a tab's path
    # is whatever was passed on the CLI (absolute, or relative to the CWD), so the two must be
    # reconciled here rather than assumed to already match.
    try:
        return str(path.resolve().relative_to(base_dir.resolve()))
    except ValueError:
        return path.name


def _collect_sources(tabs: List[Dict]) -> Dict[str, str]:
    return {tab["id"]: _tab_source(tab) for tab in tabs}


def _collect_mtimes(tabs: List[Dict]) -> Dict[str, float]:
    return {_mtime_key(tab): _tab_mtime(tab) for tab in tabs}


def _tab_source(tab: Dict) -> str:
    if tab["kind"] == "progress":
        return json.dumps(build_model(tab["path"]))
    return tab["path"].read_text()


def _tab_mtime(tab: Dict) -> float:
    if tab["kind"] == "progress":
        newest_file = max(path.stat().st_mtime for path in watched_paths(tab["path"]))
        return max(newest_file, pr_refresh_stamp(tab["path"]))
    return tab["path"].stat().st_mtime


def _mtime_key(tab: Dict) -> str:
    # The Progress tab watches several files and may share its Progress.md path with a plain md tab,
    # so it gets its own key rather than colliding with that tab's.
    return str(tab["path"]) + "#progress" if tab["kind"] == "progress" else str(tab["path"])


def _panel_html(i: int, tab: Dict) -> str:
    active = " active" if i == 0 else ""
    css_class = {"md": "markdown", "progress": "progress-view"}.get(tab["kind"], "diagram")
    return f'<div class="panel{active}"><div class="{css_class}" id="d{i}"></div></div>'


def _bind_server(handler_factory, port: Optional[int]) -> http.server.ThreadingHTTPServer:
    if port is not None:
        try:
            return http.server.ThreadingHTTPServer(("127.0.0.1", port), handler_factory)
        except OSError:
            print(f"Port {port} is in use -- picking a free one instead.")
    return http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler_factory)


def _open_url(url: str) -> None:
    if sys.platform == "darwin":
        subprocess.run(["open", url], check=False)
    else:
        webbrowser.open(url)
