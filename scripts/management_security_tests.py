#!/usr/bin/env python3
"""Independent negative tests of management boundaries and enablement recovery."""

import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import management_audit
import management_init
from management_common import (RecordError, Store, artifact_errors,
                               link_errors, project_file, seal_artifact, task_records)


class ManagementSecurityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="pm-management-security-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def write(self, relative, value):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")
        return path

    def tracked(self):
        for args in (("init", "-q"), ("config", "user.name", "Test maintainer"),
                     ("config", "user.email", "test@example.invalid"), ("add", "."),
                     ("commit", "-qm", "Track test management state")):
            subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True)

    def test_git_metadata_guard_is_case_insensitive(self):
        for relative in (".git/config", ".GIT/config", ".Git/config", "nested/.GiT/config"):
            with self.subTest(relative=relative), self.assertRaises(RecordError):
                project_file(self.root, relative, must_exist=False)

    def test_runtime_management_files_cannot_be_sealed_as_proof(self):
        paths = [management_audit.MARKER, "00-project/management/.milestones.lock"]
        for _kind, relative, _prefix, _module in management_audit.MODELS:
            paths.extend((relative, str(Path(relative).with_suffix(".md")).replace("\\", "/")))
        for relative in paths:
            self.write(relative, "Synthetic runtime state")
            with self.subTest(relative=relative), self.assertRaises(RecordError):
                seal_artifact(self.root, relative)

    def test_hashes_external_review_and_detects_changes(self):
        proof = self.write("07-quality/reviews/acceptance.md", "Independent review fixture")
        artifact = seal_artifact(self.root, "07-quality/reviews/acceptance.md")
        self.assertEqual(artifact_errors(self.root, artifact), [])
        proof.write_text("Changed evidence", encoding="utf-8")
        self.assertTrue(artifact_errors(self.root, artifact))

    def test_deleted_marker_and_all_registries_cannot_hide_enablement(self):
        management_init.initialize(self.root, "Coordinator")
        self.tracked()
        (self.root / management_audit.MARKER).unlink()
        for _kind, relative, _prefix, _module in management_audit.MODELS:
            (self.root / relative).unlink()
        errors, _ = management_audit.audit(self.root, release=True)
        self.assertTrue(any("activation" in item for item in errors))
        self.assertTrue(any("previously enabled" in item for item in errors))
        with self.assertRaises(RecordError):
            management_init.initialize(self.root, "Coordinator")
        self.assertFalse((self.root / management_audit.MARKER).exists())

    def test_new_and_old_project_initialization_preserves_tasks_and_records(self):
        task_path = self.write("00-project/management/TASKS.json", json.dumps({"tasks": [{"id": "TASK-001", "status": "DONE"}]}))
        task_bytes = task_path.read_bytes()
        management_init.initialize(self.root, "Coordinator")
        original = {(self.root / relative): (self.root / relative).read_bytes()
                    for _kind, relative, _prefix, _module in management_audit.MODELS}
        management_init.initialize(self.root, "Coordinator")
        self.assertEqual(task_path.read_bytes(), task_bytes)
        self.assertTrue(all(path.read_bytes() == value for path, value in original.items()))
        self.assertEqual(management_audit.audit(self.root), ([], []))

    def test_enabled_project_cannot_recreate_missing_uncommitted_registry(self):
        management_init.initialize(self.root, "Coordinator")
        path = self.root / management_audit.MODELS[0][1]
        path.unlink()
        with self.assertRaises(RecordError):
            management_init.initialize(self.root, "Coordinator")
        self.assertFalse(path.exists())
        self.assertTrue(management_audit.audit(self.root)[0])

    def test_malformed_marker_never_enables_or_overwrites_stores(self):
        marker = self.write(management_audit.MARKER, '{"enabled":true,"enabled":false}')
        before = marker.read_bytes()
        with self.assertRaises(RecordError):
            management_init.initialize(self.root, "Coordinator")
        self.assertEqual(marker.read_bytes(), before)
        self.assertTrue(management_audit.audit(self.root)[0])
        self.assertFalse((self.root / management_audit.MODELS[0][1]).exists())

    def test_task_status_wrong_shape_returns_domain_error(self):
        self.write("00-project/management/TASKS.json", json.dumps({"tasks": [{"id": "TASK-001", "status": []}]}))
        with self.assertRaises(RecordError):
            task_records(self.root)
        self.assertTrue(link_errors(self.root, {"tasks": ["TASK-001"]}))

    def test_missing_task_and_requirement_references_fail(self):
        self.write("00-project/management/TASKS.json", '{"tasks":[]}')
        self.assertTrue(link_errors(self.root, {"tasks": ["TASK-999"]}))
        self.assertTrue(link_errors(self.root, {"requirements": ["FIXTURE_SWE1_REQ_001@R1"]}))

    def test_git_inspection_failure_cannot_silently_reinitialize(self):
        registry = Store(self.root, "management/TEST.json", "test", "TST")
        with patch("management_common.subprocess.run", side_effect=subprocess.TimeoutExpired("git", 20)):
            with self.assertRaises(RecordError):
                registry.initialize("Coordinator")
        self.assertFalse(registry.path.exists())

    def test_git_error_in_existing_repository_cannot_be_treated_as_legacy(self):
        registry = Store(self.root, "management/TEST.json", "test", "TST")
        (self.root / ".git").mkdir()
        failed = subprocess.CompletedProcess(["git"], 128, stdout="", stderr="Synthetic Git failure")
        with patch("management_common.subprocess.run", return_value=failed):
            with self.assertRaises(RecordError):
                registry.initialize("Coordinator")
        self.assertFalse(registry.path.exists())

    def test_new_git_repository_without_commits_can_initialize(self):
        subprocess.run(["git", "-C", str(self.root), "init", "-q"], check=True, capture_output=True)
        registry = Store(self.root, "management/TEST.json", "test", "TST")
        self.assertEqual(registry.initialize("Coordinator")["records"], [])

    def test_symlink_requirement_escape_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="pm-external-requirement-") as external:
            outside = Path(external) / "requirements.md"
            outside.write_text("[FIXTURE_SWE1_REQ_001@R1]\nText:\nExternal text.\n[END_REQ]\n", encoding="utf-8")
            link = self.root / "01-requirements/external.md"
            link.parent.mkdir()
            try:
                link.symlink_to(outside)
            except OSError:
                self.skipTest("host does not permit symlink creation")
            self.assertTrue(link_errors(self.root, {"requirements": ["FIXTURE_SWE1_REQ_001@R1"]}))

    def test_in_project_alias_cannot_bypass_self_proof_guard(self):
        state = self.write("09-risks/RISKS.json", "Synthetic runtime state")
        alias = self.root / "proof.md"
        try:
            alias.symlink_to(state)
        except OSError:
            self.skipTest("host does not permit symlink creation")
        with self.assertRaises(RecordError):
            seal_artifact(self.root, "proof.md")

    def test_store_rechecks_registry_and_lock_after_construction(self):
        registry = Store(self.root, "management/TEST.json", "test", "TST")
        registry.initialize("Coordinator")
        with tempfile.TemporaryDirectory(prefix="pm-external-control-") as outside:
            target = Path(outside) / "untouched.txt"
            target.write_text("Untouched external file", encoding="utf-8")
            for controlled in (registry.path, registry.lock_path):
                original = controlled.read_bytes()
                controlled.unlink()
                try:
                    controlled.symlink_to(target)
                except OSError:
                    controlled.write_bytes(original)
                    self.skipTest("host does not permit symlink creation")
                with self.assertRaises(RecordError):
                    registry.initialize("Coordinator")
                self.assertEqual(target.read_text(encoding="utf-8"), "Untouched external file")
                controlled.unlink()
                controlled.write_bytes(original)

    def test_in_project_directory_alias_cannot_redirect_registry_identity(self):
        registry = Store(self.root, "management/TEST.json", "test", "TST")
        actual = self.root / "elsewhere"
        actual.mkdir()
        alias = self.root / "management"
        try:
            alias.symlink_to(actual, target_is_directory=True)
        except OSError:
            self.skipTest("host does not permit symlink creation")
        with self.assertRaises(RecordError):
            registry.initialize("Coordinator")
        self.assertEqual(list(actual.iterdir()), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
