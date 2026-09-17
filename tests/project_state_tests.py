#!/usr/bin/env python3
"""Behavioral and concurrency tests for the Project Manager task engine."""

from test_support import SCRIPTS

import json
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ENGINE = SCRIPTS / "project_state.py"


class ProjectStateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.project = Path(self.temporary.name)
        self.cli("init", str(self.project), "--title", "Task Fixture", "--slug", "task-fixture")

    def tearDown(self):
        self.temporary.cleanup()

    def cli(self, *arguments, expected=0):
        result = subprocess.run(
            [sys.executable, str(ENGINE), *arguments],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        self.assertEqual(expected, result.returncode, result.stdout)
        return result.stdout

    def state(self):
        return json.loads(
            (self.project / "00-project/management/TASKS.json").read_text(
                encoding="utf-8"
            )
        )

    def add(self, identifier, *extra, expected=0):
        return self.cli(
            "add", str(self.project), "--id", identifier,
            "--title", f"Task {identifier}", "--owner", "engineer",
            "--priority", "P1", "--acceptance", "Evidence reviewed",
            *extra,
            expected=expected,
        )

    def test_dependency_lifecycle_review_and_evidence(self):
        self.add("TASK-001")
        self.add("TASK-002", "--depends", "TASK-001")
        self.cli("refresh", str(self.project))
        states = {item["id"]: item["status"] for item in self.state()["tasks"]}
        self.assertEqual("READY", states["TASK-001"])
        self.assertEqual("BACKLOG", states["TASK-002"])

        self.cli("start", str(self.project), "TASK-001")
        self.cli("submit", str(self.project), "TASK-001")
        self.cli("accept", str(self.project), "TASK-001", expected=1)
        self.cli("rework", str(self.project), "TASK-001", "--reason", "Evidence missing")
        self.cli("refresh", str(self.project))
        self.cli("start", str(self.project), "TASK-001")
        self.cli(
            "submit", str(self.project), "TASK-001",
            "--evidence", "tests/report.txt",
        )
        self.cli(
            "accept", str(self.project), "TASK-001",
            "--reviewer", "main", "--note", "Acceptance criteria verified",
        )
        self.cli("refresh", str(self.project))
        tasks = {item["id"]: item for item in self.state()["tasks"]}
        self.assertEqual("DONE", tasks["TASK-001"]["status"])
        self.assertEqual("READY", tasks["TASK-002"]["status"])
        self.assertEqual("main", tasks["TASK-001"]["accepted_by"])
        self.assertTrue(tasks["TASK-001"]["evidence"])

    def test_invalid_dependency_and_duplicate_id_do_not_corrupt_state(self):
        self.add("TASK-001")
        self.add("TASK-001", expected=1)
        self.add("TASK-002", "--depends", "UNKNOWN", expected=1)
        state = self.state()
        self.assertEqual(["TASK-001"], [item["id"] for item in state["tasks"]])
        self.cli("summary", str(self.project))

    def test_legacy_optional_fields_are_normalized_on_next_write(self):
        path = self.project / "00-project/management/TASKS.json"
        state = self.state()
        state["tasks"].append({
            "id": "LEGACY-001",
            "title": "Legacy task",
            "owner": "main",
            "priority": "P2",
            "status": "BACKLOG",
        })
        path.write_text(json.dumps(state), encoding="utf-8")
        self.cli("refresh", str(self.project))
        legacy = next(item for item in self.state()["tasks"] if item["id"] == "LEGACY-001")
        self.assertEqual([], legacy["depends_on"])
        self.assertEqual([], legacy["evidence"])
        self.assertIsNone(legacy["blocker"])

    def test_start_requires_acceptance_criteria_and_enforces_wip_limit(self):
        self.cli(
            "add", str(self.project), "--id", "NO-ACCEPTANCE",
            "--title", "Missing acceptance", "--owner", "main",
        )
        for index in range(1, 5):
            self.add(f"TASK-{index:03d}")
        self.cli("refresh", str(self.project))
        self.cli("start", str(self.project), "NO-ACCEPTANCE", expected=1)
        for index in range(1, 4):
            self.cli("start", str(self.project), f"TASK-{index:03d}")
        output = self.cli("start", str(self.project), "TASK-004", expected=1)
        self.assertIn("WIP limit reached", output)

    def test_cancel_preserves_history_and_rejects_active_work(self):
        self.add("TASK-001")
        self.cli(
            "cancel", str(self.project), "TASK-001",
            "--reason", "Scope removed",
        )
        task = self.state()["tasks"][0]
        self.assertEqual("CANCELLED", task["status"])
        self.assertEqual("Scope removed", self.state()["history"][-1]["note"])

        self.add("TASK-002")
        self.cli("refresh", str(self.project))
        self.cli("start", str(self.project), "TASK-002")
        self.cli(
            "cancel", str(self.project), "TASK-002",
            "--reason", "Too late", expected=1,
        )

    def test_start_rechecks_dependencies_of_a_stale_ready_task(self):
        self.add("TASK-001")
        self.add("TASK-002", "--depends", "TASK-001")
        state = self.state()
        state["tasks"][1]["status"] = "READY"
        path = self.project / "00-project/management/TASKS.json"
        path.write_text(json.dumps(state), encoding="utf-8")
        before = path.read_bytes()
        output = self.cli("start", str(self.project), "TASK-002", expected=1)
        self.assertIn("Dependencies not satisfied", output)
        self.assertEqual(before, path.read_bytes())

    def test_blank_acceptance_and_malformed_dependency_are_rejected(self):
        output = self.cli(
            "add", str(self.project), "--id", "EMPTY", "--title", "Empty acceptance",
            "--acceptance", "   ", expected=1,
        )
        self.assertIn("acceptance_criteria must contain non-empty strings", output)
        self.assertEqual([], self.state()["tasks"])
        self.add("TASK-001")
        state = self.state()
        state["tasks"][0]["depends_on"] = [{"id": "UNKNOWN"}]
        path = self.project / "00-project/management/TASKS.json"
        path.write_text(json.dumps(state), encoding="utf-8")
        output = self.cli("summary", str(self.project), expected=1)
        self.assertIn("depends_on must contain non-empty strings", output)
        self.assertNotIn("Traceback", output)

    def test_concurrent_adds_are_serialized_without_lost_updates(self):
        def add_one(index):
            return subprocess.run(
                [
                    sys.executable, str(ENGINE), "add", str(self.project),
                    "--id", f"TASK-{index:03d}", "--title", f"Concurrent {index}",
                    "--owner", "worker", "--priority", "P2",
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(add_one, range(1, 17)))
        failures = [result.stdout for result in results if result.returncode != 0]
        self.assertEqual([], failures)
        identifiers = [item["id"] for item in self.state()["tasks"]]
        self.assertEqual(16, len(identifiers))
        self.assertEqual(16, len(set(identifiers)))
        self.assertTrue(
            (self.project / "00-project/management/TASKS.md").is_file()
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
