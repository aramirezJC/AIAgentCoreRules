// Selection -> text anchor (quote/prefix/suffix/heading_path); quote -> DOM Range, both for the
// comment just created in this session (immediate highlight) and for overlays.js's general
// redraw-all-highlights-after-every-render mechanism (task 10), which calls findQuoteRange.
import { postComment } from "./api.js";
import { discardNewThreadDraft, generateDraftId, saveNewThreadDraft } from "./drafts.js";

const PREFIX_SUFFIX_LENGTH = 40;
const POPOVER_WIDTH = 280;

let popoverEl = null;
// Set while a popover is open, to whatever should happen if it's dismissed WITHOUT an explicit
// Cancel or a successful Submit (Escape, clicking elsewhere, or the tab/page closing) -- E7/Q5:
// an abandoned-but-not-discarded draft must survive, reappearing as a sidebar Draft card.
let onPopoverDismissed = null;

window.addEventListener("beforeunload", () => onPopoverDismissed?.());

function normalizeWhitespace(text) {
  return text.replace(/\s+/g, " ");
}

function captureHeadingPath(markdownRoot, node) {
  // Mirrors anchor_resolver._heading_path_at: walk headings in document order, and a new
  // heading at level L closes every currently open heading at level >= L. Result is
  // outermost-first (H1, then its nearest H2, ...), matching the server's ordering exactly.
  const headings = Array.from(markdownRoot.querySelectorAll("h1, h2, h3, h4, h5, h6"));
  const path = [];
  for (const heading of headings) {
    if (heading.compareDocumentPosition(node) & Node.DOCUMENT_POSITION_PRECEDING) {
      break; // this heading (and every later one) comes after the selection -- not an ancestor
    }
    const level = Number(heading.tagName.slice(1));
    while (path.length > 0 && path[path.length - 1].level >= level) {
      path.pop();
    }
    path.push({ level, text: normalizeWhitespace(heading.textContent).trim() });
  }
  return path.map((entry) => entry.text);
}

export function captureSelectionAnchor(markdownRoot, selection, file) {
  if (!selection || selection.isCollapsed || selection.rangeCount === 0) {
    return null; // E15: empty selection -> no popover
  }
  const range = selection.getRangeAt(0);
  if (!markdownRoot.contains(range.commonAncestorContainer)) {
    return null; // E15: selection isn't inside this panel (e.g. it's inside the popover itself)
  }
  const quote = normalizeWhitespace(selection.toString()).trim();
  if (!quote) {
    return null;
  }

  const beforeRange = document.createRange();
  beforeRange.selectNodeContents(markdownRoot);
  beforeRange.setEnd(range.startContainer, range.startOffset);
  const prefix = normalizeWhitespace(beforeRange.toString()).slice(-PREFIX_SUFFIX_LENGTH);

  const afterRange = document.createRange();
  afterRange.selectNodeContents(markdownRoot);
  afterRange.setStart(range.endContainer, range.endOffset);
  const suffix = normalizeWhitespace(afterRange.toString()).slice(0, PREFIX_SUFFIX_LENGTH);

  return {
    kind: "text",
    file,
    quote,
    prefix,
    suffix,
    heading_path: captureHeadingPath(markdownRoot, range.startContainer),
  };
}

// Re-find a quote (already resolved server-side) in the CURRENTLY rendered markdown text, for
// overlays.js to redraw a highlight after every render or state poll. The quote/prefix/suffix
// were captured from rendered (syntax-free) text in the first place, so only whitespace needs
// normalizing here -- no Markdown-syntax stripping like the server's _normalize_markdown.
export function findQuoteRange(markdownRoot, quote, prefix, suffix) {
  const normalizedQuote = normalizeWhitespace(quote || "").trim();
  if (!normalizedQuote) {
    return null;
  }

  const walker = document.createTreeWalker(markdownRoot, NodeFilter.SHOW_TEXT);
  const segments = []; // {node, start, end} offsets into the RAW (non-normalized) combined text
  let raw = "";
  let node;
  while ((node = walker.nextNode())) {
    const start = raw.length;
    raw += node.nodeValue;
    segments.push({ node, start, end: raw.length });
  }

  let normalized = "";
  const rawOffsetAt = []; // rawOffsetAt[i] = raw-text offset the i-th normalized char came from
  let lastWasSpace = true; // true at the start so leading whitespace is dropped, like .trim()
  for (let i = 0; i < raw.length; i++) {
    const ch = raw[i];
    if (/\s/.test(ch)) {
      if (!lastWasSpace) {
        normalized += " ";
        rawOffsetAt.push(i);
      }
      lastWasSpace = true;
    } else {
      normalized += ch;
      rawOffsetAt.push(i);
      lastWasSpace = false;
    }
  }

  const positions = [];
  for (let from = 0; ; ) {
    const idx = normalized.indexOf(normalizedQuote, from);
    if (idx === -1) {
      break;
    }
    positions.push(idx);
    from = idx + 1;
  }
  if (positions.length === 0) {
    return null;
  }

  let chosen = positions[0]; // E19: no disambiguator (or none match) -> first
  if (positions.length > 1 && (prefix || suffix)) {
    const normalizedPrefix = normalizeWhitespace(prefix || "");
    const normalizedSuffix = normalizeWhitespace(suffix || "");
    const match = positions.find((pos) => {
      const before = normalized.slice(Math.max(0, pos - normalizedPrefix.length), pos);
      const after = normalized.slice(
        pos + normalizedQuote.length,
        pos + normalizedQuote.length + normalizedSuffix.length
      );
      return (
        (!normalizedPrefix || before.endsWith(normalizedPrefix)) &&
        (!normalizedSuffix || after.startsWith(normalizedSuffix))
      );
    });
    if (match !== undefined) {
      chosen = match;
    }
  }

  const rawStart = rawOffsetAt[chosen];
  const rawEnd = rawOffsetAt[chosen + normalizedQuote.length - 1] + 1;
  const startSegment = segments.find((seg) => rawStart >= seg.start && rawStart <= seg.end);
  const endSegment = segments.find((seg) => rawEnd - 1 >= seg.start && rawEnd - 1 < seg.end);
  if (!startSegment || !endSegment) {
    return null;
  }

  const range = document.createRange();
  range.setStart(startSegment.node, rawStart - startSegment.start);
  range.setEnd(endSegment.node, rawEnd - endSegment.start);
  return range;
}

