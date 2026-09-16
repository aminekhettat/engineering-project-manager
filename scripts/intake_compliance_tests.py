#!/usr/bin/env python3
"""Behavioral tests for staged source provenance and evidence-linked applicability."""

import copy
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import compliance_manager as compliance
import intake_manager as intake
from management_common import RecordError, digest, get_record

REQ = """[DEMO_SWE1_REQ_001@R{revision}]
Status: RELEASED
Upstream: ROOT
Allocated_To: NONE
Verification_Method: TEST
Verification_Scope: SOFTWARE
Verification_Activity: VERIFICATION
Verification_Process: SWE6
Implementation_Milestone: M1
Owner: Engineer
Priority: MUST
Rationale: Synthetic source intake test.
Acceptance_Criteria: The feature responds as specified.
Text:
The software shall provide the required feature.
[END_REQ]
"""


class IntakeComplianceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.req = self.root / "01-requirements/software/SWE-REQUIREMENTS.md"
        self.req.parent.mkdir(parents=True)
        self.req.write_text(REQ.format(revision=1), encoding="utf-8")
        (self.root / "inputs").mkdir()
        self.git("init", "-q")
        self.git("config", "user.name", "Synthetic Test")
        self.git("config", "user.email", "test@example.invalid")
        self.git("add", "01-requirements/software/SWE-REQUIREMENTS.md")
        self.git("commit", "-qm", "Synthetic requirement")
        self.cli(intake, "init", "--actor", "Source reviewer")
        self.cli(compliance, "init", "--actor", "Requirements engineer")

    def git(self, *args):
        result = subprocess.run(["git", *args], cwd=self.root, text=True, capture_output=True)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        return result.stdout.strip()

    def cli(self, module, *args, expected=0):
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            result = module.main(["--project", str(self.root), *args])
        self.assertEqual(expected, result, output.getvalue())
        return output.getvalue()

    def authoritative(self, module):
        return (self.root / module.REGISTRY).read_bytes()

    def source(self, version="1", keys=("A",), reviewed=True):
        path = self.root / "inputs" / f"customer-v{version}.txt"
        path.write_text("Synthetic source: feature A and option B.\n", encoding="utf-8")
        output = self.cli(intake, "create", "--title", "Customer specification", "--owner", "Reviewer",
                          "--source-key", "CUSTOMER", "--version", version,
                          "--file", path.relative_to(self.root).as_posix(),
                          "--reference", "Supplied customer document", "--license", "Synthetic test content",
                          "--confidentiality", "INTERNAL", "--actor", "Reviewer")
        source_id = output.strip()
        for key in keys:
            self.cli(intake, "obligation", source_id, "--key", key, "--locator", f"section {key}",
                     "--text", f"The software shall satisfy source obligation {key}.", "--actor", "Reviewer")
        if reviewed:
            self.cli(intake, "review", source_id, "--actor", "Reviewer", "--rationale", "Inventory checked against source")
        return source_id

    def row(self, source_id="SRC-0001", key="A"):
        return self.cli(compliance, "create", "--source", source_id, "--obligation", key,
                        "--owner", "Requirements engineer", "--actor", "Reviewer").strip()

    def proof(self, requirement="DEMO_SWE1_REQ_001@R1", result="PASS"):
        import verification_evidence as evidence
        self.cli(evidence, "init", "--actor", "Tester")
        evidence_id = self.cli(evidence, "create", "--requirement-id", requirement,
                               "--title", "Feature test", "--objective", "Verify the feature",
                               "--expected-result", "Feature behaves correctly", "--actor", "Tester").strip()
        self.cli(evidence, "record-result", evidence_id, "--result", result,
                 "--summary", "Synthetic execution result", "--actor", "Tester")
        return evidence_id

    def map(self, row_id, evidence_id=None, requirement="DEMO_SWE1_REQ_001@R1", expected=0):
        args = ["map", row_id, "--requirement", requirement, "--actor", "Reviewer", "--rationale", "Allocated to software feature"]
        if evidence_id:
            args.extend(["--evidence", evidence_id])
        return self.cli(compliance, *args, expected=expected)

    def test_source_review_freezes_inventory_and_preserves_rejected_write(self):
        sid = self.source()
        before = self.authoritative(intake)
        self.cli(intake, "obligation", sid, "--key", "B", "--locator", "section B",
                 "--text", "The software shall add a feature.", "--actor", "Reviewer", expected=2)
        self.assertEqual(before, self.authoritative(intake))
        self.assertEqual(([], []), intake.audit(self.root, release=True))

    def test_draft_correction_and_explicit_zero_obligation_review(self):
        sid = self.source(reviewed=False)
        self.cli(intake, "obligation", sid, "--key", "A", "--locator", "section 2",
                 "--text", "The software shall satisfy the corrected obligation.", "--replace", "--actor", "Reviewer")
        self.assertEqual("section 2", intake.store(self.root).read()["records"][0]["obligations"][0]["locator"])
        self.cli(intake, "review", sid, "--actor", "Reviewer", "--rationale", "Checked correction")
        empty = self.source(version="2", keys=(), reviewed=False)
        before = self.authoritative(intake)
        self.cli(intake, "review", empty, "--actor", "Reviewer", "--rationale", "Checked", expected=2)
        self.assertEqual(before, self.authoritative(intake))
        self.cli(intake, "review", empty, "--actor", "Reviewer", "--rationale", "Checked source purpose",
                 "--no-obligations-rationale", "Informational glossary with no normative obligations")
        self.cli(intake, "supersede", sid, "--by", empty, "--actor", "Reviewer", "--rationale", "New source version")
        self.assertEqual(([], []), intake.audit(self.root, release=True))
        self.assertEqual(([], []), compliance.audit(self.root, release=True))

    def test_duplicate_version_and_unsafe_source_paths_leave_state_unchanged(self):
        self.source()
        before = self.authoritative(intake)
        args = ["create", "--title", "Duplicate", "--owner", "Reviewer", "--source-key", "CUSTOMER",
                "--version", "1", "--reference", "Supplied source", "--license", "Synthetic", "--confidentiality", "PUBLIC",
                "--actor", "Reviewer"]
        for path in ("inputs/customer-v1.txt", "../outside.txt", intake.REGISTRY):
            self.cli(intake, *args, "--file", path, expected=2)
            self.assertEqual(before, self.authoritative(intake))

    def test_source_modification_and_history_tampering_are_detected(self):
        self.source()
        path = self.root / "inputs/customer-v1.txt"
        path.write_text("Changed source contents\n", encoding="utf-8")
        errors, _ = intake.audit(self.root)
        self.assertTrue(any("sealed record" in error for error in errors), errors)
        path.write_text("Synthetic source: feature A and option B.\n", encoding="utf-8")
        data = intake.store(self.root).read()
        data["records"][0]["license"] = "Altered without review"
        (self.root / intake.REGISTRY).write_text(json.dumps(data), encoding="utf-8")
        self.assertTrue(intake.audit(self.root)[0])

    def test_reviewed_history_prevents_resealing_modified_source(self):
        self.source()
        before = self.authoritative(intake)
        def malicious_edit(data):
            record = get_record(data, "SRC-0001")
            record["title"] = "Rewritten reviewed source"
            record["review_sha256"] = digest(intake.review_payload(record))
            return record["id"]
        with self.assertRaisesRegex(RecordError, "historical"):
            intake.store(self.root).update("Reviewer", "edit", malicious_edit, intake.validate_registry)
        self.assertEqual(before, self.authoritative(intake))

    def test_missing_obligation_rows_and_unassessed_rows_block_release(self):
        sid = self.source(keys=("A", "B"))
        row = self.row(sid, "A")
        errors, warnings = compliance.audit(self.root)
        self.assertEqual([], errors)
        self.assertEqual(2, len(warnings))
        self.assertEqual(2, len(compliance.audit(self.root, release=True)[0]))
        self.cli(compliance, "exclude", row, "--actor", "Reviewer", "--rationale", "Feature outside agreed product scope")
        errors, _ = compliance.audit(self.root, release=True)
        self.assertEqual(1, len(errors))
        self.assertIn("/B", errors[0])

    def test_exact_mapping_pass_coverage_and_reasoned_exclusion(self):
        sid = self.source(keys=("A", "B"))
        row = self.row(sid, "A")
        self.map(row)
        self.assertTrue(compliance.audit(self.root, release=True)[0])
        evidence_id = self.proof()
        self.map(row, evidence_id)
        excluded = self.row(sid, "B")
        before = self.authoritative(compliance)
        self.cli(compliance, "exclude", excluded, "--actor", "Reviewer", "--rationale", "   ", expected=2)
        self.assertEqual(before, self.authoritative(compliance))
        self.cli(compliance, "exclude", excluded, "--actor", "Reviewer", "--rationale", "Optional client feature excluded by agreement")
        self.assertEqual(([], []), compliance.audit(self.root, release=True))
        report = compliance.coverage_report(self.root)
        self.assertEqual(["COVERED", "EXCLUDED"], [r["coverage"] for r in report["obligations"]])
        self.assertIn("not conformity", report["notice"])
        self.cli(compliance, "reopen", row, "--actor", "Reviewer", "--rationale", "Reassess applicability")
        self.assertTrue(compliance.audit(self.root, release=True)[0])

    def test_bad_links_and_nonpass_evidence_do_not_produce_coverage(self):
        self.source()
        row = self.row()
        before = self.authoritative(compliance)
        self.map(row, "EV-999", expected=2)
        self.assertEqual(before, self.authoritative(compliance))
        self.map(row, requirement="DEMO_SWE1_REQ_099@R1", expected=2)
        self.assertEqual(before, self.authoritative(compliance))
        evidence_id = self.proof(result="FAIL")
        self.map(row, evidence_id)
        self.assertTrue(compliance.audit(self.root, release=True)[0])

    def test_new_requirement_revision_makes_old_mapping_stale(self):
        self.source()
        row = self.row()
        evidence_id = self.proof()
        self.map(row, evidence_id)
        self.req.write_text(REQ.format(revision=1) + REQ.format(revision=2), encoding="utf-8")
        errors, _ = compliance.audit(self.root)
        self.assertTrue(any("Stale or cancelled" in error for error in errors), errors)
        before = self.authoritative(compliance)
        self.map(row, evidence_id, expected=2)
        self.assertEqual(before, self.authoritative(compliance))
        newer = self.proof(requirement="DEMO_SWE1_REQ_001@R2")
        self.map(row, newer, requirement="DEMO_SWE1_REQ_001@R2")
        self.assertEqual(([], []), compliance.audit(self.root, release=True))

    def test_incompatible_strategy_or_unrelated_proof_cannot_be_mapped(self):
        self.source()
        row = self.row()
        original = self.req.read_text(encoding="utf-8")
        self.req.write_text(original + original.replace("REQ_001@R1", "REQ_002@R1"), encoding="utf-8")
        unrelated = self.proof(requirement="DEMO_SWE1_REQ_002@R1")
        before = self.authoritative(compliance)
        self.map(row, unrelated, expected=2)
        self.assertEqual(before, self.authoritative(compliance))
        correct = self.proof()
        self.req.write_text(self.req.read_text(encoding="utf-8").replace("Verification_Method: TEST", "Verification_Method: ANALYSIS"), encoding="utf-8")
        self.map(row, correct, expected=2)
        self.assertEqual(before, self.authoritative(compliance))

    def test_supersession_preserves_old_source_and_requires_new_assessment(self):
        old = self.source()
        row = self.row(old)
        self.cli(compliance, "exclude", row, "--actor", "Reviewer", "--rationale", "Not applicable to this product")
        newer = self.source(version="2")
        self.assertTrue(intake.audit(self.root, release=True)[0])
        before = self.authoritative(intake)
        self.cli(intake, "supersede", old, "--by", old, "--actor", "Reviewer", "--rationale", "Invalid self link", expected=2)
        self.assertEqual(before, self.authoritative(intake))
        self.cli(intake, "supersede", old, "--by", newer, "--actor", "Reviewer", "--rationale", "Source revision accepted")
        self.assertEqual(([], []), intake.audit(self.root, release=True))
        report = compliance.coverage_report(self.root)
        self.assertEqual([newer], [r["source_id"] for r in report["obligations"]])
        self.assertTrue(compliance.audit(self.root, release=True)[0])
        before = self.authoritative(compliance)
        self.cli(compliance, "reopen", row, "--actor", "Reviewer", "--rationale", "Historical edit", expected=2)
        self.assertEqual(before, self.authoritative(compliance))
        (self.root / "inputs/customer-v1.txt").write_text("Modified old source", encoding="utf-8")
        self.assertTrue(intake.audit(self.root)[0])

    def test_duplicate_rows_and_rewritten_locator_rejected_without_mutation(self):
        sid = self.source()
        self.row(sid)
        before = self.authoritative(compliance)
        self.cli(compliance, "create", "--source", sid, "--obligation", "A", "--owner", "Reviewer", "--actor", "Reviewer", expected=2)
        self.assertEqual(before, self.authoritative(compliance))
        def change_locator(data):
            row = get_record(data, "CMP-0001")
            row["locator"] = "Altered section"
            return row["id"]
        with self.assertRaises(RecordError):
            compliance.store(self.root).update("Reviewer", "edit", change_locator, compliance.validate_registry)
        self.assertEqual(before, self.authoritative(compliance))

    def test_malformed_json_is_reported_without_rewriting_and_legacy_is_skipped(self):
        for module in (intake, compliance):
            path = self.root / module.REGISTRY
            original = path.read_bytes()
            path.write_text('{"records": ', encoding="utf-8")
            before = path.read_bytes()
            self.cli(module, "audit", expected=1)
            self.cli(module, "init", "--actor", "Reviewer", expected=2)
            self.assertEqual(before, path.read_bytes())
            path.write_bytes(original)
        with tempfile.TemporaryDirectory() as legacy:
            self.assertEqual(([], []), intake.audit(legacy, release=True))
            self.assertEqual(([], []), compliance.audit(legacy, release=True))


if __name__ == "__main__":
    unittest.main(verbosity=2)
