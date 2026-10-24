"""SidecarStore: the single store for comment threads on a reviewed doc.

Owns `<doc>.review.json` (schema v1: threads[], each with an anchor, a status, and replies[]).
Every mutation locks, re-reads the file fresh, applies one operation, and atomically replaces
the file, so a browser POST and a CLI `reply` running at the same moment can't corrupt it or
drop either write. See LocalDocReview_TDD.md, Best Practices and Edge Case E5.
"""
import fcntl
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

SCHEMA_VERSION = 1

ALLOWED_STATUSES_BY_ACTOR = {
    "engineer": {"open", "ready", "resolved"},
    "agent": {"addressed"},
}


class SidecarStore:
    def __init__(self, doc_path: Path):
        self._doc_path = doc_path
        self._sidecar_path = doc_path.parent / (doc_path.name + ".review.json")

    def load(self) -> Dict:
        # Reads never lock: the atomic rename in _write_atomic guarantees a reader only ever
        # sees a complete, previously-committed file, never a half-written one.
        return self._read()

    def add_thread(self, anchor: Dict, author: str, text: str) -> str:
        def mutate(data: Dict) -> str:
            thread_id = self._next_id(data)
            data["threads"].append({
                "id": thread_id,
                "status": "open",
                "created_by": author,
                "created_at": _now(),
                "anchor": anchor,
                "replies": [{"author": author, "text": text, "at": _now()}],
            })
            return thread_id

        return self._mutate(mutate)

    def add_reply(self, thread_id: str, author: str, text: str) -> None:
        def mutate(data: Dict) -> None:
            thread = self._find_thread(data, thread_id)
            thread["replies"].append({"author": author, "text": text, "at": _now()})

        self._mutate(mutate)

    def set_status(self, thread_id: str, status: str, actor: str) -> None:
        if status not in ALLOWED_STATUSES_BY_ACTOR.get(actor, set()):
            raise PermissionError(f"{actor} may not set status to {status!r}")

        def mutate(data: Dict) -> None:
            thread = self._find_thread(data, thread_id)
            thread["status"] = status

        self._mutate(mutate)

    def _read(self) -> Dict:
        if not self._sidecar_path.is_file():
            return {"version": SCHEMA_VERSION, "doc": self._doc_path.name, "threads": []}
        return json.loads(self._sidecar_path.read_text())

    def _mutate(self, mutate):
        self._sidecar_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self._sidecar_path.parent / (self._sidecar_path.name + ".lock")
        # Lock a side file, not the sidecar itself: flock follows the inode, and the sidecar's
        # inode changes on every atomic replace below, so locking it directly would let a
        # second writer acquire a lock on an already-replaced (stale) inode.
        with open(lock_path, "a+") as lock_file:
            fcntl.flock(lock_file, fcntl.LOCK_EX)
            try:
                data = self._read()
                result = mutate(data)
                self._write_atomic(data)
                return result
            finally:
                fcntl.flock(lock_file, fcntl.LOCK_UN)

    def _write_atomic(self, data: Dict) -> None:
        fd, tmp_path = tempfile.mkstemp(dir=self._sidecar_path.parent, prefix=self._sidecar_path.name)
        try:
            with os.fdopen(fd, "w") as tmp_file:
                json.dump(data, tmp_file, indent=2)
            os.replace(tmp_path, self._sidecar_path)
        except BaseException:
            os.unlink(tmp_path)
            raise

    def _next_id(self, data: Dict) -> str:
        existing = [int(t["id"][1:]) for t in data["threads"] if t["id"].startswith("t") and t["id"][1:].isdigit()]
        return "t" + str((max(existing) + 1) if existing else 1)

    def _find_thread(self, data: Dict, thread_id: str) -> Dict:
        for thread in data["threads"]:
            if thread["id"] == thread_id:
                return thread
        raise KeyError(f"no thread {thread_id!r} in {self._sidecar_path}")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")
