// Fetch wrappers for the comment API. Every call returns { ok, error? } (never throws), so a
// caller only ever has one failure shape to check, whether the server rejected the request or
// the network/fetch itself failed (e.g. E21: server stops while the page is open).
async function postJson(url, body) {
  let response;
  try {
    response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch (err) {
    return { ok: false, error: err && err.message ? err.message : String(err) };
  }

  let data;
  try {
    data = await response.json();
  } catch (err) {
    return { ok: false, error: "server returned a non-JSON response" };
  }

  if (!response.ok) {
    return { ok: false, error: data.error || `request failed (${response.status})` };
  }
  return { ok: true, data };
}

export function postComment(anchor, text) {
  return postJson("/api/comment", { anchor, text });
}

export function postReply(id, text) {
  return postJson("/api/reply", { id, text });
}

export function postStatus(id, status) {
  return postJson("/api/status", { id, status });
}
