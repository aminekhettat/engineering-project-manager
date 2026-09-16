#!/usr/bin/env python3
"""Behavioral checks of milestone gates, evidence, atomic rejection and audit."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import milestone_manager as manager
from management_common import RecordError


class MilestoneTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="pm-milestone-test-")
        self.project = Path(self.temporary.name)
        self.task_data = {"schema_version": 1, "tasks": [
            {"id": "TASK-001", "title": "Verification", "priority": "P1", "status": "DONE", "depends_on": []},
            {"id": "TASK-002", "title": "Documentation", "priority": "P1", "status": "READY", "depends_on": []}], "history": []}
        self.write_tasks()
        self.proof = self.project / "05-verification/proof.md"
        self.proof.parent.mkdir(parents=True)
        self.proof.write_text("Reviewed fictional proof for criteria A and B.\n", encoding="utf-8")
        manager.initialize(self.project, "Project Manager")

    def tearDown(self):
        self.temporary.cleanup()

    def write_tasks(self):
        path = self.project / "00-project/management/TASKS.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.task_data), encoding="utf-8")

    def create(self, **overrides):
        values = dict(actor="Project Manager", title="Verification milestone", owner="Verification Owner",
                      due_date="2099-12-31", acceptance_criteria=["Criterion A", "Criterion B"],
                      tasks=["TASK-001"], release_required=True)
        values.update(overrides)
        data = manager.create(self.project, **values)
        return data["records"][-1]["id"]

    def transition(self, identifier, status, **values):
        return manager.transition(self.project, identifier, status, actor="Project Manager", **values)

    def achieve(self, identifier, **overrides):
        values = dict(reviewer="Independent Reviewer", review_note="Both criteria reviewed against the proof.",
                      criterion_evidence={1: ["05-verification/proof.md"], 2: ["05-verification/proof.md"]})
        values.update(overrides)
        return self.transition(identifier, "ACHIEVED", **values)

    def bytes(self):
        return tuple((self.project / relative).read_bytes() for relative in (manager.REGISTRY, manager.VIEW))

    def reject_unchanged(self, function):
        before = self.bytes()
        with self.assertRaises(RecordError):
            function()
        self.assertEqual(self.bytes(), before)

    def test_full_lifecycle_dependencies_evidence_and_release(self):
        tasks_before = (self.project / "00-project/management/TASKS.json").read_bytes()
        first = self.create()
        second = self.create(title="Release readiness", depends_on=[first])
        self.assertEqual((first, second), ("MS-0001", "MS-0002"))
        self.transition(first, "ACTIVE")
        self.achieve(first)
        self.transition(second, "ACTIVE")
        self.achieve(second)
        errors, warnings = manager.audit(self.project, release=True)
        self.assertEqual((errors, warnings), ([], []))
        records = manager.store(self.project).read()["records"]
        self.assertTrue(all(record["status"] == "ACHIEVED" for record in records))
        self.assertEqual(len(records[0]["completion"]["criteria"]), 2)
        self.assertEqual(len(records[0]["completion"]["criteria"][0]["artifacts"][0]["sha256"]), 64)
        self.assertEqual((self.project / "00-project/management/TASKS.json").read_bytes(), tasks_before)

    def test_incomplete_task_cannot_achieve_and_rejection_is_atomic(self):
        identifier = self.create(tasks=["TASK-002"])
        self.transition(identifier, "ACTIVE")
        self.reject_unchanged(lambda: self.achieve(identifier))
        self.task_data["tasks"][1]["status"] = "DONE"
        self.write_tasks()
        self.achieve(identifier)
        self.assertFalse(manager.audit(self.project, True)[0])

    def test_unachieved_dependency_cannot_be_bypassed(self):
        first = self.create()
        second = self.create(depends_on=[first])
        self.transition(second, "ACTIVE")
        self.reject_unchanged(lambda: self.achieve(second))
        self.transition(first, "CANCELLED", reason="Scope removed", waiver_rationale="Review accepted scope removal", waiver_reviewer="Sponsor")
        self.reject_unchanged(lambda: self.achieve(second))

    def test_dependency_cycle_unknown_task_and_missing_dependency_are_rejected(self):
        first = self.create()
        second = self.create(depends_on=[first])
        self.reject_unchanged(lambda: manager.update(self.project, first, actor="Project Manager", depends_on=[second]))
        self.reject_unchanged(lambda: self.create(tasks=["TASK-999"]))
        self.reject_unchanged(lambda: self.create(depends_on=["MS-9999"]))
        self.reject_unchanged(lambda: manager.update(self.project, first, actor="Project Manager", depends_on=[first]))
        self.assertEqual(manager.store(self.project).read()["next_id"], 3)

    def test_cancellation_still_blocks_until_explicit_reviewed_waiver(self):
        identifier = self.create()
        self.reject_unchanged(lambda: self.transition(identifier, "CANCELLED"))
        self.transition(identifier, "CANCELLED", reason="Scope no longer required")
        self.assertTrue(manager.audit(self.project, True)[0])
        self.reject_unchanged(lambda: self.transition(identifier, "CANCELLED", waiver_rationale="Accepted scope change"))
        self.transition(identifier, "CANCELLED", waiver_rationale="Sponsor accepted the documented scope change", waiver_reviewer="Sponsor")
        errors, warnings = manager.audit(self.project, True)
        self.assertEqual(errors, [])
        self.assertTrue(any("waived" in warning for warning in warnings))
        self.assertEqual(manager.store(self.project).read()["records"][0]["status"], "CANCELLED")
        self.reject_unchanged(lambda: self.transition(identifier, "CANCELLED", waiver_rationale="Overwrite", waiver_reviewer="Sponsor"))

    def test_required_flag_cannot_be_downgraded(self):
        identifier = self.create()
        self.reject_unchanged(lambda: manager.update(self.project, identifier, actor="Project Manager", release_required=False))
        self.assertTrue(manager.audit(self.project, True)[0])

    def test_optional_milestone_does_not_block_release(self):
        identifier = self.create(release_required=False)
        self.assertEqual(manager.audit(self.project, True), ([], []))
        self.transition(identifier, "CANCELLED", reason="Optional activity deferred")
        self.assertEqual(manager.audit(self.project, True), ([], []))

    def test_all_criteria_need_evidence_and_distinct_review(self):
        identifier = self.create()
        self.reject_unchanged(lambda: self.achieve(identifier))
        self.transition(identifier, "ACTIVE")
        for changes in ({"criterion_evidence": {1: ["05-verification/proof.md"]}},
                        {"criterion_evidence": {1: [], 2: ["05-verification/proof.md"]}},
                        {"criterion_evidence": {1: ["../outside.md"], 2: ["05-verification/proof.md"]}},
                        {"criterion_evidence": {1: ["missing.md"], 2: ["05-verification/proof.md"]}},
                        {"reviewer": "Project Manager"}, {"review_note": ""}):
            self.reject_unchanged(lambda changes=changes: self.achieve(identifier, **changes))

    def test_proof_tampering_and_deleted_linked_tasks_fail_audit(self):
        identifier = self.create()
        self.transition(identifier, "ACTIVE")
        self.achieve(identifier)
        original = self.proof.read_bytes()
        self.proof.write_text("Changed after review", encoding="utf-8")
        self.assertTrue(manager.audit(self.project)[0])
        self.proof.write_bytes(original)
        self.task_data["tasks"] = []
        self.write_tasks()
        self.assertTrue(manager.audit(self.project)[0])

    def test_registry_view_and_lock_cannot_serve_as_self_proof(self):
        identifier = self.create()
        self.transition(identifier, "ACTIVE")
        for path in manager.SELF_ARTIFACTS:
            self.reject_unchanged(lambda path=path: self.achieve(identifier, criterion_evidence={1: [path], 2: [path]}))

    def test_terminal_record_is_immutable(self):
        identifier = self.create()
        self.transition(identifier, "ACTIVE")
        self.achieve(identifier)
        self.reject_unchanged(lambda: manager.update(self.project, identifier, actor="Project Manager", title="Changed"))
        self.reject_unchanged(lambda: self.transition(identifier, "ACTIVE"))

    def test_overdue_audit_is_read_only(self):
        self.create(due_date="2000-01-01", release_required=False)
        before = self.bytes()
        errors, warnings = manager.audit(self.project)
        self.assertFalse(errors)
        self.assertTrue(any("overdue" in warning for warning in warnings))
        self.assertEqual(self.bytes(), before)

    def test_legacy_absence_is_skipped_without_initializing(self):
        legacy = self.project / "legacy"
        legacy.mkdir()
        self.assertEqual(manager.audit(legacy, True), ([], []))
        self.assertEqual(list(legacy.iterdir()), [])

    def test_bad_fields_and_blocking_reason_fail_without_mutation(self):
        for values in ({"release_required": "false"}, {"due_date": "2026-02-30"},
                       {"acceptance_criteria": []}, {"acceptance_criteria": ["A", "A"]}, {"owner": ""}):
            self.reject_unchanged(lambda values=values: self.create(**values))
        identifier = self.create()
        self.reject_unchanged(lambda: self.transition(identifier, "BLOCKED"))
        self.transition(identifier, "BLOCKED", reason="Required equipment unavailable")
        self.transition(identifier, "ACTIVE")
        self.assertIsNone(manager.store(self.project).read()["records"][0]["blocker"])

    def test_malformed_json_and_history_tampering_fail_audit(self):
        self.create()
        path = self.project / manager.REGISTRY
        original = path.read_bytes()
        for malformed in (b"{", b'{"schema_version":1,"schema_version":1}', b'{"value":NaN}'):
            path.write_bytes(malformed)
            self.assertTrue(manager.audit(self.project)[0])
        path.write_bytes(original)
        data = json.loads(original)
        data["history"][0]["actor"] = "Altered Actor"
        path.write_text(json.dumps(data), encoding="utf-8")
        self.assertTrue(manager.audit(self.project)[0])
        self.reject_unchanged(lambda: self.create())

    def test_common_valid_history_still_needs_valid_milestone_action(self):
        identifier = self.create()
        def invalid_action(data):
            data["records"][0]["title"] = "Modified through an invalid action"
            return identifier
        manager.store(self.project).update("Project Manager", "unrecognized", invalid_action)
        self.assertTrue(manager.audit(self.project)[0])

    def test_render_rebuilds_view_and_cli_bad_evidence_does_not_mutate(self):
        identifier = self.create()
        path = self.project / manager.VIEW
        before = (self.project / manager.REGISTRY).read_bytes()
        path.unlink()
        command = [sys.executable, "-B", str(Path(manager.__file__)), "--project", str(self.project)]
        rebuilt = subprocess.run(command + ["render"], capture_output=True, text=True)
        self.assertEqual(rebuilt.returncode, 0, rebuilt.stderr)
        self.assertTrue(path.is_file())
        self.assertEqual((self.project / manager.REGISTRY).read_bytes(), before)
        rejected = subprocess.run(command + ["transition", identifier, "ACHIEVED", "--actor", "Project Manager",
                                            "--criterion-evidence", "invalid"], capture_output=True, text=True)
        self.assertEqual(rejected.returncode, 2)
        self.assertEqual((self.project / manager.REGISTRY).read_bytes(), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