export function highlightRange(range, threadId) {
  const mark = document.createElement("mark");
  mark.className = "docreview-highlight";
  if (threadId) {
    mark.dataset.threadId = threadId;
  }
  try {
    range.surroundContents(mark);
  } catch (err) {
    // E14: a selection spanning several blocks isn't "well-formed" for surroundContents() (it
    // partially selects element boundaries) -- extract and re-insert into the mark instead.
    const contents = range.extractContents();
    mark.appendChild(contents);
    range.insertNode(mark);
  }
  return mark;
}

function closePopover() {
  if (popoverEl) {
    onPopoverDismissed?.();
    onPopoverDismissed = null;
    popoverEl.remove();
    popoverEl = null;
  }
}

function openPopover(range, anchor, onCommentCreated) {
  closePopover(); // dismisses (and drafts, if non-empty) any popover already open elsewhere
  const draftId = generateDraftId();
  const rect = range.getBoundingClientRect();
  const popover = document.createElement("div");
  popover.className = "docreview-popover";
  popover.style.top = `${rect.bottom + 8}px`;
  popover.style.left = `${Math.max(8, Math.min(rect.left, window.innerWidth - POPOVER_WIDTH - 8))}px`;
  popover.innerHTML = `
    <textarea class="docreview-popover-input" placeholder="Add a comment..."></textarea>
    <div class="docreview-popover-error" hidden></div>
    <div class="docreview-popover-actions">
      <button type="button" class="docreview-popover-cancel">Cancel</button>
      <button type="button" class="docreview-popover-submit">Comment</button>
    </div>
  `;
  document.body.appendChild(popover);
  popoverEl = popover;

  const textarea = popover.querySelector(".docreview-popover-input");
  const errorEl = popover.querySelector(".docreview-popover-error");
  textarea.focus();

  onPopoverDismissed = () => {
    const text = textarea.value.trim();
    if (text) {
      saveNewThreadDraft(draftId, anchor, text);
    }
  };

  popover.querySelector(".docreview-popover-cancel").addEventListener("click", () => {
    onPopoverDismissed = null; // an explicit Cancel means don't persist on the way out
    discardNewThreadDraft(draftId);
    closePopover();
  });

  popover.querySelector(".docreview-popover-submit").addEventListener("click", async () => {
    const text = textarea.value.trim();
    if (!text) {
      errorEl.textContent = "Comment can't be empty.";
      errorEl.hidden = false;
      return;
    }
    const result = await postComment(anchor, text);
    if (!result.ok) {
      // E21: a POST error must not lose the draft -- leave the popover (and its text) open.
      errorEl.textContent = result.error;
      errorEl.hidden = false;
      return;
    }
    onPopoverDismissed = null;
    discardNewThreadDraft(draftId); // no-op if this draft was never actually persisted
    closePopover();
    // Highlighting is overlays.js's job exclusively (it owns clearing/redrawing every mark so it
    // can track and remove them later). Drawing one here too, on the still-live Range, used to
    // race it: overlays.js's very next redraw didn't know about this one (it only tracks marks it
    // drew itself), so it highlighted the same text a second time without clearing the first --
    // found via show-and-tell as a selection straddling a bold/code/link span fragmenting into
    // nested empty elements. onCommentCreated -> refreshFromServer() draws the one true highlight.
    if (onCommentCreated) {
      onCommentCreated(result.data, anchor);
    }
  });
}

function activeMarkdownPanel() {
  return document.querySelector(".panel.active .markdown");
}

export function enableTextSelectionComments({ getActiveTabFile, onCommentCreated }) {
  document.addEventListener("mouseup", (event) => {
    if (popoverEl && popoverEl.contains(event.target)) {
      return; // a click inside the popover (e.g. selecting its textarea text) must not recapture
    }
    const markdownRoot = activeMarkdownPanel();
    if (!markdownRoot) {
      closePopover();
      return;
    }
    const anchor = captureSelectionAnchor(markdownRoot, window.getSelection(), getActiveTabFile());
    if (!anchor) {
      closePopover();
      return;
    }
    openPopover(window.getSelection().getRangeAt(0), anchor, onCommentCreated);
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closePopover();
    }
  });
}
