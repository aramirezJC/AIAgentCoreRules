// Right sidebar: Drafts, Active, Orphaned, Resolved (collapsed) sections; cards with replies, a
// reply box, and Ready/Resolve/Reopen status buttons.
import { postComment, postReply, postStatus } from "./api.js";
import { discardNewThreadDraft, discardReplyDraft, listNewThreadDrafts, listReplyDrafts, saveReplyDraft } from "./drafts.js";

const STATUS_BUTTONS = [
  { status: "ready", label: "Ready" },
  { status: "resolved", label: "Resolve" },
  { status: "open", label: "Reopen" },
];

// Keyed by thread id: an in-progress reply the engineer is typing. Read before every rebuild and
// restored after, so a poll landing mid-keystroke (U10/E16) never erases a draft reply. Seeded
// once from localStorage so a reply started before an actual page reload isn't lost either (E7).
const pendingReplies = {};
let repliesSeededFromStorage = false;

function seedPendingRepliesOnce() {
  if (repliesSeededFromStorage) {
    return;
  }
  repliesSeededFromStorage = true;
  Object.assign(pendingReplies, listReplyDrafts());
}

// Every renderThreadPanel() call fully rebuilds the panel's innerHTML, which would otherwise
// reset every <details> back to its hardcoded default each time -- found via show-and-tell: a
// just-expanded Resolved section snapped shut on the next rebuild, looking like it couldn't be
// expanded at all. Read the CURRENT state before rebuilding so a manual toggle always wins.
const sectionOpenState = { drafts: true, active: true, orphaned: true, resolved: false };

