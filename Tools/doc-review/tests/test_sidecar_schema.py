"""Category 1 (JSON Deserialization) tests for LocalDocReview.

This tool has no [JsonProperty] Config classes -- its equivalent data contract is the
`<doc>.review.json` sidecar schema owned by SidecarStore. These tests play the same role
Phase5_UnitTests.md asks of Config-class deserialization tests: every schema field populates
correctly on load, an unrecognized field never throws, and fields optional at the anchor level
still leave the required thread fields populated.

    python3 -m unittest discover -s Tools/doc-review/tests -p 'test_*.py'
"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parents[1]
if str(TOOL_DIR) not in sys.path:
    sys.path.insert(0, str(TOOL_DIR))

from sidecar_store import SCHEMA_VERSION, SidecarStore  # noqa: E402


class SidecarSchemaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="sidecar-schema-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.doc_path = self.tmp / "LocalDocReview_TDD.md"
        self.doc_path.write_text("# Title\n")

    def sidecar_path(self) -> Path:
        return self.tmp / (self.doc_path.name + ".review.json")

    def test_load_missing_file_returns_default_schema_with_all_fields(self):
        data = SidecarStore(self.doc_path).load()

        self.assertEqual(data["version"], SCHEMA_VERSION, "default schema must stamp the current version")
        self.assertEqual(data["doc"], self.doc_path.name, "default schema must name the doc it belongs to")
        self.assertEqual(data["threads"], [], "default schema must start with no threads")

    def test_add_thread_round_trip_populates_all_thread_fields(self):
        anchor = {
            "kind": "text",
            "file": self.doc_path.name,
            "quote": "the quoted sentence",
            "prefix": "before ",
            "suffix": " after",
            "heading_path": ["Architecture"],
        }
        store = SidecarStore(self.doc_path)

        thread_id = store.add_thread(anchor, "engineer", "please clarify this")

        # A second, independent SidecarStore forces a real read of the file just written --
        # this is the deserialization half of the round trip, not just the in-memory mutation.
        reloaded = SidecarStore(self.doc_path).load()
        self.assertEqual(len(reloaded["threads"]), 1, "add_thread must persist exactly one thread")
        thread = reloaded["threads"][0]
        self.assertEqual(thread["id"], thread_id, "persisted id must match the id add_thread returned")
        self.assertEqual(thread["status"], "open", "a new thread must start open")
        self.assertEqual(thread["created_by"], "engineer", "created_by must record the author passed in")
        self.assertTrue(thread["created_at"], "created_at must be populated, not empty")
        self.assertEqual(thread["anchor"], anchor, "anchor must round-trip unchanged")
        self.assertEqual(len(thread["replies"]), 1, "add_thread must seed exactly one reply")
        reply = thread["replies"][0]
        self.assertEqual(reply["author"], "engineer")
        self.assertEqual(reply["text"], "please clarify this")
        self.assertTrue(reply["at"], "reply timestamp must be populated, not empty")

    def test_load_tolerates_unrecognized_top_level_field(self):
        self.sidecar_path().write_text(json.dumps({
            "version": SCHEMA_VERSION,
            "doc": self.doc_path.name,
            "threads": [],
            "future_field_this_code_does_not_know_about": {"anything": True},
        }))

        data = SidecarStore(self.doc_path).load()

        self.assertEqual(data["threads"], [], "load must not throw on an unrecognized top-level field")

    def test_load_tolerates_unrecognized_thread_field(self):
        self.sidecar_path().write_text(json.dumps({
            "version": SCHEMA_VERSION,
            "doc": self.doc_path.name,
            "threads": [{
                "id": "t1",
                "status": "open",
                "created_by": "engineer",
                "created_at": "2026-10-22T09:00:00",
                "anchor": {"kind": "text", "file": self.doc_path.name, "quote": "x"},
                "replies": [{"author": "engineer", "text": "x", "at": "2026-10-22T09:00:00"}],
                "priority": "high",  # unknown to this schema version
            }],
        }))
        store = SidecarStore(self.doc_path)

        store.add_reply("t1", "agent", "on it")  # must not throw despite the unknown field

        reloaded = store.load()
        thread = reloaded["threads"][0]
        self.assertEqual(thread["priority"], "high", "an unrecognized field must survive a mutation untouched")
        self.assertEqual(len(thread["replies"]), 2, "the new reply must still be appended correctly")

    def test_add_thread_with_optional_anchor_fields_absent_still_populates_required_thread_fields(self):
        # prefix/suffix/heading_path are optional on a text anchor (anchor_resolver reads them
        # with .get(..., default)) -- only kind/file/quote are required.
        minimal_anchor = {"kind": "text", "file": self.doc_path.name, "quote": "a quote"}
        store = SidecarStore(self.doc_path)

        thread_id = store.add_thread(minimal_anchor, "engineer", "note")

        thread = SidecarStore(self.doc_path).load()["threads"][0]
        self.assertEqual(thread["id"], thread_id)
        self.assertEqual(thread["status"], "open")
        self.assertEqual(thread["created_by"], "engineer")
        self.assertTrue(thread["created_at"])
        self.assertEqual(thread["anchor"], minimal_anchor)


if __name__ == "__main__":
    unittest.main()
