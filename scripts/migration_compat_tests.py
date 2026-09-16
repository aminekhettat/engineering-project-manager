#!/usr/bin/env python3
"""Migration compatibility tests: legacy skip behavior and assessment accuracy."""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ASSESS = SCRIPTS / "migration_assess.py"
RELEASE = SCRIPTS / "release_check.py"

PASS_COUNT = 0
FAILURES = []


def ok(label):
    global PASS_COUNT
    PASS_COUNT += 1
    print(f"PASS: {label}")


def fail(label, detail=""):
    message = label if not detail else f"{label}: {detail}"
    FAILURES.append(message)
    print(f"FAIL: {message}")


def run(command, cwd):
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        command, cwd=cwd, env=env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )


def git(project, *args):
    return run(["git", *args], project)


def commit_all(project, message):
    git(project, "add", ".")
    result = git(project, "commit", "-qm", message)
    if result.returncode:
        print(result.stdout)
        raise RuntimeError(f"fixture commit failed: {message}")


def write(project, relative, content):
    path = project / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n", encoding="utf-8")
    return path


def build_legacy_project(root):
    rid = "SWE-REQ-001"
    evidence = f"{rid} is implemented and verified with recorded evidence."

    write(root, "00-project/PROJECT.md", "# Project\n\nLegacy migration fixture.")
    write(root, "00-project/PROCESS-SCOPE.md", "# Process Scope\n\nSWE is active.")
    write(root, "00-project/STANDARDS.md", "# Standards\n\nDeterministic project controls apply.")
    write(
        root, "00-project/STATUS.md",
        "# Project Status\n\n- Current Baseline:\n\n"
        "| Gate | Status | Main Issue |\n|---|---|---|\n"
        "| G0 Project Definition | PASS | |\n"
        "| G1 Requirements Baseline | PASS | |\n"
        "| G2 Architecture Baseline | PASS | |\n"
        "| G3 Release Readiness | PASS | |\n",
    )
    write(root, "00-project/DECISIONS.md", "# Decisions\n\nDEC-001: use the release gate.")
    write(
        root, "00-project/BOOTSTRAP.json",
        json.dumps({"title": "Legacy Fixture", "slug": "legacy-fixture", "domains": ["SWE"]}),
    )
    write(
        root, "00-project/BOOTSTRAP-STATUS.json",
        json.dumps({"state": "COMPLETE", "complete": True}),
    )
    write(
        root, "00-project/management/TASKS.json",
        json.dumps({
            "schema_version": 1,
            "project": "legacy-fixture",
            "tasks": [{
                "id": "TASK-001", "title": "Legacy proof", "status": "DONE",
                "priority": "P1", "depends_on": [],
            }],
        }),
    )
    write(root, "00-project/management/TASKS.md", "# Tasks\n\nTASK-001 is DONE.")
    write(
        root, "01-requirements/software/SWE-REQUIREMENTS.md",
        "# Software Requirements\n\n"
        "## SWE-REQ-001 — Legacy requirement\n\n"
        "Verification Method: TEST\n\n"
        "Le logiciel doit passer l'audit de migration.\n",
    )
    write(
        root, "01-requirements/TRACEABILITY.md",
        "# Traceability\n\n"
        "| Requirement | Architecture | Design | Test | Evidence |\n"
        "|---|---|---|---|---|\n"
        "| SWE-REQ-001 | SWE-ARCH-001 | SWE-DES-001 | SWE-TEST-001 | SWE-VER-001 |\n",
    )
    write(
        root, "02-architecture/software/SWE-ARCHITECTURE.md",
        "# Software Architecture\n\nSWE-ARCH-001\n\n" + evidence,
    )
    write(
        root, "03-design/software/SWE-DETAILED-DESIGN.md",
        "# Software Detailed Design\n\nSWE-DES-001\n\n" + evidence,
    )
    write(
        root, "05-verification/software/SWE-TEST-SPECIFICATION.md",
        "# Software Test Specification\n\nSWE-TEST-001\n\n" + evidence,
    )
    write(
        root, "05-verification/software/SWE-VERIFICATION-REPORT.md",
        "# Software Verification Report\n\nSWE-VER-001\n\n" + evidence,
    )
    write(root, "07-quality/QA-PLAN.md", "# QA Plan\n\nIndependent review is required.")
    write(root, "08-configuration/CONFIGURATION-PLAN.md", "# Configuration Plan\n\nGit identifies the release candidate.")
    write(root, "08-configuration/CONFIGURATION-ITEMS.md", "# Configuration Items\n\nThe repository is controlled.")
    write(root, "08-configuration/BASELINES.md", "# Baselines\n\nPending initialization.")
    write(root, "09-risks/RISK-REGISTER.md", "# Risks\n\nNo open release risk.")
    write(
        root, ".gitignore",
        "__pycache__/\n*.pyc\n08-configuration/.change-requests.lock\n"
        "08-configuration/.baselines.lock\n05-verification/.evidence.lock\n",
    )

    git(root, "init", "-q")
    git(root, "config", "user.email", "test@example.invalid")
    git(root, "config", "user.name", "Project Manager Test")
    git(root, "remote", "add", "origin", "https://git.example.invalid/legacy-fixture.git")
    commit_all(root, "legacy V1.0 fixture")


