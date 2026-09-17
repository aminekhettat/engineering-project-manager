#!/usr/bin/env python3
"""Behavior tests for read-only status and bounded delegation contracts."""

from test_support import SCRIPTS

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from delegation_plan import build_plan
from project_report import build_report


class ProjectOperationsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.task = {"id": "T-1", "title": "Implement feature", "status": "READY",
                     "priority": "P1", "depends_on": [], "requirements": [],
                     "acceptance_criteria": ["Behavior verified"], "outputs": ["src/feature.py"],
                     "evidence": [], "owner": "Coordinator"}
        self.state = {"schema_version": 1, "tasks": [self.task], "history": []}
        self.setup = {"schema_version": 1, "delegation": {
            "enabled": True, "agents": [{"label": "builder", "role": "SWE", "worker": "worker-a"}],
            "max_parallel": 3, "max_attempts": 2, "writable_paths": ["src", "tests"],
            "approval_policy": "review-before-integration"}}
        self.save()
        self.git("init", "-q")
        self.git("config", "user.name", "Test maintainer")
        self.git("config", "user.email", "test@example.invalid")
        self.git("add", ".")
        self.git("commit", "-qm", "Synthetic project")

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True, text=True)

    def save(self):
        for name, value in [("00-project/management/TASKS.json", self.state),
                            ("00-project/PROJECT-SETUP.json", self.setup)]:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(value), encoding="utf-8")

    def snapshot(self):
        return {str(p.relative_to(self.root)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in self.root.rglob("*") if p.is_file() and ".git" not in p.parts}

    def test_report_and_contract_do_not_mutate_records(self):
        before = self.snapshot()
        report = build_report(self.root)
        self.assertEqual({"READY": 1}, report["tasks"]["counts"])
        self.assertEqual("NOT_EVALUATED", report["release_readiness"])
        self.assertEqual([], report["findings"])
        self.assertFalse(report["git"]["dirty"])
        plan = build_plan(self.root, "T-1", "builder", ["src/feature.py"])
        self.assertFalse(plan["dispatched"])
        self.assertEqual("worker-a", plan["agent"]["worker"])
        self.assertEqual(40, len(plan["base_commit"]))
        self.assertEqual(before, self.snapshot())

    def test_report_rejects_corrupted_tasks_without_inventing_status(self):
        self.state["tasks"][0]["status"] = "FAKE"
        self.save()
        report = build_report(self.root)
        self.assertIsNone(report["tasks"])
        self.assertTrue(any("Invalid task state" in item for item in report["findings"]))
        self.assertIsNotNone(report["requirements"])

    def test_report_contains_malformed_registry_failures(self):
        path = self.root / "08-configuration/CHANGE-REQUESTS.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"model_version": "1.1", "changes": [None]}), encoding="utf-8")
        before = self.snapshot()
        report = build_report(self.root)
        self.assertIsNone(report["changes"])
        self.assertTrue(report["findings"])
        self.assertEqual({"READY": 1}, report["tasks"]["counts"])
        self.assertEqual(before, self.snapshot())

    def test_assignment_rejects_unknown_or_disabled_worker(self):
        with self.assertRaisesRegex(ValueError, "configured agent"):
            build_plan(self.root, "T-1", "unknown", ["src"])
        self.setup["delegation"]["enabled"] = False
        self.save()
        with self.assertRaisesRegex(ValueError, "disabled"):
            build_plan(self.root, "T-1", "builder", ["src"])

    def test_assignment_rejects_scope_escape_and_policy_expansion(self):
        for scope in ["../outside", "/etc", ".", "./", ".//", ".git/config", "src/.git/config", "unapproved"]:
            with self.subTest(scope=scope), self.assertRaises(ValueError):
                build_plan(self.root, "T-1", "builder", [scope])

    def test_assignment_detects_live_work_conflict(self):
        other = copy.deepcopy(self.task)
        other.update(id="T-2", status="IN_PROGRESS", outputs=["src/feature.py"])
        self.state["tasks"].append(other)
        self.save()
        with self.assertRaisesRegex(ValueError, "conflicts"):
            build_plan(self.root, "T-1", "builder", ["src"])
        self.setup["delegation"]["max_parallel"] = 1
        self.save()
        with self.assertRaisesRegex(ValueError, "limit"):
            build_plan(self.root, "T-1", "builder", ["tests"])

    def test_assignment_requires_done_dependencies_and_acceptance(self):
        other = copy.deepcopy(self.task)
        other.update(id="T-2", status="BACKLOG")
        self.task["depends_on"] = ["T-2"]
        self.state["tasks"].append(other)
        self.save()
        with self.assertRaises(ValueError):
            build_plan(self.root, "T-1", "builder", ["src"])
        self.task["depends_on"] = []
        self.task["acceptance_criteria"] = []
        self.save()
        with self.assertRaisesRegex(ValueError, "acceptance"):
            build_plan(self.root, "T-1", "builder", ["src"])

    def test_assignment_requires_expected_outputs_inside_writable_paths(self):
        with self.assertRaisesRegex(ValueError, "outside assignment writable paths"):
            build_plan(self.root, "T-1", "builder", ["tests"])
        self.task["outputs"] = ["../outside.py"]
        self.save()
        with self.assertRaisesRegex(ValueError, "Expected outputs must name bounded"):
            build_plan(self.root, "T-1", "builder", ["src"])

    def test_assignment_hash_changes_when_canonical_task_state_changes(self):
        first = build_plan(self.root, "T-1", "builder", ["src"])
        self.task["acceptance_criteria"].append("New acceptance criterion")
        self.save()
        second = build_plan(self.root, "T-1", "builder", ["src"])
        self.assertNotEqual(first["task_state_sha256"], second["task_state_sha256"])

    def test_assignment_rejects_a_link_outside_the_project(self):
        with tempfile.TemporaryDirectory() as outside:
            try:
                (self.root / "src").symlink_to(outside, target_is_directory=True)
            except OSError:
                self.skipTest("Symlink creation unavailable")
            with self.assertRaisesRegex(ValueError, "outside"):
                build_plan(self.root, "T-1", "builder", ["src/escape.py"])

    def test_assignment_detects_scope_alias_conflicts(self):
        (self.root / "implementation").mkdir()
        try:
            (self.root / "src").symlink_to(self.root / "implementation", target_is_directory=True)
        except OSError:
            self.skipTest("Symlink creation unavailable")
        other = copy.deepcopy(self.task)
        other.update(id="T-2", status="IN_PROGRESS", outputs=["implementation/feature.py"])
        self.state["tasks"].append(other)
        self.save()
        with self.assertRaisesRegex(ValueError, "conflicts"):
            build_plan(self.root, "T-1", "builder", ["src"])

    def test_assignment_rejects_a_link_into_git_metadata(self):
        try:
            (self.root / "src").symlink_to(self.root / ".git", target_is_directory=True)
        except OSError:
            self.skipTest("Symlink creation unavailable")
        with self.assertRaises(ValueError):
            build_plan(self.root, "T-1", "builder", ["src"])


if __name__ == "__main__":
    unittest.main()
