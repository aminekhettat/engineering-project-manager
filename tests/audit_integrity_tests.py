#!/usr/bin/env python3
"""Guard explicit management activation against silent downgrade to legacy."""

from test_support import SCRIPTS

import json
import copy
import subprocess
import tempfile
import unittest
from pathlib import Path

from configuration_audit import audit as configuration_audit
from verification_evidence_audit import audit as evidence_audit
from baseline_manager import blocking_changes, immutable_payload, main as baseline_main
from pm_common import canonical_sha256


MODELS = (
    (configuration_audit, "08-configuration/CONFIGURATION-MANAGEMENT.json",
     "08-configuration/BASELINE-REGISTRY.json"),
    (evidence_audit, "05-verification/EVIDENCE-MANAGEMENT.json",
     "05-verification/EVIDENCE.json"),
)


class EnablementIntegrityTests(unittest.TestCase):
    def git(self, root, *args):
        result = subprocess.run(
            ["git", *args], cwd=root, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        self.assertEqual(0, result.returncode, result.stdout)
        return result.stdout.strip()

    def initialize(self, root):
        self.git(root, "init", "-q")
        self.git(root, "config", "user.name", "Project Manager Test")
        self.git(root, "config", "user.email", "test@example.invalid")
        (root / "README.md").write_text("Legacy project\n", encoding="utf-8")
        self.git(root, "add", "README.md")
        self.git(root, "commit", "-qm", "Legacy project")

    def test_true_legacy_project_still_skips_both_models(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.initialize(root)
            for audit, _, _ in MODELS:
                with self.subTest(audit=audit.__module__):
                    self.assertEqual(([], []), audit(root, strict=True))
                    errors, warnings = audit(root)
                    self.assertEqual([], errors)
                    self.assertTrue(warnings)
            self.assertEqual("", self.git(root, "status", "--porcelain"))

    def test_orphan_authoritative_registry_is_not_legacy(self):
        for audit, _, registry in MODELS:
            with self.subTest(audit=audit.__module__), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.initialize(root)
                path = root / registry
                path.parent.mkdir(parents=True)
                path.write_text("{}\n", encoding="utf-8")
                before = path.read_bytes()
                errors, _ = audit(root, strict=True)
                self.assertTrue(any("enablement marker is missing" in item for item in errors), errors)
                self.assertEqual(before, path.read_bytes())

    def test_deleting_all_state_cannot_disable_previously_enabled_model(self):
        for audit, marker, registry in MODELS:
            with self.subTest(audit=audit.__module__), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.initialize(root)
                for relative in (marker, registry):
                    path = root / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(json.dumps({"enabled": True}) + "\n", encoding="utf-8")
                self.git(root, "add", marker, registry)
                self.git(root, "commit", "-qm", "Enable management")
                self.git(root, "rm", marker, registry)
                self.git(root, "commit", "-qm", "Remove management files")
                errors, _ = audit(root, strict=True)
                self.assertTrue(any("enablement marker is missing" in item for item in errors), errors)
                self.assertEqual("", self.git(root, "status", "--porcelain"))

    def baseline_fixture(self, root):
        self.initialize(root)
        head = self.git(root, "rev-parse", "HEAD")
        configuration = root / "08-configuration"
        (configuration / "baselines").mkdir(parents=True)
        records = {}
        for number in range(1, 4):
            bid = f"BL-{number:03d}"
            history = [{"previous_status": None, "new_status": "DRAFT"},
                       {"previous_status": "DRAFT", "new_status": "FROZEN"}]
            status = "FROZEN"
            replacement = None
            if number < 3:
                history.extend([{"previous_status": "FROZEN", "new_status": "RELEASED"},
                                {"previous_status": "RELEASED", "new_status": "SUPERSEDED"}])
                status = "SUPERSEDED"
                replacement = f"BL-{number + 1:03d}"
            record = {
                "Baseline_ID": bid, "Status": status, "Purpose": "Supersession fixture",
                "Created_At": "2026-01-01T00:00:00Z", "Created_By": "Test",
                "Git_Commit": head, "Requirements_Snapshot": [], "Configuration_Items": [],
                "Related_Change_Requests": [], "Open_Deviations": [], "Open_Problems_Accepted": [],
                "History": history, "Superseded_By": replacement,
            }
            record["Snapshot_Integrity_SHA256"] = canonical_sha256(immutable_payload(record))
            records[bid] = record
        files = {
            "CONFIGURATION-MANAGEMENT.json": {"enabled": True, "model_version": "1.1"},
            "CHANGE-REQUESTS.json": {"model_version": "1.1", "next_number": 1, "changes": []},
            "BASELINE-REGISTRY.json": {"model": "PROJECT_MANAGER_BASELINE_MANAGEMENT", "model_version": "1.1",
                                       "registry_revision": 0, "next_number": 4, "baselines": list(records)},
        }
        for filename, value in files.items():
            (configuration / filename).write_text(json.dumps(value), encoding="utf-8")
        (root / "00-project").mkdir()
        (root / "00-project/STATUS.md").write_text("- Current Baseline: BL-003\n", encoding="utf-8")
        self.save_baselines(root, records)
        return records

    def save_baselines(self, root, records):
        for bid, record in records.items():
            (root / "08-configuration/baselines" / f"{bid}.json").write_text(
                json.dumps(record), encoding="utf-8"
            )

    def test_baseline_supersession_chain_validates_and_rejects_self_or_cycles(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pristine = self.baseline_fixture(root)
            self.assertEqual(([], []), configuration_audit(root, strict=True))
            for replacement in ("BL-001", "BL-002"):
                records = copy.deepcopy(pristine)
                records[replacement]["Superseded_By"] = "BL-001"
                self.save_baselines(root, records)
                errors, _ = configuration_audit(root, strict=True)
                self.assertTrue(any("cyclic baseline supersession" in item for item in errors), errors)

    def test_baseline_supersession_must_end_in_a_release_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            records = self.baseline_fixture(root)
            records["BL-003"]["Status"] = "DRAFT"
            records["BL-003"]["History"] = [{"previous_status": None, "new_status": "DRAFT"}]
            self.save_baselines(root, records)
            errors, _ = configuration_audit(root, strict=True)
            self.assertTrue(any("replacement chain must end in FROZEN or RELEASED" in item for item in errors), errors)

    def test_baseline_cli_rejects_self_supersession_without_record_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            records = self.baseline_fixture(root)
            records["BL-003"]["Status"] = "RELEASED"
            records["BL-003"]["History"].append({"previous_status": "FROZEN", "new_status": "RELEASED"})
            self.save_baselines(root, records)
            path = root / "08-configuration/baselines/BL-003.json"
            before = path.read_bytes()
            result = baseline_main(["--project", str(root), "supersede", "BL-003",
                                    "--by", "BL-003", "--actor", "Test"])
            self.assertEqual(2, result)
            self.assertEqual(before, path.read_bytes())

    def test_stable_item_blocking_keeps_nonrequirement_ids_exact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / "08-configuration"
            folder.mkdir()
            changes = [
                {"Change_ID": "CR-001", "Status": "IMPLEMENTING", "Changed_Items": ["M5_SYS2_REQ_001@R1"]},
                {"Change_ID": "CR-002", "Status": "DEFERRED", "Changed_Items": ["CI-002"]},
                {"Change_ID": "CR-003", "Status": "SUBMITTED", "Changed_Items": ["CI-002-other"]},
                {"Change_ID": "CR-004", "Status": "IMPLEMENTING", "Changed_Items": ["OTHER_SYS2_REQ_001@R1"]},
            ]
            (folder / "CHANGE-REQUESTS.json").write_text(json.dumps({"changes": changes}), encoding="utf-8")
            candidate = {"Requirements_Snapshot": [{"id": "M5_SYS2_REQ_001@R2"}],
                         "Configuration_Items": [{"id": "CI-002"}]}
            self.assertEqual((["CR-001"], ["CR-002"]), blocking_changes(root, candidate))


if __name__ == "__main__":
    unittest.main(verbosity=2)