def build_v11_requirement():
    return """[MIG_SWE1_REQ_001@R1]
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
Rationale: Migration fixture.
Acceptance_Criteria: The migration assessment reports correctly.
Text:
The software shall support migration assessment.
[END_REQ]
"""


def build_v11cm_project(root):
    rid = "MIG_SWE1_REQ_001@R1"
    evidence = f"{rid} is implemented and verified with recorded evidence."

    write(root, "00-project/PROJECT.md", "# Project\n\nV1.1-CM migration fixture.")
    write(root, "00-project/PROCESS-SCOPE.md", "# Process Scope\n\nSWE is active.")
    write(root, "00-project/STANDARDS.md", "# Standards\n\nDeterministic project controls apply.")
    write(
        root, "00-project/STATUS.md",
        "# Project Status\n\n- Current Baseline:\n\n"
        "| Gate | Status | Main Issue |\n|---|---|---|\n"
        "| G3 Release Readiness | PASS | |\n",
    )
    write(root, "00-project/DECISIONS.md", "# Decisions\n\nDEC-001: migrate to V1.1.")
    write(
        root, "00-project/BOOTSTRAP.json",
        json.dumps({"title": "V1.1-CM Fixture", "slug": "v11cm-fixture", "domains": ["SWE"]}),
    )
    write(
        root, "00-project/BOOTSTRAP-STATUS.json",
        json.dumps({"state": "COMPLETE", "complete": True}),
    )
    write(
        root, "00-project/management/TASKS.json",
        json.dumps({
            "schema_version": 1,
            "project": "v11cm-fixture",
            "tasks": [{
                "id": "TASK-001", "title": "V1.1-CM proof", "status": "DONE",
                "priority": "P1", "depends_on": [],
            }],
        }),
    )
    write(root, "00-project/management/TASKS.md", "# Tasks\n\nTASK-001 is DONE.")
    write(
        root, "01-requirements/software/SWE-REQUIREMENTS.md",
        "# Software Requirements\n\n" + build_v11_requirement(),
    )
    write(
        root, "01-requirements/TRACEABILITY.md",
        "# Traceability\n\n"
        "| Requirement | Architecture |\n|---|---|\n"
        "| MIG_SWE1_REQ_001@R1 | SWE-ARCH-001 |\n",
    )
    write(
        root, "02-architecture/software/SWE-ARCHITECTURE.md",
        "# Software Architecture\n\nSWE-ARCH-001\n\n" + evidence,
    )
    write(
        root, "03-design/software/SWE-DETAILED-DESIGN.md",
        "# Software Detailed Design\n\nSWE-DES-001\n\n" + evidence,
    )
    write(
        root, "05-verification/software/SWE-TEST-SPECIFICATION.md",
        "# Software Test Specification\n\nSWE-TEST-001\n\n" + evidence,
    )
    write(
        root, "05-verification/software/SWE-VERIFICATION-REPORT.md",
        "# Software Verification Report\n\nSWE-VER-001\n\n" + evidence,
    )
    write(root, "07-quality/QA-PLAN.md", "# QA Plan\n\nIndependent review is required.")
    write(root, "08-configuration/CONFIGURATION-PLAN.md", "# Configuration Plan\n\nGit identifies the release candidate.")
    write(root, "08-configuration/CONFIGURATION-ITEMS.md", "# Configuration Items\n\nThe repository is controlled.")
    write(root, "08-configuration/BASELINES.md", "# Baselines\n\nPending initialization.")
    write(
        root, "08-configuration/CONFIGURATION-MANAGEMENT.json",
        json.dumps({
            "model": "PROJECT_MANAGER_CONFIGURATION_MANAGEMENT",
            "model_version": "1.1",
            "enabled": True,
            "enabled_at": "2026-01-01T00:00:00Z",
            "enabled_by": "Test",
        }),
    )
    write(root, "09-risks/RISK-REGISTER.md", "# Risks\n\nNo open release risk.")
    write(
        root, ".gitignore",
        "__pycache__/\n*.pyc\n08-configuration/.change-requests.lock\n"
        "08-configuration/.baselines.lock\n05-verification/.evidence.lock\n",
    )

    git(root, "init", "-q")
    git(root, "config", "user.email", "test@example.invalid")
    git(root, "config", "user.name", "Project Manager Test")
    git(root, "remote", "add", "origin", "https://git.example.invalid/v11cm-fixture.git")
    commit_all(root, "V1.1-CM fixture")


