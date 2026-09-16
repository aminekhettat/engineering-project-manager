#!/usr/bin/env python3
"""Behavior and fault isolation for management state persistence."""

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from management_common import (Store, RecordError, add_record, get_record,
                               artifact_errors, seal_artifact, project_file)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = Store(self.root, "management/RECORDS.json", "test", "TEST")
        self.store.initialize("Coordinator")

    def create(self, title="First"):
        return self.store.update("Coordinator", "create", lambda data: add_record(data, "TEST", title, "Owner", "OPEN")["id"])

    def test_replay_and_idempotent_init_preserve_records(self):
        initial = self.create()
        self.assertEqual(initial, self.store.initialize("Other actor"))
        updated = self.store.update("Reviewer", "close", self.close)
        self.assertEqual("CLOSED", updated["records"][0]["status"])
        self.assertEqual([], self.store.errors(updated))
        self.assertEqual("OPEN", updated["history"][0]["after"]["status"])
        self.assertEqual("Reviewer", updated["history"][1]["actor"])

    @staticmethod
    def close(data):
        record = get_record(data, "TEST-0001")
        record["status"] = "CLOSED"
        return record["id"]

    def test_rejected_validation_and_exception_leave_canonical_bytes_unchanged(self):
        self.create()
        before = self.store.path.read_bytes()
        with self.assertRaisesRegex(RecordError, "Not accepted"):
            self.store.update("Owner", "close", self.close, lambda *_: ["Not accepted"])
        self.assertEqual(before, self.store.path.read_bytes())
        def broken(data):
            data["records"][0]["status"] = "CLOSED"
            raise RuntimeError("Interrupted before commit")
        with self.assertRaises(RuntimeError):
            self.store.update("Owner", "close", broken)
        self.assertEqual(before, self.store.path.read_bytes())
        with patch("management_common.write_json_atomic", side_effect=OSError("Disk unavailable")):
            with self.assertRaises(OSError):
                self.store.update("Owner", "close", self.close)
        self.assertEqual(before, self.store.path.read_bytes())

    def test_history_snapshot_metadata_and_duplicate_id_tampering_rejected(self):
        good = self.create()
        corrupted = []
        for mutate in (lambda d: d["records"][0].update(title="Edited outside manager"),
                       lambda d: d["history"][0].update(actor="Forged"),
                       lambda d: d.update(next_id=10**50),
                       lambda d: d["records"].append(copy.deepcopy(d["records"][0])),
                       lambda d: d.update(history=[])):
            data = copy.deepcopy(good)
            mutate(data)
            corrupted.append(data)
        for data in corrupted + [None, [], {"schema_version": True}, {**good, "records": [None]}]:
            with self.subTest(data_type=type(data).__name__):
                self.assertTrue(self.store.errors(data))

    def test_callback_cannot_rewrite_history_or_multiple_records(self):
        self.create()
        self.create("Second")
        before = self.store.path.read_bytes()
        def multiple(data):
            for record in data["records"]:
                record["status"] = "CLOSED"
            return "TEST-0001"
        def history(data):
            data["history"] = []
            return "TEST-0001"
        for operation in (multiple, history):
            with self.assertRaises(RecordError):
                self.store.update("Owner", "alter", operation)
            self.assertEqual(before, self.store.path.read_bytes())

    def test_json_duplicate_keys_rejected(self):
        self.store.path.write_text('{"kind":"test","kind":"other"}')
        with self.assertRaisesRegex(RecordError, "Duplicate"):
            self.store.read()

    def test_concurrent_writers_keep_all_unique_ids_and_history(self):
        code = """import sys
sys.path.insert(0,sys.argv[1])
from management_common import Store,add_record
s=Store(sys.argv[2],'management/RECORDS.json','test','TEST')
for i in range(3):
 s.update('Worker','create',lambda d:add_record(d,'TEST','Parallel record','Owner','OPEN')['id'])
"""
        processes = [subprocess.Popen([sys.executable, "-B", "-c", code, str(Path(__file__).parent), str(self.root)],
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(4)]
        for process in processes:
            stdout, stderr = process.communicate(timeout=40)
            self.assertEqual(0, process.returncode, stdout + stderr)
        data = self.store.read()
        self.assertEqual(12, len(data["records"]))
        self.assertEqual(12, len(data["history"]))
        self.assertEqual(13, data["next_id"])

    def test_artifact_digest_and_containment(self):
        (self.root / "proof.txt").write_text("Verified result\n")
        artifact = seal_artifact(self.root, "proof.txt")
        self.assertEqual([], artifact_errors(self.root, artifact))
        (self.root / "proof.txt").write_text("Changed\n")
        self.assertTrue(artifact_errors(self.root, artifact))
        for value in ("..", "../proof.txt", ".", "./", ".git/config", "C:/proof.txt"):
            with self.assertRaises(RecordError):
                project_file(self.root, value, must_exist=False)

    def test_artifact_symlink_escape(self):
        with tempfile.TemporaryDirectory() as outside:
            target = Path(outside) / "proof.txt"
            target.write_text("Outside\n")
            try:
                (self.root / "link.txt").symlink_to(target)
            except OSError:
                self.skipTest("Symlink creation unavailable")
            with self.assertRaises(RecordError):
                seal_artifact(self.root, "link.txt")

    def test_deleted_tracked_registry_cannot_be_reinitialized(self):
        self.create()
        for command in (["init", "-q"], ["config", "user.name", "Test maintainer"],
                        ["config", "user.email", "test@example.invalid"],
                        ["add", "management/RECORDS.json"], ["commit", "-qm", "Tracked registry"]):
            subprocess.run(["git", "-C", str(self.root), *command], check=True, capture_output=True)
        self.store.path.unlink()
        with self.assertRaisesRegex(RecordError, "restore"):
            self.store.initialize("Owner")
        self.assertFalse(self.store.path.exists())


if __name__ == "__main__":
    unittest.main()
