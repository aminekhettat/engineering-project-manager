#!/usr/bin/env python3
"""Real management-to-release integration, legacy opt-in and source isolation."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from management_audit import audit, MODELS
from management_init import initialize
from pm_common import requirement_definitions
from release_fixture_test import build_fixture

SCRIPTS = Path(__file__).resolve().parent
REQ = "FIXTURE_SWE1_REQ_001@R1"
PROOF = "05-verification/software/SWE-VERIFICATION-REPORT.md"


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        build_fixture(self.root)
        with (self.root / ".gitignore").open("a") as stream:
            stream.write("\n**/.*.lock\n")
        for args in (("init", "-q"), ("config", "user.name", "Project Manager Test"),
                     ("config", "user.email", "test@example.invalid"),
                     ("remote", "add", "origin", "https://git.example.invalid/fixture.git")):
            self.run_command(["git", *args])

    def run_command(self, command, expected=0, env=None):
        result = subprocess.run(command, cwd=self.root, capture_output=True, text=True,
                                env=env, timeout=90)
        self.assertEqual(expected, result.returncode, result.stdout + result.stderr)
        return result.stdout + result.stderr

    def cli(self, script, *args, expected=0):
        return self.run_command([sys.executable, "-B", str(SCRIPTS / script), "--project", str(self.root), *args], expected)

    def commit(self, message):
        self.run_command(["git", "add", "."])
        self.run_command(["git", "commit", "-qm", message])

    def test_legacy_opt_in_preserves_documents_and_detects_deleted_models(self):
        old = (self.root / "09-risks/RISK-REGISTER.md").read_bytes()
        self.assertEqual(([], []), audit(self.root, release=True))
        initialize(self.root, "Coordinator")
        initialize(self.root, "Coordinator")
        self.assertEqual(old, (self.root / "09-risks/RISK-REGISTER.md").read_bytes())
        self.assertEqual(([], []), audit(self.root, release=True))
        for _, relative, _, _ in MODELS:
            self.assertTrue((self.root / relative).is_file())
        self.commit("Enable project management")
        (self.root / "09-risks/RISKS.json").unlink()
        self.assertTrue(any("missing" in error for error in audit(self.root)[0]))

    def test_intake_documents_are_not_engineering_requirement_definitions(self):
        before = [item["id"] for item in requirement_definitions(self.root)]
        path = self.root / "01-requirements/intake/external.md"
        path.parent.mkdir(parents=True)
        path.write_text("[EXTERNAL_SYS1_REQ_001@R1]\nText:\nThe source shall remain external.\n[END_REQ]\n")
        self.assertEqual(before, [item["id"] for item in requirement_definitions(self.root)])

    def test_complete_managed_project_passes_real_release_and_detects_tampering(self):
        initialize(self.root, "Coordinator")
        self.cli("change_manager.py", "init")
        self.cli("baseline_manager.py", "init", "--actor", "Configuration Manager")
        self.cli("verification_evidence.py", "init", "--actor", "Verifier")
        source = self.root / "01-requirements/intake/source.txt"
        source.write_text("The delivered software must preserve verified records.\n")
        self.cli("risk_manager.py", "create", "--title", "Lost evidence", "--owner", "Quality",
                 "--description", "Evidence could be lost", "--probability", "3", "--impact", "5", "--actor", "Coordinator")
        self.cli("problem_manager.py", "create", "--title", "Fixture issue", "--owner", "Builder",
                 "--description", "Observed fixture defect", "--severity", "HIGH", "--actor", "Coordinator")
        self.cli("milestone_manager.py", "create", "--title", "Verified delivery", "--owner", "Quality",
                 "--due-date", "2099-12-31", "--criterion", "Verification reviewed", "--task", "TASK-001",
                 "--release-required", "--actor", "Coordinator")
        self.cli("intake_manager.py", "create", "--title", "Synthetic source", "--owner", "Analyst",
                 "--source-key", "SOURCE", "--version", "1", "--reference", "Synthetic customer document",
                 "--license", "Synthetic test content", "--confidentiality", "PUBLIC", "--file",
                 "01-requirements/intake/source.txt", "--actor", "Analyst")
        self.cli("intake_manager.py", "obligation", "SRC-0001", "--key", "O-1", "--locator", "Section 1",
                 "--text", "Preserve verified records", "--actor", "Analyst")
        self.cli("intake_manager.py", "review", "SRC-0001", "--rationale", "Reviewed complete inventory", "--actor", "Reviewer")
        errors, _ = audit(self.root, release=True)
        for kind in ("risks", "problems", "milestones", "compliance"):
            self.assertTrue(any(error.startswith(kind + ":") for error in errors), errors)

        self.cli("risk_manager.py", "transition", "RISK-0001", "--to", "ACCEPTED", "--reason",
                 "Accountable owner accepts this synthetic risk", "--review-date", "2099-12-31", "--actor", "Risk owner")
        for target in ("TRIAGED", "IN_PROGRESS", "RESOLVED", "VERIFIED", "CLOSED"):
            extra = ["--disposition", "FIXED"] if target == "RESOLVED" else []
            if target in {"RESOLVED", "VERIFIED"}:
                extra += ["--evidence", PROOF]
            self.cli("problem_manager.py", "transition", "PRB-0001", "--to", target,
                     "--reason", "Fixture result reviewed", "--actor", "Reviewer", *extra)
        self.cli("milestone_manager.py", "transition", "MS-0001", "ACTIVE", "--actor", "Coordinator")
        self.cli("milestone_manager.py", "transition", "MS-0001", "ACHIEVED", "--actor", "Coordinator",
                 "--reviewer", "Reviewer", "--review-note", "Criterion verified", "--criterion-evidence", "1=" + PROOF)
        self.cli("verification_evidence.py", "create", "--requirement-id", REQ, "--title", "Fixture verification",
                 "--objective", "Preserve verified records", "--expected-result", "Audits pass", "--actor", "Verifier")
        self.cli("compliance_manager.py", "create", "--source", "SRC-0001", "--obligation", "O-1", "--owner", "Analyst", "--actor", "Analyst")
        self.cli("compliance_manager.py", "map", "CMP-0001", "--requirement", REQ, "--evidence", "EV-001",
                 "--rationale", "Exact revision implements the obligation", "--actor", "Analyst")
        self.assertTrue(any("PASS evidence" in error for error in audit(self.root, release=True)[0]))
        self.commit("Complete engineering and management candidate")
        self.cli("baseline_manager.py", "create", "--purpose", "Managed release candidate", "--actor", "Configuration Manager")
        self.commit("Create candidate baseline")
        self.cli("baseline_manager.py", "freeze", "BL-001", "--actor", "Configuration Manager")
        self.commit("Freeze candidate baseline")
        self.cli("verification_evidence.py", "record-result", "EV-001", "--result", "PASS", "--actor", "Verifier",
                 "--summary", "Synthetic fixture verification completed", "--baseline", "BL-001", "--artifact", PROOF)
        self.commit("Record verification result")
        self.assertEqual(([], []), audit(self.root, release=True))
        head = self.run_command(["git", "rev-parse", "HEAD"]).strip()
        output = self.run_command([sys.executable, "-B", str(SCRIPTS / "release_check.py"), str(self.root), "--baseline", "BL-001"],
                                  env=dict(os.environ, CI_COMMIT_SHA=head))
        self.assertIn("RELEASE CHECK: PASS", output)
        source.write_text("Changed source after review\n")
        self.assertTrue(any("sources:" in error for error in audit(self.root, release=True)[0]))


if __name__ == "__main__":
    unittest.main()