def build_v113_project(root):
    rid = "MIG_SWE1_REQ_001@R1"
    evidence = f"{rid} is implemented and verified with recorded evidence."

    write(root, "00-project/PROJECT.md", "# Project\n\nV1.1.3 migration fixture.")
    write(root, "00-project/PROCESS-SCOPE.md", "# Process Scope\n\nSWE is active.")
    write(root, "00-project/STANDARDS.md", "# Standards\n\nDeterministic project controls apply.")
    write(
        root, "00-project/STATUS.md",
        "# Project Status\n\n- Current Baseline:\n\n"
        "| Gate | Status | Main Issue |\n|---|---|---|\n"
        "| G3 Release Readiness | PASS | |\n",
    )
    write(root, "00-project/DECISIONS.md", "# Decisions\n\nDEC-001: enable evidence management.")
    write(
        root, "00-project/BOOTSTRAP.json",
        json.dumps({"title": "V1.1.3 Fixture", "slug": "v113-fixture", "domains": ["SWE"]}),
    )
    write(
        root, "00-project/BOOTSTRAP-STATUS.json",
        json.dumps({"state": "COMPLETE", "complete": True}),
    )
    write(
        root, "00-project/management/TASKS.json",
        json.dumps({
            "schema_version": 1,
            "project": "v113-fixture",
            "tasks": [{
                "id": "TASK-001", "title": "V1.1.3 proof", "status": "DONE",
                "priority": "P1", "depends_on": [],
            }],
        }),
    )
    write(root, "00-project/management/TASKS.md", "# Tasks\n\nTASK-001 is DONE.")
    write(
        root, "01-requirements/software/SWE-REQUIREMENTS.md",
        "# Software Requirements\n\n" + build_v11_requirement(),
    )
    write(
        root, "01-requirements/TRACEABILITY.md",
        "# Traceability\n\n"
        "| Requirement | Architecture |\n|---|---|\n"
        "| MIG_SWE1_REQ_001@R1 | SWE-ARCH-001 |\n",
    )
    write(
        root, "02-architecture/software/SWE-ARCHITECTURE.md",
        "# Software Architecture\n\nSWE-ARCH-001\n\n" + evidence,
    )
    write(
        root, "03-design/software/SWE-DETAILED-DESIGN.md",
        "# Software Detailed Design\n\nSWE-DES-001\n\n" + evidence,
    )
    write(
        root, "05-verification/software/SWE-TEST-SPECIFICATION.md",
        "# Software Test Specification\n\nSWE-TEST-001\n\n" + evidence,
    )
    write(
        root, "05-verification/software/SWE-VERIFICATION-REPORT.md",
        "# Software Verification Report\n\nSWE-VER-001\n\n" + evidence,
    )
    write(root, "07-quality/QA-PLAN.md", "# QA Plan\n\nIndependent review is required.")
    write(root, "08-configuration/CONFIGURATION-PLAN.md", "# Configuration Plan\n\nGit identifies the release candidate.")
    write(root, "08-configuration/CONFIGURATION-ITEMS.md", "# Configuration Items\n\nThe repository is controlled.")
    write(root, "08-configuration/BASELINES.md", "# Baselines\n\nPending initialization.")
    write(
        root, "08-configuration/CONFIGURATION-MANAGEMENT.json",
        json.dumps({
            "model": "PROJECT_MANAGER_CONFIGURATION_MANAGEMENT",
            "model_version": "1.1",
            "enabled": True,
            "enabled_at": "2026-01-01T00:00:00Z",
            "enabled_by": "Test",
        }),
    )
    write(
        root, "05-verification/EVIDENCE-MANAGEMENT.json",
        json.dumps({
            "model": "PROJECT_MANAGER_VERIFICATION_EVIDENCE_MANAGEMENT",
            "model_version": "1.0",
            "enabled": True,
            "enabled_at": "2026-01-01T00:00:00Z",
            "enabled_by": "Test",
        }),
    )
    write(
        root, "05-verification/EVIDENCE.json",
        json.dumps({
            "model": "PROJECT_MANAGER_VERIFICATION_EVIDENCE",
            "model_version": "1.0",
            "registry_revision": 0,
            "next_number": 1,
            "evidence": [],
        }),
    )
    write(root, "09-risks/RISK-REGISTER.md", "# Risks\n\nNo open release risk.")
    write(
        root, ".gitignore",
        "__pycache__/\n*.pyc\n08-configuration/.change-requests.lock\n"
        "08-configuration/.baselines.lock\n05-verification/.evidence.lock\n",
    )

    git(root, "init", "-q")
    git(root, "config", "user.email", "test@example.invalid")
    git(root, "config", "user.name", "Project Manager Test")
    git(root, "remote", "add", "origin", "https://git.example.invalid/v113-fixture.git")
    commit_all(root, "V1.1.3 fixture")


