// Draw and clear highlights (md) and pins (diagram), re-applied after every render (a markdown
// re-render replaces innerHTML, losing any prior overlay) and after every state poll (new threads
// may have arrived, via the CLI or another browser tab -- U10, E22).
import { findQuoteRange, highlightRange } from "./text_anchors.js";

const SVG_NS = "http://www.w3.org/2000/svg";

let activeMarks = [];
let activePins = [];

function tabIdForFile(file) {
  const tab = (window.docReview?.tabs || []).find((t) => t.file === file);
  return tab ? tab.id : null;
}

function clearOverlays() {
  activeMarks.forEach((mark) => {
    const parent = mark.parentNode;
    if (!parent) {
      return;
    }
    while (mark.firstChild) {
      parent.insertBefore(mark.firstChild, mark);
    }
    parent.removeChild(mark);
  });
  activeMarks = [];
  activePins.forEach((pin) => pin.remove());
  activePins = [];
}

function drawTextHighlight(thread) {
  const tabId = tabIdForFile(thread.anchor.file);
  if (!tabId) {
    return; // E20: this file isn't one of the tabs served this run
  }
  const markdownRoot = document.getElementById(tabId);
  if (!markdownRoot) {
    return;
  }
  const range = findQuoteRange(markdownRoot, thread.anchor.quote, thread.anchor.prefix, thread.anchor.suffix);
  if (!range) {
    return; // can happen between a source edit and the next resolver poll catching up
  }
  activeMarks.push(highlightRange(range, thread.id));
}

function drawDiagramPin(thread, renderFailedTabIds) {
  const tabId = tabIdForFile(thread.anchor.file);
  if (!tabId || renderFailedTabIds.has(tabId)) {
    return; // E20, E17: not served this run, or the diagram failed to render -- no SVG to pin onto
  }
  const panel = document.getElementById(tabId);
  const svg = panel ? panel.querySelector("svg") : null;
  if (!svg) {
    return;
  }
  const viewport = svg.querySelector("g.svg-pan-zoom_viewport") || svg;
  const { x, y } = thread.anchor.point;
  const pin = document.createElementNS(SVG_NS, "circle");
  pin.setAttribute("cx", String(x));
  pin.setAttribute("cy", String(y));
  pin.setAttribute("r", "6");
  pin.setAttribute("class", "docreview-pin");
  pin.dataset.threadId = thread.id;
  viewport.appendChild(pin);
  activePins.push(pin);
}

export function redrawOverlays(threads, renderFailedTabIds) {
  clearOverlays();
  threads.forEach((thread) => {
    if (thread.status === "resolved") {
      return; // a resolved thread is done being tracked in the doc -- found via show-and-tell:
      // leaving its highlight/pin behind forever made the render look permanently annotated.
    }
    if (!thread.resolution || thread.resolution.status !== "resolved") {
      return; // ambiguous/orphaned threads show in the panel only, nothing to draw on the render
    }
    if (thread.anchor.kind === "text") {
      drawTextHighlight(thread);
    } else {
      drawDiagramPin(thread, renderFailedTabIds || new Set());
    }
  });
}
