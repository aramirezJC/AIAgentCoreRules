// localStorage drafts, keyed per doc (window.docReview's main doc file): new-thread drafts (with
// their own anchor) and reply drafts (keyed by thread id). Every access is wrapped in try/catch --
// private browsing, disabled storage, or a full quota must never break the page; a draft is a
// convenience, never state the rest of the UI depends on existing.
const STORAGE_PREFIX = "docreview-drafts:";

function mainDocFile() {
  return window.docReview?.tabs?.[0]?.file || "";
}

function storageKey() {
  return STORAGE_PREFIX + mainDocFile();
}

function readStore() {
  try {
    const parsed = JSON.parse(localStorage.getItem(storageKey()));
    return {
      newThreads: (parsed && parsed.newThreads) || {},
      replies: (parsed && parsed.replies) || {},
    };
  } catch (err) {
    return { newThreads: {}, replies: {} };
  }
}

function writeStore(store) {
  try {
    localStorage.setItem(storageKey(), JSON.stringify(store));
  } catch (err) {
    // ignore -- quota exceeded, storage disabled, or private browsing
  }
}

export function generateDraftId() {
  return `draft-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export function saveNewThreadDraft(draftId, anchor, text) {
  const store = readStore();
  store.newThreads[draftId] = { anchor, text };
  writeStore(store);
}

export function discardNewThreadDraft(draftId) {
  const store = readStore();
  delete store.newThreads[draftId];
  writeStore(store);
}

export function listNewThreadDrafts() {
  const store = readStore();
  return Object.entries(store.newThreads).map(([draftId, draft]) => ({ draftId, ...draft }));
}

export function saveReplyDraft(threadId, text) {
  const store = readStore();
  store.replies[threadId] = text;
  writeStore(store);
}

export function discardReplyDraft(threadId) {
  const store = readStore();
  delete store.replies[threadId];
  writeStore(store);
}

export function listReplyDrafts() {
  return readStore().replies;
}