def assess(project):
    return run([sys.executable, str(ASSESS), str(project), "--json"], project)


def test_legacy_project_passes_release_gate(root):
    build_legacy_project(root)

    checks = [
        ("project_audit.py", [sys.executable, str(SCRIPTS / "project_audit.py"), str(root), "--strict"]),
        ("requirements_lint.py", [sys.executable, str(SCRIPTS / "requirements_lint.py"), str(root), "--strict"]),
        ("traceability_check.py", [sys.executable, str(SCRIPTS / "traceability_check.py"), str(root), "--strict"]),
        ("domain_audit.py", [sys.executable, str(SCRIPTS / "domain_audit.py"), str(root), "--strict"]),
        ("configuration_audit.py", [sys.executable, str(SCRIPTS / "configuration_audit.py"), str(root), "--strict"]),
        ("verification_evidence_audit.py", [sys.executable, str(SCRIPTS / "verification_evidence_audit.py"), str(root), "--strict"]),
    ]

    for name, command in checks:
        result = run(command, root)
        check_passes = result.returncode == 0
        if name in {"configuration_audit.py", "verification_evidence_audit.py"}:
            check(
                check_passes,
                f"{name} skips legacy project without markers",
                result.stdout,
            )
        else:
            check(
                check_passes,
                f"{name} passes on complete legacy project",
                result.stdout,
            )

    head = git(root, "rev-parse", "HEAD").stdout.strip()
    env = dict(os.environ, CI_COMMIT_SHA=head)
    gate = subprocess.run(
        [sys.executable, str(RELEASE), str(root)],
        cwd=root,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    check(
        gate.returncode == 0,
        "release_check passes for complete legacy project",
        gate.stdout,
    )
    check(
        "CONFIGURATION AUDIT: PASS" in gate.stdout,
        "configuration audit is PASS (skipped) in legacy release gate",
        gate.stdout,
    )
    check(
        "VERIFICATION EVIDENCE AUDIT: PASS" in gate.stdout,
        "verification evidence audit is PASS (skipped) in legacy release gate",
        gate.stdout,
    )
    check(
        "legacy project skipped" not in gate.stdout,
        "strict release gate silently skips legacy markers",
        gate.stdout,
    )


def test_assess_reports_legacy(root):
    build_legacy_project(root)
    result = assess(root)
    check(result.returncode == 0, "assess exits 0 on legacy project", result.stdout)
    report = json.loads(result.stdout)
    check(report["requirements"]["state"] == "LEGACY", "legacy requirements state detected")
    check(
        any(
            file["legacy_french"] and file["legacy_headings"] > 0
            for file in report["requirements"]["files"]
        ),
        "legacy French wording and headings detected",
    )
    check(report["configuration_management"]["state"] == "MISSING", "legacy CM marker missing")
    check(report["verification_evidence"]["state"] == "MISSING", "legacy evidence marker missing")
    check(report["tasks"]["schema_version"] == 1, "legacy TASKS.json schema version detected")
    check(report["traceability"]["state"] == "LEGACY", "legacy traceability detected")


def test_assess_reports_v11cm(root):
    build_v11cm_project(root)
    result = assess(root)
    check(result.returncode == 0, "assess exits 0 on V1.1-CM project", result.stdout)
    report = json.loads(result.stdout)
    check(report["requirements"]["state"] == "V1.1", "V1.1-CM requirements state detected")
    check(report["configuration_management"]["state"] == "ENABLED", "V1.1-CM marker enabled")
    check(report["verification_evidence"]["state"] == "MISSING", "V1.1-CM evidence marker missing")
    check(report["traceability"]["state"] == "V1.1", "V1.1-CM traceability detected")
    check(
        "baseline_manager.py" in report["configuration_management"]["init_command"],
        "V1.1-CM init command references configuration management",
    )


def test_assess_reports_v113(root):
    build_v113_project(root)
    result = assess(root)
    check(result.returncode == 0, "assess exits 0 on V1.1.3 project", result.stdout)
    report = json.loads(result.stdout)
    check(report["requirements"]["state"] == "V1.1", "V1.1.3 requirements state detected")
    check(report["configuration_management"]["state"] == "ENABLED", "V1.1.3 CM marker enabled")
    check(report["verification_evidence"]["state"] == "ENABLED", "V1.1.3 evidence marker enabled")
    check(report["traceability"]["state"] == "V1.1", "V1.1.3 traceability detected")
    check(not report["attention"], "V1.1.3 fixture has no attention items", str(report["attention"]))


def test_assess_is_non_destructive(root):
    build_legacy_project(root)
    before = git(root, "status", "--porcelain").stdout.strip()
    check(before == "", "git working tree clean before assessment")
    result = run([sys.executable, str(ASSESS), str(root)], root)
    check(result.returncode == 0, "assess runs without error", result.stdout)
    after = git(root, "status", "--porcelain").stdout.strip()
    check(after == "", "git working tree clean after assessment")


def test_assess_rejects_non_directory():
    result = run([sys.executable, str(ASSESS), "/nonexistent/path/for/migration"], "/tmp")
    check(result.returncode == 2, "assess exits 2 for a missing project path")


def check(condition, label, detail=""):
    if condition:
        ok(label)
    else:
        fail(label, detail)


def main():
    suites = (
        ("legacy project passes release gate", test_legacy_project_passes_release_gate),
        ("assess reports legacy findings", test_assess_reports_legacy),
        ("assess reports V1.1-CM findings", test_assess_reports_v11cm),
        ("assess reports V1.1.3 findings", test_assess_reports_v113),
        ("assess is non-destructive", test_assess_is_non_destructive),
        ("assess rejects non-directory", lambda _root: test_assess_rejects_non_directory()),
    )

    for name, suite in suites:
        print(f"=== {name} ===")
        with tempfile.TemporaryDirectory(prefix="pm-migration-compat-") as temporary:
            root = Path(temporary)
            try:
                suite(root)
            except Exception as exc:  # noqa: BLE001 - test harness must report, not crash
                fail(f"{name} raised an unexpected exception", repr(exc))
        print()

    print(f"MIGRATION COMPAT TESTS: {PASS_COUNT} PASS, {len(FAILURES)} FAIL")
    if FAILURES:
        for failure in FAILURES:
            print(f"- {failure}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