function syncSectionOpenState(container) {
  container.querySelectorAll(".docreview-section").forEach((el) => {
    sectionOpenState[el.dataset.group] = el.open;
  });
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function quotePreview(thread) {
  const anchor = thread.anchor;
  const text = anchor.kind === "text" ? anchor.quote : anchor.label || anchor.source_id || "(empty space)";
  return text.length > 80 ? `${text.slice(0, 79)}…` : text;
}

function classifyThread(thread, renderFailedTabIds) {
  const tabId = (window.docReview?.tabs || []).find((t) => t.file === thread.anchor.file)?.id;
  if (thread.status === "resolved") {
    return "resolved";
  }
  if (tabId && renderFailedTabIds.has(tabId)) {
    return "render_failed"; // E17: a parse error must not be mistaken for an orphan
  }
  if (thread.resolution && thread.resolution.status === "orphaned") {
    return "orphaned"; // U12
  }
  return "active";
}

function renderReplies(thread) {
  return thread.replies
    .map((reply) => `<div class="docreview-reply"><b>${escapeHtml(reply.author)}:</b> ${escapeHtml(reply.text)}</div>`)
    .join("");
}

function renderStatusButtons(thread) {
  return STATUS_BUTTONS.filter((btn) => btn.status !== thread.status)
    .map((btn) => `<button type="button" class="docreview-status-btn" data-status="${btn.status}">${btn.label}</button>`)
    .join("");
}

function renderNote(group) {
  if (group === "orphaned") {
    return '<div class="docreview-card-note">Anchor not found in the current source.</div>';
  }
  if (group === "render_failed") {
    return '<div class="docreview-card-note">Diagram failed to render.</div>';
  }
  return "";
}

function renderCard(thread, renderFailedTabIds) {
  const group = classifyThread(thread, renderFailedTabIds);
  return `
    <div class="docreview-card" data-thread-id="${thread.id}">
      <div class="docreview-card-quote">${escapeHtml(quotePreview(thread))}</div>
      ${renderNote(group)}
      <div class="docreview-card-replies">${renderReplies(thread)}</div>
      <textarea class="docreview-reply-input" placeholder="Reply...">${escapeHtml(pendingReplies[thread.id] || "")}</textarea>
      <div class="docreview-card-error" hidden></div>
      <div class="docreview-card-actions">
        ${renderStatusButtons(thread)}
        <button type="button" class="docreview-reply-btn">Reply</button>
      </div>
    </div>
  `;
}

function draftQuotePreview(anchor) {
  const text = anchor.kind === "text" ? anchor.quote : anchor.label || anchor.source_id || "(empty space)";
  return text.length > 80 ? `${text.slice(0, 79)}…` : text;
}

function renderDraftCard(draft) {
  return `
    <div class="docreview-card docreview-draft-card" data-draft-id="${draft.draftId}">
      <div class="docreview-card-quote">${escapeHtml(draftQuotePreview(draft.anchor))}</div>
      <div class="docreview-card-note">Not sent yet.</div>
      <textarea class="docreview-draft-input" placeholder="Add a comment...">${escapeHtml(draft.text)}</textarea>
      <div class="docreview-card-error" hidden></div>
      <div class="docreview-card-actions">
        <button type="button" class="docreview-draft-discard">Discard</button>
        <button type="button" class="docreview-draft-send">Send</button>
      </div>
    </div>
  `;
}

function renderDraftsSection(drafts) {
  const openAttr = sectionOpenState.drafts ? " open" : "";
  return `
    <details class="docreview-section" data-group="drafts"${openAttr}>
      <summary>Drafts (${drafts.length})</summary>
      <div class="docreview-section-body">${drafts.map(renderDraftCard).join("")}</div>
    </details>
  `;
}

function wireDraftCard(card, draft, onChanged) {
  const textarea = card.querySelector(".docreview-draft-input");
  const errorEl = card.querySelector(".docreview-card-error");

  card.querySelector(".docreview-draft-discard").addEventListener("click", () => {
    discardNewThreadDraft(draft.draftId);
    onChanged();
  });

  card.querySelector(".docreview-draft-send").addEventListener("click", async () => {
    const text = textarea.value.trim();
    if (!text) {
      errorEl.textContent = "Comment can't be empty.";
      errorEl.hidden = false;
      return;
    }
    const result = await postComment(draft.anchor, text);
    if (!result.ok) {
      errorEl.textContent = result.error; // E21: keep the draft card (and its text) around
      errorEl.hidden = false;
      return;
    }
    discardNewThreadDraft(draft.draftId);
    onChanged();
  });
}

function renderSection(title, threads, group, renderFailedTabIds) {
  if (threads.length === 0 && group !== "drafts") {
    return "";
  }
  const openAttr = sectionOpenState[group] ? " open" : "";
  return `
    <details class="docreview-section"${openAttr} data-group="${group}">
      <summary>${title} (${threads.length})</summary>
      <div class="docreview-section-body">${threads.map((t) => renderCard(t, renderFailedTabIds)).join("")}</div>
    </details>
  `;
}

function savePendingReplies(container) {
  container.querySelectorAll(".docreview-card[data-thread-id]").forEach((card) => {
    const textarea = card.querySelector(".docreview-reply-input");
    const threadId = card.dataset.threadId;
    if (textarea.value) {
      pendingReplies[threadId] = textarea.value;
    } else {
      delete pendingReplies[threadId];
    }
  });
}

function wireCard(card, threadId, onChanged) {
  const textarea = card.querySelector(".docreview-reply-input");
  const errorEl = card.querySelector(".docreview-card-error");

  textarea.addEventListener("input", () => {
    pendingReplies[threadId] = textarea.value;
    if (textarea.value) {
      saveReplyDraft(threadId, textarea.value);
    } else {
      discardReplyDraft(threadId);
    }
  });

  card.querySelector(".docreview-reply-btn").addEventListener("click", async () => {
    const text = textarea.value.trim();
    if (!text) {
      errorEl.textContent = "Reply can't be empty.";
      errorEl.hidden = false;
      return;
    }
    const result = await postReply(threadId, text);
    if (!result.ok) {
      errorEl.textContent = result.error; // E21
      errorEl.hidden = false;
      return;
    }
    delete pendingReplies[threadId];
    discardReplyDraft(threadId);
    onChanged();
  });

  card.querySelectorAll(".docreview-status-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const result = await postStatus(threadId, btn.dataset.status);
      if (!result.ok) {
        errorEl.textContent = result.error;
        errorEl.hidden = false;
        return;
      }
      onChanged();
    });
  });
}

export function renderThreadPanel(container, threads, renderFailedTabIds, { onChanged, onThreadFocused }) {
  seedPendingRepliesOnce();
  savePendingReplies(container);
  syncSectionOpenState(container);

  const drafts = listNewThreadDrafts();
  const failedTabIds = renderFailedTabIds || new Set();
  const groups = { active: [], orphaned: [], resolved: [] };
  threads.forEach((thread) => {
    const group = classifyThread(thread, failedTabIds);
    groups[group === "render_failed" ? "active" : group].push(thread);
  });

  container.innerHTML = `
    <div class="docreview-panel-header">Comments</div>
    ${renderDraftsSection(drafts)}
    ${renderSection("Active", groups.active, "active", failedTabIds)}
    ${renderSection("Orphaned", groups.orphaned, "orphaned", failedTabIds)}
    ${renderSection("Resolved", groups.resolved, "resolved", failedTabIds)}
  `;

  container.querySelectorAll(".docreview-draft-card").forEach((card) => {
    const draft = drafts.find((d) => d.draftId === card.dataset.draftId);
    if (draft) {
      wireDraftCard(card, draft, onChanged);
    }
  });

  container.querySelectorAll(".docreview-card[data-thread-id]").forEach((card) => {
    const threadId = card.dataset.threadId;
    wireCard(card, threadId, onChanged);
    card.querySelector(".docreview-card-quote").addEventListener("click", () => onThreadFocused?.(threadId));
  });
}
