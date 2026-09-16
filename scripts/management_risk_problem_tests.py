#!/usr/bin/env python3
"""Behavioral risk/problem lifecycle, release, evidence and corruption regressions."""

import contextlib
from datetime import date, timedelta
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import problem_manager as problems
import risk_manager as risks


class ManagementRiskProblemTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.project = Path(self.temp.name)
        self.future = (date.today() + timedelta(days=30)).isoformat()
        self.write("proof.txt", "Executed verification with observable acceptance evidence.\n")
        self.write("00-project/management/TASKS.json", json.dumps({"schema_version": 1, "tasks": [{"id": "TASK-001", "status": "READY"}]}))
        self.write("08-configuration/CHANGE-REQUESTS.json", json.dumps({"changes": [{"Change_ID": "CR-001"}]}))
        self.write("01-requirements/software/SWE-REQUIREMENTS.md", """[DEMO_SWE1_REQ_001@R1]
Status: RELEASED
Upstream: ROOT
Allocated_To: NONE
Verification_Method: TEST
Verification_Scope: SOFTWARE
Verification_Activity: VERIFICATION
Verification_Process: SWE6
Text:
The software shall retain the recorded result.
[END_REQ]
""")
        self.cli(risks, "init", "--actor", "coordinator")
        self.cli(problems, "init", "--actor", "coordinator")

    def tearDown(self):
        self.temp.cleanup()

    def write(self, relative, text):
        path = self.project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def cli(self, engine, *args, expected=0):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = engine.main(["--project", str(self.project), *args])
        self.assertEqual(expected, code, output.getvalue())
        return output.getvalue()

    def state(self, engine):
        return json.loads((self.project / engine.REGISTRY).read_text(encoding="utf-8"))

    def unchanged_failure(self, engine, *args):
        before = (self.project / engine.REGISTRY).read_bytes()
        output = self.cli(engine, *args, expected=2)
        self.assertEqual(before, (self.project / engine.REGISTRY).read_bytes())
        return output

    def risk(self, *extra, expected=0):
        return self.cli(risks, "create", "--actor", "risk-owner", "--title", "Interface risk", "--owner", "systems",
                        "--description", "The interface may miss its response budget", "--probability", "4", "--impact", "5",
                        *extra, expected=expected).strip()

    def problem(self, *extra, expected=0):
        return self.cli(problems, "create", "--actor", "reporter", "--title", "Response defect", "--owner", "software",
                        "--description", "The recorded response misses its budget", "--severity", "HIGH", *extra, expected=expected).strip()

    def transition(self, engine, identifier, target, *extra, expected=0):
        return self.cli(engine, "transition", identifier, "--actor", "reviewer", "--to", target,
                        "--reason", "Recorded engineering rationale", *extra, expected=expected)

    def test_risk_mitigation_lifecycle_residual_release_and_traced_reopen(self):
        identifier = self.risk("--mitigation", "Measure and tune response handling", "--task", "TASK-001",
                               "--requirement", "DEMO_SWE1_REQ_001@R1", "--change", "CR-001")
        self.assertEqual("RISK-0001", identifier)
        self.assertTrue(risks.audit(self.project, release=True)[0])
        self.transition(risks, identifier, "MITIGATING")
        self.transition(risks, identifier, "MITIGATED", "--residual-probability", "2", "--residual-impact", "3", "--evidence", "proof.txt")
        self.assertFalse(risks.audit(self.project, release=True)[0])
        record = self.state(risks)["records"][0]
        self.assertEqual(6, risks.effective_score(record))
        self.transition(risks, identifier, "CLOSED", "--evidence", "proof.txt")
        closed = self.state(risks)
        self.assertEqual("CLOSED", closed["records"][0]["status"])
        self.transition(risks, identifier, "OPEN")
        reopened = self.state(risks)
        self.assertEqual(20, risks.effective_score(reopened["records"][0]))
        self.assertIsNone(reopened["records"][0]["closure"])
        self.assertEqual(closed["records"][0], reopened["history"][-2]["after"])
        self.assertTrue(risks.audit(self.project, release=True)[0])

    def test_explicit_risk_acceptance_expiry_and_review_does_not_renew(self):
        identifier = self.risk()
        self.transition(risks, identifier, "ACCEPTED", "--review-date", self.future)
        record = self.state(risks)["records"][0]
        self.assertEqual("reviewer", record["acceptance"]["actor"])
        self.assertEqual(20, risks.effective_score(record))
        self.assertFalse(risks.audit(self.project, release=True)[0])
        self.cli(risks, "review", identifier, "--actor", "risk-owner", "--reason", "Reviewed exposure",
                 "--next-review-date", self.future)
        self.assertEqual(record["acceptance"], self.state(risks)["records"][0]["acceptance"])
        later = (date.fromisoformat(self.future) + timedelta(days=1)).isoformat() + "T12:00:00+00:00"
        with patch.object(risks, "now", return_value=later):
            errors, warnings = risks.audit(self.project, release=True)
        self.assertTrue(errors)
        self.assertTrue(any("expired" in item for item in warnings))
        self.transition(risks, identifier, "ACCEPTED", "--review-date", self.future)
        self.assertGreaterEqual(len(self.state(risks)["history"]), 4)

    def test_risk_invalid_transitions_dates_residuals_and_links_do_not_write(self):
        identifier = self.risk()
        operations = [
            ("transition", identifier, "--actor", "owner", "--to", "CLOSED", "--reason", "No proof"),
            ("transition", identifier, "--actor", "owner", "--to", "MITIGATING", "--reason", "No plan"),
            ("transition", identifier, "--actor", "owner", "--to", "ACCEPTED", "--reason", "Invalid date", "--review-date", "2030-02-30"),
            ("transition", identifier, "--actor", "owner", "--to", "ACCEPTED", "--reason", "Past date", "--review-date", "2000-01-01"),
            ("transition", identifier, "--actor", "owner", "--to", "ACCEPTED", "--reason", "Unproved reduction", "--review-date", self.future, "--residual-probability", "1"),
            ("update", identifier, "--actor", "owner", "--reason", "Invalid rating", "--impact", "6"),
            ("update", identifier, "--actor", "owner", "--reason", "Unknown task", "--task", "TASK-999"),
            ("update", identifier, "--actor", "owner", "--reason", "Unknown revision", "--requirement", "DEMO_SWE1_REQ_001@R2"),
            ("update", identifier, "--actor", "owner", "--reason", "Unknown change", "--change", "CR-999"),
        ]
        for operation in operations:
            with self.subTest(operation=operation):
                self.unchanged_failure(risks, *operation)
        self.assertEqual(2, self.state(risks)["next_id"])
        self.cli(risks, "update", identifier, "--actor", "owner", "--reason", "Add plan", "--mitigation", "Mitigate response latency")
        self.transition(risks, identifier, "MITIGATING")
        self.unchanged_failure(risks, "transition", identifier, "--actor", "owner", "--to", "MITIGATED", "--reason", "Missing proof",
                               "--residual-probability", "1", "--residual-impact", "2")
        self.assertEqual("MITIGATING", self.state(risks)["records"][0]["status"])

    def test_high_residual_threshold_is_inclusive_and_needs_acceptance(self):
        identifier = self.risk("--mitigation", "Measure remaining exposure")
        self.transition(risks, identifier, "MITIGATING")
        self.transition(risks, identifier, "MITIGATED", "--residual-probability", "3", "--residual-impact", "5", "--evidence", "proof.txt")
        self.assertTrue(risks.audit(self.project, release=True)[0])
        self.transition(risks, identifier, "ACCEPTED", "--review-date", self.future)
        self.assertFalse(risks.audit(self.project, release=True)[0])
        self.unchanged_failure(risks, "transition", identifier, "--actor", "owner", "--to", "CLOSED", "--reason", "No proof")

    def test_problem_verified_closure_blocks_release_until_closed_and_can_reopen(self):
        identifier = self.problem("--task", "TASK-001", "--requirement", "DEMO_SWE1_REQ_001@R1", "--change", "CR-001")
        self.assertEqual("PRB-0001", identifier)
        self.assertTrue(problems.audit(self.project, release=True)[0])
        self.transition(problems, identifier, "TRIAGED")
        self.transition(problems, identifier, "IN_PROGRESS")
        self.transition(problems, identifier, "RESOLVED", "--disposition", "FIXED", "--evidence", "proof.txt")
        self.unchanged_failure(problems, "transition", identifier, "--actor", "owner", "--to", "CLOSED", "--reason", "Skip verification")
        self.transition(problems, identifier, "VERIFIED", "--evidence", "proof.txt")
        self.assertTrue(problems.audit(self.project, release=True)[0])
        self.transition(problems, identifier, "CLOSED")
        self.assertFalse(problems.audit(self.project, release=True)[0])
        closed = self.state(problems)["records"][0]
        self.transition(problems, identifier, "IN_PROGRESS")
        reopened = self.state(problems)
        self.assertIsNone(reopened["records"][0]["resolution"])
        self.assertEqual(closed, reopened["history"][-2]["after"])
        self.assertTrue(problems.audit(self.project, release=True)[0])

    def test_duplicate_and_rejected_dispositions_require_verified_evidence(self):
        first, second = self.problem(), self.problem("--release-blocking", "false")
        self.transition(problems, first, "TRIAGED")
        self.transition(problems, second, "TRIAGED")
        self.unchanged_failure(problems, "transition", first, "--actor", "owner", "--to", "RESOLVED", "--reason", "Duplicate",
                               "--disposition", "DUPLICATE", "--duplicate-of", first, "--evidence", "proof.txt")
        self.transition(problems, first, "RESOLVED", "--disposition", "DUPLICATE", "--duplicate-of", second, "--evidence", "proof.txt")
        self.unchanged_failure(problems, "transition", second, "--actor", "owner", "--to", "RESOLVED", "--reason", "Cycle",
                               "--disposition", "DUPLICATE", "--duplicate-of", first, "--evidence", "proof.txt")
        self.transition(problems, first, "VERIFIED", "--evidence", "proof.txt")
        self.transition(problems, first, "CLOSED")
        self.unchanged_failure(problems, "transition", second, "--actor", "owner", "--to", "RESOLVED", "--reason", "Rejected",
                               "--disposition", "REJECTED")
        self.transition(problems, second, "RESOLVED", "--disposition", "REJECTED", "--evidence", "proof.txt")
        self.transition(problems, second, "VERIFIED", "--evidence", "proof.txt")
        self.transition(problems, second, "CLOSED")
        self.assertFalse(problems.audit(self.project, release=True)[0])

    def test_problem_rejected_updates_and_reclassification_keep_history(self):
        identifier = self.problem()
        self.unchanged_failure(problems, "transition", identifier, "--actor", "owner", "--to", "VERIFIED", "--reason", "Invalid")
        self.unchanged_failure(problems, "update", identifier, "--actor", "owner", "--reason", "Invalid link", "--change", "CR-999")
        self.cli(problems, "update", identifier, "--actor", "triage-owner", "--reason", "Accepted non-release impact",
                 "--release-blocking", "false", "--owner", "quality", "--severity", "LOW")
        state = self.state(problems)
        self.assertFalse(state["records"][0]["release_blocking"])
        self.assertTrue(state["history"][0]["after"]["release_blocking"])
        self.assertFalse(problems.audit(self.project, release=True)[0])

    def test_closed_blocking_duplicate_waits_for_canonical_problem_and_reopening(self):
        duplicate, canonical = self.problem(), self.problem("--release-blocking", "false")
        self.transition(problems, duplicate, "TRIAGED")
        self.transition(problems, duplicate, "RESOLVED", "--disposition", "DUPLICATE",
                        "--duplicate-of", canonical, "--evidence", "proof.txt")
        self.transition(problems, duplicate, "VERIFIED", "--evidence", "proof.txt")
        self.transition(problems, duplicate, "CLOSED")
        errors, _ = problems.audit(self.project, release=True)
        self.assertTrue(any(canonical in error and "NEW" in error for error in errors), errors)
        self.transition(problems, canonical, "TRIAGED")
        self.transition(problems, canonical, "IN_PROGRESS")
        self.transition(problems, canonical, "RESOLVED", "--disposition", "FIXED", "--evidence", "proof.txt")
        self.transition(problems, canonical, "VERIFIED", "--evidence", "proof.txt")
        self.transition(problems, canonical, "CLOSED")
        self.assertEqual(([], []), problems.audit(self.project, release=True))
        self.transition(problems, canonical, "IN_PROGRESS")
        self.assertTrue(problems.audit(self.project, release=True)[0])

    def test_duplicate_chain_preserves_original_release_obligation(self):
        original = self.problem()
        middle, canonical = self.problem("--release-blocking", "false"), self.problem("--release-blocking", "false")
        for identifier, replacement in ((original, middle), (middle, canonical)):
            self.transition(problems, identifier, "TRIAGED")
            self.transition(problems, identifier, "RESOLVED", "--disposition", "DUPLICATE",
                            "--duplicate-of", replacement, "--evidence", "proof.txt")
            self.transition(problems, identifier, "VERIFIED", "--evidence", "proof.txt")
            self.transition(problems, identifier, "CLOSED")
        errors, _ = problems.audit(self.project, release=True)
        self.assertTrue(any(original in error and canonical in error for error in errors), errors)
        # An explicit, recorded reclassification remains available.
        self.transition(problems, original, "IN_PROGRESS")
        self.cli(problems, "update", original, "--actor", "Triage owner", "--reason", "Reviewed non-release impact",
                 "--release-blocking", "false")
        self.assertEqual(([], []), problems.audit(self.project, release=True))

    def test_evidence_tampering_rejects_audit_and_further_mutation(self):
        identifier = self.risk("--mitigation", "Run response experiments")
        self.transition(risks, identifier, "MITIGATING")
        self.transition(risks, identifier, "MITIGATED", "--residual-probability", "1", "--residual-impact", "1", "--evidence", "proof.txt")
        problem = self.problem()
        self.transition(problems, problem, "TRIAGED")
        self.transition(problems, problem, "RESOLVED", "--disposition", "REJECTED", "--evidence", "proof.txt")
        self.write("proof.txt", "Changed artifact after registration\n")
        for engine, identifier, target in ((risks, identifier, "OPEN"), (problems, problem, "IN_PROGRESS")):
            self.assertTrue(engine.audit(self.project, release=True)[0])
            self.unchanged_failure(engine, "transition", identifier, "--actor", "owner", "--to", target, "--reason", "Cannot hide corruption")

    def test_closed_records_require_reopening_and_keep_artifact_checks(self):
        risk = self.risk()
        self.transition(risks, risk, "ACCEPTED", "--review-date", self.future)
        self.transition(risks, risk, "CLOSED", "--evidence", "proof.txt")
        problem = self.problem()
        self.transition(problems, problem, "TRIAGED")
        self.transition(problems, problem, "RESOLVED", "--disposition", "REJECTED", "--evidence", "proof.txt")
        self.transition(problems, problem, "VERIFIED", "--evidence", "proof.txt")
        self.transition(problems, problem, "CLOSED")
        for engine, identifier in ((risks, risk), (problems, problem)):
            self.unchanged_failure(engine, "update", identifier, "--actor", "owner", "--reason", "Cannot modify assessed record", "--owner", "replacement")
            self.assertFalse(engine.audit(self.project, release=True)[0])
        self.write("proof.txt", "Changed after closure\n")
        self.assertTrue(risks.audit(self.project, release=True)[0])
        self.assertTrue(problems.audit(self.project, release=True)[0])

    def test_domain_validation_rejects_consistently_hashed_but_malformed_records(self):
        risk = self.risk()
        problem = self.problem()
        for engine, identifier, field, value in ((risks, risk, "probability", True),
                                                  (problems, problem, "release_blocking", "false")):
            def malformed(data):
                data["records"][0][field] = value
                return identifier
            engine.store(self.project).update("fixture", "simulate malformed domain input", malformed)
            self.assertFalse(engine.store(self.project).errors(self.state(engine)))
            self.assertTrue(engine.audit(self.project)[0])
            self.unchanged_failure(engine, "update", identifier, "--actor", "owner", "--reason", "Invalid source state", "--owner", "replacement")

    def test_common_history_tampering_malformed_json_and_idempotent_init(self):
        self.risk()
        self.problem()
        for engine in (risks, problems):
            path = self.project / engine.REGISTRY
            before = path.read_bytes()
            self.cli(engine, "init", "--actor", "coordinator")
            self.assertEqual(before, path.read_bytes())
            state = self.state(engine)
            state["records"][0]["owner"] = "unrecorded-owner"
            path.write_text(json.dumps(state), encoding="utf-8")
            self.assertTrue(engine.audit(self.project)[0])
            self.unchanged_failure(engine, "update", state["records"][0]["id"], "--actor", "owner", "--reason", "Hidden edit", "--owner", "replacement")
            path.write_text('{"records":', encoding="utf-8")
            self.assertTrue(engine.audit(self.project)[0])

    def test_missing_evidence_and_outside_paths_reject_without_write(self):
        identifier = self.problem()
        self.transition(problems, identifier, "TRIAGED")
        for path in ("missing.txt", "../outside.txt", ".git/config"):
            self.unchanged_failure(problems, "transition", identifier, "--actor", "owner", "--to", "RESOLVED", "--reason", "Review",
                                   "--disposition", "REJECTED", "--evidence", path)

    def test_read_only_audits_and_absent_registry_legacy_compatibility(self):
        with tempfile.TemporaryDirectory() as empty:
            for engine in (risks, problems):
                self.assertEqual(([], []), engine.audit(empty, release=True))
                self.assertEqual([], list(Path(empty).iterdir()))
        self.risk()
        self.problem()
        before = {str(path.relative_to(self.project)): path.read_bytes() for path in self.project.rglob("*") if path.is_file()}
        risks.audit(self.project, release=True)
        problems.audit(self.project, release=True)
        after = {str(path.relative_to(self.project)): path.read_bytes() for path in self.project.rglob("*") if path.is_file()}
        self.assertEqual(before, after)

    def test_real_cli_error_exit_and_derived_view_rebuild(self):
        self.risk()
        (self.project / risks.VIEW).unlink()
        self.cli(risks, "render")
        self.assertIn("RISK-0001", (self.project / risks.VIEW).read_text(encoding="utf-8"))
        result = subprocess.run([sys.executable, str(Path(problems.__file__)), "--project", str(self.project), "create",
                                 "--actor", "owner", "--title", "Invalid", "--owner", "quality", "--severity", "HIGH",
                                 "--description", "", "--release-blocking", "true"], text=True, capture_output=True)
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(1, self.state(problems)["next_id"])

    def test_view_failure_reports_committed_json_and_can_be_rebuilt(self):
        with patch.object(risks, "write_view", side_effect=OSError("view unavailable")):
            output = self.risk()
        self.assertIn("registry update committed", output)
        self.assertEqual(1, len(self.state(risks)["records"]))
        self.cli(risks, "render")
        self.assertIn("RISK-0001", (self.project / risks.VIEW).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
