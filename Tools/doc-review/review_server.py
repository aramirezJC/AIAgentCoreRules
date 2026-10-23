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

from sidecar_store import SidecarStore

MERMAID_CDN = "https://cdnjs.cloudflare.com/ajax/libs/mermaid/11.15.0/mermaid.min.js"
MARKED_CDN = "https://cdnjs.cloudflare.com/ajax/libs/marked/18.1.1/lib/marked.umd.min.js"
SVG_PAN_ZOOM_CDN = "https://cdn.jsdelivr.net/npm/svg-pan-zoom@3.6.1/dist/svg-pan-zoom.min.js"
POLL_INTERVAL_MS = 1000

PAGE_TEMPLATE = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Doc review{live_suffix}</title>
<script src="{marked_cdn}"></script>
<script src="{mermaid_cdn}"></script>
<script src="{panzoom_cdn}"></script>
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
</style>
</head>
<body>
<header>{header_text}
  <span class="hint">scroll/pinch to zoom on diagrams &middot; drag to pan &middot; bottom-left icons to reset</span>
</header>
<div class="tabs">
{tab_buttons}
</div>
{panels}
<script>
  mermaid.initialize({{ startOnLoad: false, theme: "dark" }});
  const tabKinds = {tab_kinds_js};
  const sources = {sources_js};
  const panZoomInstances = {{}};
  const renderedSourceFor = {{}};

  function renderMarkdown(id, src) {{
    const target = document.getElementById(id);
    try {{
      target.innerHTML = marked.parse(src);
    }} catch (err) {{
      // A failure here must not stop renderAll()'s forEach from reaching the other tabs.
      target.innerHTML = '<div class="error">' + (err && err.message ? err.message : err) + '</div>';
    }}
  }}

  async function renderDiagram(id, src) {{
    const target = document.getElementById(id);
    const existing = panZoomInstances[id];
    const savedPan = existing ? existing.getPan() : null;
    const savedZoom = existing ? existing.getZoom() : null;
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
    }}
  }}

  function renderTab(id) {{
    if (tabKinds[id] === "md") {{
      renderMarkdown(id, sources[id]);
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
      if (tabKinds[id] === "md") {{
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
</body>
</html>
"""

LIVE_SCRIPT_TEMPLATE = """
  let knownMtimes = {{}};
  async function pollState() {{
    try {{
      const res = await fetch("/api/state");
      const state = await res.json();
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
          if (tabKinds[id] === "md" || isActiveTabId(id)) {{
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
    print(url)
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
    def __init__(self, *args, doc_paths: List[Path], store: SidecarStore, **kwargs):
        # Set before super().__init__: BaseHTTPRequestHandler.__init__ handles the request
        # immediately, so these must already be in place -- same pattern SimpleHTTPRequestHandler
        # uses for its `directory` argument.
        self._doc_paths = doc_paths
        self._store = store
        super().__init__(*args, **kwargs)

    def do_GET(self):
        if self.path in ("/", ""):
            self._send_html(build_page(self._doc_paths, live=True))
        elif self.path == "/api/state":
            self._send_json(self._state())
        elif self.path == "/api/sources":
            self._send_json(_collect_sources(_tabs(self._doc_paths)))
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == "/api/comment":
            self._handle_comment()
        elif self.path == "/api/status":
            self._handle_status()
        else:
            self.send_error(404)

    def log_message(self, format_string, *args):  # noqa: A002 - matches BaseHTTPRequestHandler's signature
        pass  # stdout is reserved for the server URL the engineer scripts against

    def _state(self) -> Dict:
        return {"mtimes": _collect_mtimes(_tabs(self._doc_paths)), "threads": self._store.load()["threads"]}

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
    tab_paths_js = json.dumps({tab["id"]: str(tab["path"]) for tab in tabs})

    live_script = ""
    if live:
        live_script = f"const tabPaths = {tab_paths_js};\n" + LIVE_SCRIPT_TEMPLATE.format(
            poll_interval_ms=POLL_INTERVAL_MS
        )

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
    )


def _tabs(paths: List[Path]) -> List[Dict]:
    return [
        {"id": f"d{i}", "title": path.stem, "kind": "md" if path.suffix == ".md" else "mmd", "path": path}
        for i, path in enumerate(paths)
    ]


def _collect_sources(tabs: List[Dict]) -> Dict[str, str]:
    return {tab["id"]: tab["path"].read_text() for tab in tabs}


def _collect_mtimes(tabs: List[Dict]) -> Dict[str, float]:
    return {str(tab["path"]): tab["path"].stat().st_mtime for tab in tabs}


def _panel_html(i: int, tab: Dict) -> str:
    active = " active" if i == 0 else ""
    css_class = "markdown" if tab["kind"] == "md" else "diagram"
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
