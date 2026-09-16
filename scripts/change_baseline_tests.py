#!/usr/bin/env python3
"""Deterministic integration tests for Change and Baseline Management V1.1."""

import json
import importlib.util
import os
import shutil
import subprocess
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parent
CHANGE = SCRIPTS / "change_manager.py"
BASELINE = SCRIPTS / "baseline_manager.py"
AUDIT = SCRIPTS / "configuration_audit.py"
TRACEABILITY = SCRIPTS / "traceability_check.py"


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def requirement(identifier, upstream="ROOT", status="RELEASED", change_id=""):
    change = f"Change_ID: {change_id}\n" if change_id else ""
    return f"""[{identifier}]
Status: {status}
Upstream: {upstream}
Allocated_To: NONE
Verification_Method: TEST
Verification_Scope: SYSTEM
Verification_Activity: VERIFICATION
Verification_Process: SYS5
Implementation_Milestone: M1
Verification_Milestone: M2
Owner: SYS
Priority: MUST
{change}Rationale: Test rationale.
Acceptance_Criteria: Test criterion.
Text:
The system shall provide deterministic behavior.
[END_REQ]
"""


class ChangeBaselineTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.project = Path(self.temporary.name)
        (self.project / "01-requirements").mkdir()
        (self.project / "00-project").mkdir()
        (self.project / "00-project/STATUS.md").write_text("- Current Baseline: NONE\n", encoding="utf-8")
        (self.project / ".gitignore").write_text("__pycache__/\n*.pyc\n", encoding="utf-8")
        (self.project / "01-requirements/REQ.md").write_text(
            requirement("M5_SYS2_REQ_001@R1")
            + "\n" + requirement("M5_SWE1_REQ_001@R1", "M5_SYS2_REQ_001@R1")
            + "\n" + requirement("M5_SWE2_REQ_001@R1", "M5_SWE1_REQ_001@R1"),
            encoding="utf-8",
        )
        self.git("init")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "user.name", "Test Actor")
        self.git("add", ".")
        self.git("commit", "-m", "fixture")
        self.run_cli(CHANGE, "init")
        self.run_cli(BASELINE, "init", "--actor", "Configuration Manager")

    def tearDown(self):
        self.temporary.cleanup()

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.project, check=True, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def run_cli(self, script, *args, expected=0, env=None):
        result = subprocess.run(
            ["python3", str(script), "--project", str(self.project), *args],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            env=env,
        )
        self.assertEqual(expected, result.returncode, result.stdout)
        return result.stdout

    def release_harness(self):
        harness = self.project / "release-harness"
        harness.mkdir(exist_ok=True)
        for name in (
            "baseline_manager.py",
            "release_check.py",
            "pm_common.py",
            "configuration_audit.py",
            "change_manager.py",
        ):
            shutil.copy2(SCRIPTS / name, harness / name)
        for name in (
            "project_audit.py",
            "requirements_lint.py",
            "traceability_check.py",
            "domain_audit.py",
            # Evidence coverage is proven with the real audit in
            # verification_evidence_tests.py; these tests isolate
            # configuration and baseline behavior.
            "verification_evidence_audit.py",
            # The real combined management gate is exercised by
            # management_integration_tests.py.
            "management_audit.py",
        ):
            (harness / name).write_text(
                "#!/usr/bin/env python3\nimport sys\n"
                "print('DUMMY AUDIT: PASS')\nsys.exit(0)\n",
                encoding="utf-8",
            )
        return harness

    def create_change(self, changed="M5_SYS2_REQ_001@R1"):
        output = self.run_cli(
            CHANGE, "create", "--title", "Controlled update", "--requester", "Requester",
            "--priority", "HIGH", "--reason", "Engineering change", "--assignee", "Alice",
            "--role", "Requester", "--actor", "Alice", "--changed-item", changed,
        )
        self.assertIn("CR-001", output)
        return "CR-001"

    def move(self, cid, status, assignee, role):
        self.run_cli(CHANGE, "transition", cid, status, "--assignee", assignee,
                     "--role", role, "--actor", assignee)

    def test_change_workflow_assignment_history_and_invalid_transition(self):
        cid = self.create_change()
        registry = json.loads((self.project / "08-configuration/CHANGE-REQUESTS.json").read_text())
        self.assertEqual("DRAFT", registry["changes"][0]["Status"])
        self.assertTrue((self.project / "08-configuration/changes/CR-001.md").exists())
        self.run_cli(CHANGE, "transition", cid, "IMPLEMENTED", "--assignee", "X", "--role", "Y", "--actor", "X", expected=2)
        self.move(cid, "SUBMITTED", "Bob", "System Architect")
        self.move(cid, "UNDER_ANALYSIS", "Carol", "Software Lead")
        self.run_cli(CHANGE, "set-result", cid, "IMPLEMENT", "--actor", "Carol", "--summary", "Implement")
        self.move(cid, "ANALYZED", "Carol", "Software Lead")
        self.move(cid, "IMPLEMENTING", "Dan", "Software Developer")
        self.move(cid, "IMPLEMENTED", "Dan", "Software Developer")
        self.move(cid, "VERIFIED", "Eve", "System Verification Engineer")
        self.move(cid, "CLOSED", "Frank", "Configuration Manager")
        self.run_cli(CHANGE, "transition", cid, "IMPLEMENTING", "--assignee", "X", "--role", "Y", "--actor", "X", expected=2)
        data = json.loads((self.project / "08-configuration/CHANGE-REQUESTS.json").read_text())["changes"][0]
        self.assertEqual("CLOSED", data["Status"])
        self.assertEqual("Frank", data["Current_Assignee"])
        self.assertGreaterEqual(len({event["assignee"] for event in data["History"]}), 6)
        self.run_cli(CHANGE, "validate")

    def test_analysis_results_and_recursive_impact(self):
        expected = {"IMPLEMENT": "IMPLEMENTING", "REJECT": "REJECTED", "DEFER": "DEFERRED",
                    "MORE_INFORMATION_REQUIRED": "UNDER_ANALYSIS"}
        for index, (result, destination) in enumerate(expected.items(), 1):
            cid = self.create_change() if index == 1 else self.run_cli(
                CHANGE, "create", "--title", f"Change {index}", "--requester", "R",
                "--priority", "MEDIUM", "--reason", "Test", "--assignee", "A",
                "--role", "R", "--actor", "A", "--changed-item", "M5_SYS2_REQ_001@R1",
            ).strip().splitlines()[-1]
            self.move(cid, "SUBMITTED", "A", "R")
            self.move(cid, "UNDER_ANALYSIS", "B", "Analyst")
            self.run_cli(CHANGE, "set-result", cid, result, "--actor", "B", "--summary", result)
            self.move(cid, "ANALYZED", "B", "Analyst")
            if result == "REJECT":
                self.run_cli(CHANGE, "transition", cid, "IMPLEMENTING", "--assignee", "C",
                             "--role", "Disposition Owner", "--actor", "C", expected=2)
            self.move(cid, destination, "C", "Disposition Owner")
        self.run_cli(CHANGE, "impact", "CR-001", "--actor", "B")
        change = json.loads((self.project / "08-configuration/CHANGE-REQUESTS.json").read_text())["changes"][0]
        self.assertEqual(["M5_SWE1_REQ_001@R1"], change["Impacted_Items"]["direct"])
        self.assertEqual(["M5_SWE2_REQ_001@R1"], change["Impacted_Items"]["transitive"])

    def test_changed_items_remain_distinct_from_manual_impacts(self):
        cid = self.create_change("CI-001")
        self.run_cli(
            CHANGE, "impact", cid, "--actor", "Analyst",
            "--manual-impact", "CI-002", "--summary", "Manual review",
        )
        change = json.loads(
            (self.project / "08-configuration/CHANGE-REQUESTS.json").read_text()
        )["changes"][0]
        self.assertEqual(["CI-001"], change["Changed_Items"])
        self.assertEqual(["CI-002"], change["Impacted_Items"]["manual"])
        self.run_cli(
            CHANGE, "impact", cid, "--actor", "Analyst", "--clear-manual-impact"
        )
        change = json.loads(
            (self.project / "08-configuration/CHANGE-REQUESTS.json").read_text()
        )["changes"][0]
        self.assertEqual([], change["Impacted_Items"]["manual"])

    def test_open_change_blocks_a_newer_revision_of_the_same_requirement(self):
        cid = self.create_change()
        self.move(cid, "SUBMITTED", "Analyst", "Analysis")
        manager = load_module(BASELINE, "baseline_revision_gate")
        candidate = {"Requirements_Snapshot": [{"id": "M5_SYS2_REQ_001@R2"}],
                     "Configuration_Items": []}
        self.assertEqual(([cid], []), manager.blocking_changes(self.project, candidate))
        candidate["Requirements_Snapshot"] = [{"id": "M5_SYS2_REQ_002@R1"}]
        self.assertEqual(([], []), manager.blocking_changes(self.project, candidate))

    def test_change_and_baseline_identifiers_are_not_reused(self):
        self.assertEqual("CR-001", self.create_change())
        second = self.run_cli(
            CHANGE, "create", "--title", "Second change", "--requester", "R",
            "--priority", "LOW", "--reason", "Sequence proof", "--assignee", "A",
            "--role", "Requester", "--actor", "A",
        ).strip().splitlines()[-1]
        self.assertEqual("CR-002", second)
        self.run_cli(BASELINE, "create", "--purpose", "First", "--actor", "CM")
        self.run_cli(BASELINE, "cancel", "BL-001", "--actor", "CM")
        second_baseline = self.run_cli(
            BASELINE, "create", "--purpose", "Second", "--actor", "CM"
        ).strip().splitlines()[-1]
        self.assertEqual("BL-002", second_baseline)

    def test_requirement_revision_preserves_source_and_stale_links(self):
        cid = self.create_change()
        self.run_cli(BASELINE, "create", "--purpose", "Pre-change snapshot", "--actor", "CM")
        self.move(cid, "SUBMITTED", "A", "R")
        self.move(cid, "UNDER_ANALYSIS", "B", "Analyst")
        self.run_cli(CHANGE, "set-result", cid, "IMPLEMENT", "--actor", "B", "--summary", "Implement")
        self.move(cid, "ANALYZED", "B", "Analyst")
        original = (self.project / "01-requirements/REQ.md").read_bytes()
        output = self.run_cli(CHANGE, "revise-requirement", cid, "M5_SYS2_REQ_001@R1", "--actor", "B")
        self.assertIn("M5_SYS2_REQ_001@R2", output)
        updated = (self.project / "01-requirements/REQ.md").read_bytes()
        self.assertTrue(updated.startswith(original))
        self.assertIn(b"[M5_SYS2_REQ_001@R2]", updated)
        self.assertIn(b"Status: DRAFT", updated[len(original):])
        self.assertIn(b"Change_ID: CR-001", updated[len(original):])
        traceability = subprocess.run(
            ["python3", str(TRACEABILITY), str(self.project), "--strict"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        self.assertNotEqual(0, traceability.returncode, traceability.stdout)
        self.assertIn(
            "stale Upstream reference: M5_SYS2_REQ_001@R1; "
            "current revision: M5_SYS2_REQ_001@R2",
            traceability.stdout,
        )
        self.run_cli(CHANGE, "impact", cid, "--actor", "B")
        self.run_cli(BASELINE, "validate", "BL-001", expected=1)

    def test_revision_rejects_non_released_source(self):
        cid = self.create_change()
        self.move(cid, "SUBMITTED", "A", "Requester")
        self.move(cid, "UNDER_ANALYSIS", "B", "Analyst")
        self.run_cli(
            CHANGE, "set-result", cid, "IMPLEMENT", "--actor", "B",
            "--summary", "Implement",
        )
        self.move(cid, "ANALYZED", "B", "Analyst")
        requirements = self.project / "01-requirements/REQ.md"
        requirements.write_text(
            requirements.read_text(encoding="utf-8").replace(
                "Status: RELEASED", "Status: DRAFT", 1
            ),
            encoding="utf-8",
        )
        output = self.run_cli(
            CHANGE, "revise-requirement", cid, "M5_SYS2_REQ_001@R1",
            "--actor", "B", expected=2,
        )
        self.assertIn("only be created from a RELEASED requirement", output)

    def test_freeze_rejects_non_released_requirement(self):
        requirements = self.project / "01-requirements/REQ.md"
        requirements.write_text(
            requirements.read_text(encoding="utf-8").replace(
                "Status: RELEASED", "Status: DRAFT", 1
            ),
            encoding="utf-8",
        )
        self.git("add", ".")
        self.git("commit", "-m", "draft requirement")
        self.run_cli(BASELINE, "create", "--purpose", "Invalid candidate", "--actor", "CM")
        self.git("add", ".")
        self.git("commit", "-m", "invalid baseline draft")
        output = self.run_cli(
            BASELINE, "freeze", "BL-001", "--actor", "CM", expected=2
        )
        self.assertIn("non-RELEASED requirements", output)

    def test_baseline_dirty_blocking_freeze_hash_and_supersede(self):
        harness = self.release_harness()
        cid = self.create_change()
        self.move(cid, "SUBMITTED", "A", "R")
        self.move(cid, "UNDER_ANALYSIS", "B", "Analyst")
        self.run_cli(CHANGE, "set-result", cid, "IMPLEMENT", "--actor", "B", "--summary", "Implement")
        self.move(cid, "ANALYZED", "B", "Analyst")
        self.move(cid, "IMPLEMENTING", "C", "Developer")
        self.run_cli(BASELINE, "create", "--purpose", "Release candidate", "--actor", "CM", "--related-cr", cid)
        self.run_cli(BASELINE, "freeze", "BL-001", "--actor", "CM", expected=2)
        self.git("add", ".")
        self.git("commit", "-m", "draft baseline")
        self.run_cli(BASELINE, "freeze", "BL-001", "--actor", "CM", expected=2)
        # Make the affecting CR non-blocking, then commit the authoritative state.
        self.move(cid, "IMPLEMENTED", "C", "Developer")
        self.move(cid, "VERIFIED", "V", "Verifier")
        self.move(cid, "CLOSED", "CM", "Configuration Manager")
        self.run_cli(CHANGE, "impact", cid, "--actor", "CM")
        self.git("add", ".")
        self.git("commit", "-m", "close change")
        self.run_cli(BASELINE, "refresh", "BL-001", "--actor", "CM")
        self.git("add", ".")
        self.git("commit", "-m", "refresh baseline")
        self.run_cli(BASELINE, "freeze", "BL-001", "--actor", "CM")
        self.assertIn(
            "- Current Baseline: BL-001",
            (self.project / "00-project/STATUS.md").read_text(encoding="utf-8"),
        )
        frozen_path = self.project / "08-configuration/baselines/BL-001.json"
        frozen = json.loads(frozen_path.read_text())
        self.assertRegex(frozen["Snapshot_Integrity_SHA256"], r"^[0-9a-f]{64}$")
        self.git("add", ".")
        self.git("commit", "-m", "freeze candidate")
        self.run_cli(
            harness / "baseline_manager.py",
            "release", "BL-001", "--actor", "CM", expected=2,
        )
        status = self.project / "00-project/STATUS.md"
        status.write_text(
            status.read_text(encoding="utf-8")
            + "\n| Gate | Status |\n|---|---|\n| G3 | PASS |\n",
            encoding="utf-8",
        )
        self.git("add", ".")
        self.git("commit", "-m", "authorize release candidate")
        release_environment = dict(os.environ)
        release_environment["CI_COMMIT_SHA"] = self.git("rev-parse", "HEAD").stdout.strip()
        self.run_cli(
            harness / "baseline_manager.py",
            "release", "BL-001", "--actor", "CM", env=release_environment,
        )
        self.run_cli(BASELINE, "supersede", "BL-001", "--by", "BL-001", "--actor", "CM", expected=2)
        self.run_cli(BASELINE, "create", "--purpose", "Replacement", "--actor", "CM")
        self.git("add", ".")
        self.git("commit", "-m", "replacement draft")
        self.run_cli(BASELINE, "freeze", "BL-002", "--actor", "CM")
        self.run_cli(BASELINE, "supersede", "BL-001", "--by", "BL-002", "--actor", "CM")
        self.git("add", ".")
        self.git("commit", "-m", "freeze replacement and supersede baseline")
        audit = subprocess.run(
            ["python3", str(AUDIT), str(self.project), "--strict"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        self.assertEqual(0, audit.returncode, audit.stdout)
        frozen = json.loads(frozen_path.read_text())
        frozen["Requirements_Snapshot"] = []
        frozen_path.write_text(json.dumps(frozen), encoding="utf-8")
        self.run_cli(BASELINE, "validate", "BL-001", expected=1)

    def test_released_historical_baseline_survives_new_requirement_revision(self):
        cid = self.create_change()
        self.move(cid, "SUBMITTED", "A", "Requester")
        self.move(cid, "UNDER_ANALYSIS", "B", "Analyst")
        self.run_cli(
            CHANGE, "set-result", cid, "IMPLEMENT", "--actor", "B",
            "--summary", "Implement",
        )
        self.move(cid, "ANALYZED", "B", "Analyst")
        self.move(cid, "IMPLEMENTING", "C", "Developer")
        self.move(cid, "IMPLEMENTED", "C", "Developer")
        self.move(cid, "VERIFIED", "V", "Verifier")
        self.move(cid, "CLOSED", "CM", "Configuration Manager")
        self.run_cli(BASELINE, "create", "--purpose", "Historical", "--actor", "CM")
        self.git("add", ".")
        self.git("commit", "-m", "historical draft")
        self.run_cli(BASELINE, "freeze", "BL-001", "--actor", "CM")
        self.git("add", ".")
        self.git("commit", "-m", "historical frozen")
        baseline = json.loads(
            (self.project / "08-configuration/baselines/BL-001.json").read_text()
        )
        baseline["Status"] = "RELEASED"
        baseline["History"].append({
            "timestamp": "9999-01-01T00:00:00+00:00",
            "actor": "test",
            "previous_status": "FROZEN",
            "new_status": "RELEASED",
            "comment": "Previously gate-authorized release",
        })
        # Lifecycle metadata is intentionally outside the immutable hash.
        (self.project / "08-configuration/baselines/BL-001.json").write_text(
            json.dumps(baseline), encoding="utf-8"
        )
        revision_change = self.run_cli(
            CHANGE, "create", "--title", "Later revision", "--requester", "R",
            "--priority", "HIGH", "--reason", "Later change", "--assignee", "A",
            "--role", "Requester", "--actor", "A",
            "--changed-item", "M5_SYS2_REQ_001@R1",
        ).strip().splitlines()[-1]
        self.move(revision_change, "SUBMITTED", "A", "Requester")
        self.move(revision_change, "UNDER_ANALYSIS", "B", "Analyst")
        self.run_cli(
            CHANGE, "set-result", revision_change, "IMPLEMENT", "--actor", "B",
            "--summary", "Implement later revision",
        )
        self.move(revision_change, "ANALYZED", "B", "Analyst")
        self.run_cli(
            CHANGE, "revise-requirement", revision_change,
            "M5_SYS2_REQ_001@R1", "--actor", "B",
        )
        self.move(revision_change, "IMPLEMENTING", "C", "Developer")
        self.move(revision_change, "IMPLEMENTED", "C", "Developer")
        self.move(revision_change, "VERIFIED", "V", "Verifier")
        self.move(revision_change, "CLOSED", "CM", "Configuration Manager")
        self.run_cli(BASELINE, "validate", "BL-001")

    def test_legacy_audit_skip_and_enabled_audit(self):
        marker = self.project / "08-configuration/CONFIGURATION-MANAGEMENT.json"
        marker.unlink()
        result = subprocess.run(["python3", str(AUDIT), str(self.project), "--strict"], text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.assertNotEqual(0, result.returncode, result.stdout)
        self.assertIn("marker", result.stdout.lower())
        legacy = self.project / "true-legacy"
        legacy.mkdir()
        result = subprocess.run(["python3", str(AUDIT), str(legacy), "--strict"], text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.assertEqual(0, result.returncode, result.stdout)

    def test_blank_current_baseline_does_not_consume_next_status_field(self):
        audit_module = load_module(AUDIT, "configuration_audit_under_test")
        status = self.project / "00-project/STATUS.md"
        status.write_text(
            "# Status\n\n- Current Baseline:\n- Primary Git Repository: origin\n",
            encoding="utf-8",
        )
        self.assertIsNone(audit_module.current_baseline(self.project))

    def test_legacy_markdown_requirement_heading_is_detected(self):
        common = load_module(SCRIPTS / "pm_common.py", "pm_common_under_test")
        requirement_file = self.project / "01-requirements/LEGACY.md"
        requirement_file.write_text(
            "## SWE-REQ-001 — Deterministic behavior\n\n"
            "The software shall behave deterministically.\n",
            encoding="utf-8",
        )
        definitions = common.requirement_definitions(self.project)
        self.assertIn("SWE-REQ-001", {item["id"] for item in definitions})

    def test_bootstrap_assets_are_idempotent(self):
        spec = importlib.util.spec_from_file_location("bootstrap_under_test", SCRIPTS / "bootstrap_project.py")
        bootstrap = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bootstrap)
        bootstrap.PM = SCRIPTS.parent
        bootstrap.TEMPLATES = SCRIPTS.parent / "templates"
        target = self.project / "bootstrapped"
        bootstrap.create_structure(target, ["SYS"])
        args = Namespace(title="Bootstrap Test", slug="bootstrap-test", archetype="custom",
                         git_backend="gitlab", repo="group/project", visibility="private",
                         drive_url=None)
        backend = {"profile": "test", "host": "git.example.invalid"}
        bootstrap._instantiate_project_before_work_products(target, args, {}, backend, ["SYS"])
        first = (target / "08-configuration/CHANGE-REQUESTS.json").read_bytes()
        bootstrap._instantiate_project_before_work_products(target, args, {}, backend, ["SYS"])
        self.assertEqual(first, (target / "08-configuration/CHANGE-REQUESTS.json").read_bytes())
        for relative in ("CONFIGURATION-MANAGEMENT.json", "CHANGE-REQUESTS.json",
                         "CHANGE-REQUESTS.md", "BASELINE-REGISTRY.json", "BASELINES.md"):
            self.assertTrue((target / "08-configuration" / relative).exists(), relative)
        self.assertTrue((target / "08-configuration/changes").is_dir())
        self.assertTrue((target / "08-configuration/baselines").is_dir())

    def test_configuration_audit_controls_release_gate(self):
        harness = self.release_harness()
        self.run_cli(
            BASELINE, "create", "--purpose", "Audit propagation", "--actor", "CM"
        )
        self.git("add", ".")
        self.git("commit", "-m", "audit candidate draft")
        self.run_cli(BASELINE, "freeze", "BL-001", "--actor", "CM")
        status = self.project / "00-project/STATUS.md"
        status.write_text(
            status.read_text(encoding="utf-8")
            + "\n| Gate | Status |\n|---|---|\n| G3 | PASS |\n",
            encoding="utf-8",
        )
        self.git("add", ".")
        self.git("commit", "-m", "frozen audit candidate")
        release_environment = dict(os.environ)
        release_environment["CI_COMMIT_SHA"] = self.git("rev-parse", "HEAD").stdout.strip()
        passed = subprocess.run(
            ["python3", str(harness / "release_check.py"), str(self.project),
             "--baseline", "BL-001"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            env=release_environment,
        )
        self.assertEqual(0, passed.returncode, passed.stdout)
        registry_path = self.project / "08-configuration/CHANGE-REQUESTS.json"
        registry = json.loads(registry_path.read_text())
        registry["next_number"] = 0
        registry_path.write_text(json.dumps(registry), encoding="utf-8")
        failed = subprocess.run(
            ["python3", str(harness / "release_check.py"), str(self.project),
             "--baseline", "BL-001"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            env=release_environment,
        )
        self.assertNotEqual(0, failed.returncode, failed.stdout)
        self.assertIn("configuration_audit.py: FAIL", failed.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
