#!/usr/bin/env python3
"""Prove that a complete minimal project passes the real V1.1 release gate."""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent


def write(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n", encoding="utf-8")


def run(command: list[str], cwd: Path, env=None) -> subprocess.CompletedProcess:
    return subprocess.run(command, cwd=cwd, env=env, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def build_fixture(root: Path) -> None:
    write(root, "00-project/PROJECT.md", "# Project\n\nRelease fixture.")
    write(root, "00-project/PROCESS-SCOPE.md", "# Process Scope\n\nSWE is active.")
    write(root, "00-project/STANDARDS.md", "# Standards\n\nDeterministic project controls apply.")
    write(root, "00-project/DECISIONS.md", "# Decisions\n\nDEC-001: use the release gate.")
    write(root, "00-project/STATUS.md", """
# Project Status

- Current Baseline:

| Gate | Status | Main Issue |
|---|---|---|
| G0 Project Definition | PASS | |
| G1 Requirements Baseline | PASS | |
| G2 Architecture Baseline | PASS | |
| G3 Release Readiness | PASS | |
""")
    write(root, "00-project/BOOTSTRAP.json", json.dumps({
        "title": "Release Fixture", "slug": "release-fixture", "domains": ["SWE"]
    }))
    write(root, "00-project/BOOTSTRAP-STATUS.json", json.dumps({
        "state": "COMPLETE", "complete": True
    }))
    write(root, "00-project/management/TASKS.json", json.dumps({
        "schema_version": 1, "project": "release-fixture", "tasks": [{
            "id": "TASK-001", "title": "Release proof", "status": "DONE",
            "priority": "P1", "depends_on": []
        }]
    }))
    write(root, "00-project/management/TASKS.md", "# Tasks\n\nTASK-001 is DONE.")
    write(root, "01-requirements/software/SWE-REQUIREMENTS.md", """
# Software Requirements

[FIXTURE_SWE1_REQ_001@R1]
Status: RELEASED
Upstream: ROOT
Allocated_To: NONE
Verification_Method: TEST
Verification_Scope: SOFTWARE
Verification_Activity: VERIFICATION
Verification_Process: SWE6
Implementation_Milestone: M1
Verification_Milestone: M2
Owner: SWE
Priority: MUST
Rationale: The release fixture must exercise the current requirement model.
Acceptance_Criteria: Every release audit exits successfully.
Text:
The software shall execute complete release validation deterministically.
[END_REQ]
""")
    write(root, "01-requirements/TRACEABILITY.md", """
# Traceability

| Requirement | Architecture | Design | Test | Evidence |
|---|---|---|---|---|
| FIXTURE_SWE1_REQ_001@R1 | SWE-ARCH-001 | SWE-DES-001 | SWE-TEST-001 | SWE-VER-001 |
""")
    evidence = "FIXTURE_SWE1_REQ_001@R1 is implemented and verified with recorded evidence."
    write(root, "02-architecture/software/SWE-ARCHITECTURE.md",
          "# Software Architecture\n\nSWE-ARCH-001\n\n" + evidence)
    write(root, "03-design/software/SWE-DETAILED-DESIGN.md",
          "# Software Detailed Design\n\nSWE-DES-001\n\n" + evidence)
    write(root, "05-verification/software/SWE-TEST-SPECIFICATION.md",
          "# Software Test Specification\n\nSWE-TEST-001\n\n" + evidence)
    write(root, "05-verification/software/SWE-VERIFICATION-REPORT.md",
          "# Software Verification Report\n\nSWE-VER-001\n\n" + evidence)
    write(root, "07-quality/QA-PLAN.md", "# QA Plan\n\nIndependent review is required.")
    write(root, "08-configuration/CONFIGURATION-PLAN.md",
          "# Configuration Plan\n\nGit identifies the release candidate.")
    write(root, "08-configuration/CONFIGURATION-ITEMS.md",
          "# Configuration Items\n\nThe repository is controlled.")
    write(root, "08-configuration/BASELINES.md", "# Baselines\n\nPending initialization.")
    write(root, "09-risks/RISK-REGISTER.md", "# Risks\n\nNo open release risk.")
    write(
        root,
        ".gitignore",
        "__pycache__/\n*.pyc\n08-configuration/.change-requests.lock\n"
        "08-configuration/.baselines.lock\n05-verification/.evidence.lock\n",
    )


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="pm-release-fixture-") as temporary:
        root = Path(temporary)
        build_fixture(root)
        commands = [
            ["git", "init", "-q"],
            ["git", "config", "user.email", "test@example.invalid"],
            ["git", "config", "user.name", "Project Manager Test"],
            ["git", "remote", "add", "origin", "https://git.example.invalid/release-fixture.git"],
            ["git", "add", "."],
            ["git", "commit", "-qm", "complete release fixture"],
        ]
        for command in commands:
            result = run(command, root)
            if result.returncode:
                print(result.stdout)
                return result.returncode
        setup_commands = [
            [sys.executable, str(SCRIPTS / "change_manager.py"),
             "--project", str(root), "init"],
            [sys.executable, str(SCRIPTS / "baseline_manager.py"),
             "--project", str(root), "init", "--actor", "Configuration Manager"],
            [sys.executable, str(SCRIPTS / "verification_evidence.py"),
             "--project", str(root), "init", "--actor", "Verification Engineer"],
            ["git", "add", "."],
            ["git", "commit", "-qm", "enable configuration and evidence management"],
            [sys.executable, str(SCRIPTS / "verification_evidence.py"),
             "--project", str(root), "create",
             "--requirement-id", "FIXTURE_SWE1_REQ_001@R1",
             "--title", "Release validation execution",
             "--objective", "Prove the release gate end to end",
             "--expected-result", "Every release audit exits successfully",
             "--actor", "Verification Engineer"],
            ["git", "add", "."],
            ["git", "commit", "-qm", "plan release validation evidence"],
            [sys.executable, str(SCRIPTS / "baseline_manager.py"),
             "--project", str(root), "create", "--purpose", "Release candidate",
             "--actor", "Configuration Manager"],
            ["git", "add", "."],
            ["git", "commit", "-qm", "create baseline draft"],
            [sys.executable, str(SCRIPTS / "baseline_manager.py"),
             "--project", str(root), "freeze", "BL-001",
             "--actor", "Configuration Manager"],
            ["git", "add", "."],
            ["git", "commit", "-qm", "freeze release candidate"],
            [sys.executable, str(SCRIPTS / "verification_evidence.py"),
             "--project", str(root), "record-result", "EV-001",
             "--result", "PASS",
             "--actor", "Verification Engineer",
             "--summary", "All release audits executed successfully on the frozen candidate",
             "--baseline", "BL-001",
             "--artifact", "05-verification/software/SWE-VERIFICATION-REPORT.md"],
            ["git", "add", "."],
            ["git", "commit", "-qm", "record release validation evidence"],
        ]
        for command in setup_commands:
            result = run(command, root)
            if result.returncode:
                print(result.stdout)
                print("RELEASE FIXTURE SETUP: FAIL")
                return result.returncode

        head = run(["git", "rev-parse", "HEAD"], root).stdout.strip()
        env = dict(os.environ, CI_COMMIT_SHA=head)
        result = run(
            [sys.executable, str(SCRIPTS / "release_check.py"), str(root),
             "--baseline", "BL-001"],
            root,
            env,
        )
        print(result.stdout, end="")
        if result.returncode:
            print("RELEASE FIXTURE TEST: FAIL")
            return result.returncode
        release = run(
            [sys.executable, str(SCRIPTS / "baseline_manager.py"),
             "--project", str(root), "release", "BL-001",
             "--actor", "Configuration Manager"],
            root,
            env,
        )
        print(release.stdout, end="")
        if release.returncode:
            print("BASELINE RELEASE INTEGRATION: FAIL")
            return release.returncode
        baseline = json.loads(
            (root / "08-configuration/baselines/BL-001.json").read_text(
                encoding="utf-8"
            )
        )
        if baseline.get("Status") != "RELEASED":
            print("BASELINE RELEASE INTEGRATION: FAIL (status is not RELEASED)")
            return 1
        print("RELEASE FIXTURE TEST: PASS")
        return 0


if __name__ == "__main__":
    sys.exit(main())
