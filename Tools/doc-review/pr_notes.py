"""Fetch a pull request's comments and review notes with the gh CLI, for the Progress tab.

One PR = three kinds of note: conversation comments and review bodies (gh pr view) plus inline
review comments (gh api .../pulls/<n>/comments). gh resolves the repository from repo_dir's git
remote. Results are cached per refresh window, so the 1s live poll never shells out: a window flip
is also what makes the Progress tab's mtime move (progress_view.pr_refresh_stamp), and the
re-render that follows is the one call that refetches.

Batch replies (feature PRs only): pull_threads writes the PR's threads to a draft file in the
feature folder, the reply fields are filled in, and push_replies posts them -- a dry run unless
confirmed. Threads are never resolved here; reviewers resolve their own.
"""
import json
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "feature-state"))
from feature_state import atomic_write, load_state

REFRESH_SECONDS = 300
GH_TIMEOUT_SECONDS = 20
QUOTE_LENGTH = 120

_cache: Dict[Tuple[str, int], Tuple[int, Dict]] = {}
_cache_lock = threading.Lock()
_repo_urls: Dict[str, str] = {}
GITHUB_REMOTE = re.compile(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?/?$")


def refresh_window() -> int:
    return int(time.time() // REFRESH_SECONDS)


def fetch_pr_notes(number: int, repo_dir: Path) -> Dict:
    key = (str(repo_dir), number)
    window = refresh_window()
    with _cache_lock:
        cached = _cache.get(key)
        if cached is not None and cached[0] == window:
            return cached[1]
    pr = _fetch(number, repo_dir)
    with _cache_lock:
        _cache[key] = (window, pr)
    return pr


def pr_url(number: int, repo_dir: Path) -> str:
    """A PR's GitHub page built from repo_dir's origin remote -- no gh call -- or "" when the remote
    is not GitHub. The remote is read once per repo_dir."""
    key = str(repo_dir)
    if key not in _repo_urls:
        result = subprocess.run(["git", "remote", "get-url", "origin"], cwd=key, capture_output=True, text=True,
                                timeout=GH_TIMEOUT_SECONDS, check=False)
        match = GITHUB_REMOTE.search(result.stdout.strip()) if result.returncode == 0 else None
        _repo_urls[key] = f"https://github.com/{match.group(1)}" if match else ""
    return f"{_repo_urls[key]}/pull/{number}" if _repo_urls[key] else ""


def pull_threads(number: int, feature_dir: Path, repo_dir: Optional[Path] = None) -> Tuple[Path, Dict[str, int]]:
    """Write the PR's threads to <feature>/<feature>_PR<n>_review.json, keeping the reply and posted
    fields of threads already in the draft. gh runs in repo_dir (default: the feature folder, which sits
    inside the game repository). Returns the draft path and new/awaiting/gone counts."""
    feature_dir = Path(feature_dir)
    state = load_state(feature_dir)
    if not any(number in numbers for numbers in state["pull_requests"].values()):
        raise ValueError(f"PR #{number} is not listed under pull_requests for {state['feature']} -- record it with /feature-pr first")
    view, inline = _fetch_raw(number, repo_dir or feature_dir)
    path = draft_path(feature_dir, number)
    previous = {thread["id"]: thread for thread in json.loads(path.read_text())["threads"]} if path.is_file() else {}

    previous_ids = set(previous)
    threads = _build_threads(view, inline)
    for thread in threads:
        old = previous.pop(thread["id"], None)
        if old is not None:
            thread["reply"], thread["posted"] = old.get("reply", ""), old.get("posted")
    for old in previous.values():
        old["gone"] = True
        threads.append(old)
    counts = {"threads": len(threads),
              "new": sum(1 for thread in threads if not thread.get("gone") and thread["id"] not in previous_ids),
              "awaiting": sum(1 for thread in threads if not thread.get("gone") and not thread["posted"]),
              "gone": sum(1 for thread in threads if thread.get("gone"))}
    atomic_write(path, json.dumps({"pr": number, "feature": state["feature"], "title": view.get("title", ""),
                         "url": view.get("url", ""), "pulled_at": _now(), "threads": threads}, indent=2))
    return path, counts


def push_replies(path: Path, confirm: bool, repo_dir: Optional[Path] = None) -> List[Dict]:
    """The threads with a reply not yet posted. Without confirm nothing is sent. With confirm each is
    posted in order and recorded as posted straight away; the first gh failure stops the batch."""
    path = Path(path)
    draft = json.loads(path.read_text())
    pending = [thread for thread in draft["threads"]
               if (thread.get("reply") or "").strip() and not thread.get("posted") and not thread.get("gone")]
    if not confirm:
        return pending
    for thread in pending:
        posted = _post_reply(draft["pr"], thread, repo_dir or path.parent)
        thread["posted"] = {"url": posted.get("html_url", ""), "at": _now()}
        atomic_write(path, json.dumps(draft, indent=2))
    return pending


def draft_path(feature_dir: Path, number: int) -> Path:
    return Path(feature_dir) / f"{Path(feature_dir).name}_PR{number}_review.json"


def _build_threads(view: Dict, inline: List[Dict]) -> List[Dict]:
    threads: List[Dict] = []
    for comment in view.get("comments", []):
        threads.append(_thread(f"comment:{comment.get('id', '')}", "comment", "", comment.get("url", ""), "",
                               [_thread_comment(comment.get("author"), comment.get("createdAt"), comment.get("body"))]))
    for review in view.get("reviews", []):
        if (review.get("body") or "").strip():
            threads.append(_thread(f"review:{review.get('id', '')}", "review", "", "", review.get("state", ""),
                                   [_thread_comment(review.get("author"), review.get("submittedAt"), review.get("body"))]))
    roots: Dict[int, Dict] = {}
    for comment in sorted(inline, key=lambda item: item.get("created_at") or ""):
        entry = _thread_comment(comment.get("user"), comment.get("created_at"), comment.get("body"))
        root = roots.get(comment.get("in_reply_to_id"))
        if root is not None:
            root["comments"].append(entry)
            continue
        # GitHub only accepts replies to a thread's root comment, so the root id is the thread id.
        root = _thread(f"inline:{comment.get('id')}", "inline", _location(comment), comment.get("html_url", ""), "", [entry])
        roots[comment.get("id")] = root
        threads.append(root)
    threads.sort(key=lambda thread: thread["comments"][0]["created_at"])
    return threads


def _thread(thread_id: str, kind: str, location: str, url: str, state: str, comments: List[Dict]) -> Dict:
    return {"id": thread_id, "kind": kind, "location": location, "url": url, "state": state,
            "comments": comments, "reply": "", "posted": None}


def _thread_comment(author, created_at, body) -> Dict:
    login = (author or {}).get("login", "") if isinstance(author, dict) else ""
    return {"author": login, "created_at": created_at or "", "body": body or ""}


def _post_reply(number: int, thread: Dict, repo_dir: Path) -> Dict:
    if thread["kind"] == "inline":
        root_id = thread["id"].split(":", 1)[1]
        return _gh_json(["api", f"repos/{{owner}}/{{repo}}/pulls/{number}/comments/{root_id}/replies",
                         "-f", f"body={thread['reply']}"], repo_dir)
    # Conversation comments and review bodies have no reply endpoint: answer in the conversation, quoting the note.
    first = thread["comments"][0]
    quote = " ".join(first["body"].split())
    quote = quote if len(quote) <= QUOTE_LENGTH else quote[: QUOTE_LENGTH - 1] + "…"
    link = f" ({thread['url']})" if thread["url"] else ""
    body = f"> @{first['author']}: {quote}{link}\n\n{thread['reply']}"
    return _gh_json(["api", f"repos/{{owner}}/{{repo}}/issues/{number}/comments", "-f", f"body={body}"], repo_dir)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fetch_raw(number: int, repo_dir: Path) -> Tuple[Dict, List[Dict]]:
    view = _gh_json(["pr", "view", str(number), "--json", "number,title,url,state,comments,reviews"], repo_dir)
    # {owner}/{repo} are gh placeholders filled from repo_dir's remote; --slurp wraps the pages in one array.
    pages = _gh_json(["api", f"repos/{{owner}}/{{repo}}/pulls/{number}/comments", "--paginate", "--slurp"], repo_dir)
    return view, [item for page in pages for item in page]


def _location(comment: Dict) -> str:
    location = comment.get("path", "")
    line = comment.get("line") or comment.get("original_line")
    if location and line:
        location += f":{line}"
    return location


def _fetch(number: int, repo_dir: Path) -> Dict:
    try:
        view, inline = _fetch_raw(number, repo_dir)
    except (OSError, subprocess.SubprocessError, ValueError) as e:
        return {"number": number, "title": "", "url": "", "state": "", "error": str(e), "notes": []}

    notes: List[Dict] = []
    for comment in view.get("comments", []):
        notes.append(_note("comment", comment.get("author"), comment.get("createdAt"), comment.get("body"),
                           comment.get("url", "")))
    for review in view.get("reviews", []):
        if (review.get("body") or "").strip():
            notes.append(_note("review", review.get("author"), review.get("submittedAt"), review.get("body"), "",
                               state=review.get("state", "")))
    for comment in inline:
        notes.append(_note("inline", comment.get("user"), comment.get("created_at"), comment.get("body"),
                           comment.get("html_url", ""), location=_location(comment)))
    notes.sort(key=lambda note: note["created_at"])
    return {"number": view.get("number", number), "title": view.get("title", ""), "url": view.get("url", ""),
            "state": view.get("state", ""), "error": "", "notes": notes}


def _note(kind: str, author, created_at, body, url: str, location: str = "", state: str = "") -> Dict:
    login = (author or {}).get("login", "") if isinstance(author, dict) else ""
    return {"kind": kind, "author": login, "created_at": created_at or "", "body": body or "", "url": url,
            "location": location, "state": state}


def _gh_json(args: List[str], repo_dir: Path):
    result = subprocess.run(["gh"] + args, cwd=str(repo_dir), capture_output=True, text=True,
                            timeout=GH_TIMEOUT_SECONDS, check=False)
    if result.returncode != 0:
        lines = result.stderr.strip().splitlines()
        raise ValueError(f"gh {args[0]} failed: {lines[-1] if lines else 'exit ' + str(result.returncode)}")
    return json.loads(result.stdout)
