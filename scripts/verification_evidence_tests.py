#!/usr/bin/env python3
"""Behavior, negative and propagation tests for verification evidence management."""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
EVIDENCE = SCRIPTS / "verification_evidence.py"
AUDIT = SCRIPTS / "verification_evidence_audit.py"
RELEASE = SCRIPTS / "release_check.py"

PASS_COUNT = 0
FAILURES = []


def ok(label):
    global PASS_COUNT
    PASS_COUNT += 1
    print(f"PASS: {label}")


def fail(label, detail=""):
    FAILURES.append(label if not detail else f"{label}: {detail}")
    print(f"FAIL: {label} {detail}")


def check(condition, label, detail=""):
    if condition:
        ok(label)
    else:
        fail(label, detail)


def run(command, cwd):
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        command, cwd=cwd, env=env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )


def evidence(project, *args):
    return run([sys.executable, str(EVIDENCE), "--project", str(project), *args], project)


def audit(project, *args):
    return run([sys.executable, str(AUDIT), str(project), *args], project)


def git(project, *args):
    return run(["git", *args], project)


def commit_all(project, message):
    git(project, "add", ".")
    result = git(project, "commit", "-qm", message)
    if result.returncode:
        print(result.stdout)
        raise RuntimeError(f"fixture commit failed: {message}")


def registry(project):
    return json.loads(
        (project / "05-verification/EVIDENCE.json").read_text(encoding="utf-8")
    )


def save_registry(project, data):
    (project / "05-verification/EVIDENCE.json").write_text(
        json.dumps(data, indent=2) + "\n", encoding="utf-8"
    )


REQUIREMENT = """
[{prefix}_SWE1_REQ_{seq:03d}@R{rev}]
Status: {status}
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
Rationale: Evidence behavior fixture.
Acceptance_Criteria: The behavior under test is proven.
Text:
The software shall support verification evidence behavior test {seq} revision {rev}.
[END_REQ]
"""


def build_project(root, extra_requirements=""):
    (root / "01-requirements/software").mkdir(parents=True)
    (root / "08-configuration/baselines").mkdir(parents=True)
    (root / "00-project").mkdir(parents=True)
    (root / ".gitignore").write_text(
        "__pycache__/\n*.pyc\n05-verification/.evidence.lock\n", encoding="utf-8"
    )
    requirement = REQUIREMENT.format(prefix="BEH", seq=1, rev=1, status="RELEASED")
    (root / "01-requirements/software/SWE-REQUIREMENTS.md").write_text(
        "# Software Requirements\n" + requirement + extra_requirements,
        encoding="utf-8",
    )
    git(root, "init", "-q")
    git(root, "config", "user.email", "test@example.invalid")
    git(root, "config", "user.name", "Project Manager Test")
    commit_all(root, "evidence behavior fixture")


def create_pass_evidence(project, requirement_id="BEH_SWE1_REQ_001@R1"):
    created = evidence(
        project, "create", "--requirement-id", requirement_id,
        "--title", "Behavior verification", "--objective", "Prove behavior",
        "--expected-result", "Expected behavior is observed", "--actor", "Tester",
    )
    if created.returncode:
        return created
    evidence_id = created.stdout.strip()
    started = evidence(project, "start", evidence_id, "--actor", "Tester")
    if started.returncode:
        return started
    return evidence(
        project, "record-result", evidence_id, "--result", "PASS",
        "--actor", "Tester", "--summary", "Behavior proven",
    )


def test_positive_lifecycle(root):
    result = evidence(root, "init", "--actor", "Tester")
    check(result.returncode == 0, "init succeeds", result.stdout)
    marker = root / "05-verification/EVIDENCE-MANAGEMENT.json"
    check(marker.is_file() and json.loads(marker.read_text())["enabled"] is True,
          "init writes the enablement marker")
    result = create_pass_evidence(root)
    check(result.returncode == 0, "create/start/record-result lifecycle", result.stdout)
    data = registry(root)
    record = data["evidence"][0]
    check(record["Evidence_ID"] == "EV-001" and record["Status"] == "PASS",
          "record identity and PASS status persisted")
    check(record["Verification_Method"] == "TEST"
          and record["Verification_Scope"] == "SOFTWARE"
          and record["Verification_Process"] == "SWE6",
          "verification strategy inferred from the requirement")
    head = git(root, "rev-parse", "HEAD").stdout.strip()
    check(record["Execution"]["Git_Commit"] == head,
          "execution captures the exact Git commit")
    check(record["History"][0]["event"] == "CREATED"
          and record["History"][-1]["event"] == "RESULT_PASS",
          "history records CREATED then RESULT_PASS")
    check((root / "05-verification/evidence/EV-001.md").is_file(),
          "Markdown evidence view is generated")
    validated = evidence(root, "validate")
    check(validated.returncode == 0 and "EVIDENCE VALIDATION: PASS" in validated.stdout,
          "validate passes on a consistent registry", validated.stdout)
    coverage = evidence(root, "coverage", "--strict")
    check(coverage.returncode == 0 and "Uncovered requirements: 0" in coverage.stdout,
          "strict coverage passes with compatible PASS evidence", coverage.stdout)
    audited = audit(root, "--strict")
    check(audited.returncode == 0 and "VERIFICATION EVIDENCE AUDIT: PASS" in audited.stdout,
          "strict audit passes when covered", audited.stdout)
    # Re-init must not destroy existing records.
    again = evidence(root, "init", "--actor", "Tester")
    check(again.returncode == 0 and len(registry(root)["evidence"]) == 1,
          "re-init is idempotent and preserves records", again.stdout)


def test_negative_inputs(root):
    evidence(root, "init", "--actor", "Tester")
    unknown = evidence(
        root, "create", "--requirement-id", "BEH_SWE1_REQ_099@R1",
        "--title", "X", "--objective", "X", "--expected-result", "X", "--actor", "Tester",
    )
    check(unknown.returncode == 2 and "does not exist" in unknown.stdout,
          "create against an unknown requirement is rejected", unknown.stdout)
    mismatch = evidence(
        root, "create", "--requirement-id", "BEH_SWE1_REQ_001@R1",
        "--title", "X", "--objective", "X", "--expected-result", "X",
        "--method", "INSPECTION", "--actor", "Tester",
    )
    check(mismatch.returncode == 2 and "does not match requirement strategy" in mismatch.stdout,
          "strategy override conflicting with the requirement is rejected", mismatch.stdout)
    check(registry(root)["evidence"] == [],
          "rejected creates leave the registry unchanged")
    traversal = evidence(
        root, "create", "--requirement-id", "BEH_SWE1_REQ_001@R1",
        "--title", "X", "--objective", "X", "--expected-result", "X",
        "--artifact", "../outside.log", "--actor", "Tester",
    )
    check(traversal.returncode == 2 and "traversal" in traversal.stdout,
          "artifact path traversal is rejected", traversal.stdout)
    created = evidence(
        root, "create", "--requirement-id", "BEH_SWE1_REQ_001@R1",
        "--title", "Behavior", "--objective", "Behavior", "--expected-result", "Behavior",
        "--actor", "Tester",
    )
    evidence_id = created.stdout.strip()
    superseded = evidence(root, "supersede", evidence_id, "--by", "EV-002", "--actor", "Tester")
    check(superseded.returncode == 2 and "Only PASS evidence" in superseded.stdout,
          "superseding a non-PASS record is rejected", superseded.stdout)
    restarted = evidence(root, "start", evidence_id, "--actor", "Tester")
    check(restarted.returncode == 0, "start from PLANNED succeeds", restarted.stdout)
    restarts = evidence(root, "start", evidence_id, "--actor", "Tester")
    check(restarts.returncode == 2 and "start requires PLANNED" in restarts.stdout,
          "start from IN_PROGRESS is rejected", restarts.stdout)
    blocked = evidence(
        root, "record-result", evidence_id, "--result", "BLOCKED",
        "--actor", "Tester", "--summary", "Environment unavailable",
    )
    check(blocked.returncode == 0, "BLOCKED result is recorded", blocked.stdout)
    coverage = evidence(root, "coverage", "--strict")
    check(coverage.returncode == 1 and "BEH_SWE1_REQ_001@R1" in coverage.stdout,
          "BLOCKED evidence does not satisfy strict coverage", coverage.stdout)
    late_start = evidence(root, "start", evidence_id, "--actor", "Tester")
    check(late_start.returncode == 2, "start after a result is rejected", late_start.stdout)


def test_registry_tampering(root):
    evidence(root, "init", "--actor", "Tester")
    result = create_pass_evidence(root)
    if result.returncode:
        fail("tamper fixture setup", result.stdout)
        return
    artifact = root / "05-verification/software/report.log"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text("original\n", encoding="utf-8")
    commit_all(root, "add report artifact")
    added = evidence(
        root, "create", "--requirement-id", "BEH_SWE1_REQ_001@R1",
        "--title", "Artifact check", "--objective", "Artifact integrity",
        "--expected-result", "Checksum verified", "--artifact",
        "05-verification/software/report.log", "--artifact-type", "LOG",
        "--actor", "Tester",
    )
    check(added.returncode == 0, "artifact checksum is captured at create", added.stdout)
    artifact.write_text("tampered\n", encoding="utf-8")
    validated = evidence(root, "validate")
    check(validated.returncode == 1 and "SHA-256 mismatch" in validated.stdout,
          "artifact tampering is detected by validation", validated.stdout)
    artifact.write_text("original\n", encoding="utf-8")

    pristine = registry(root)
    duplicate = json.loads(json.dumps(pristine))
    duplicate["evidence"].append(dict(duplicate["evidence"][0]))
    save_registry(root, duplicate)
    validated = evidence(root, "validate")
    check(validated.returncode == 1 and "not unique" in validated.stdout,
          "duplicate Evidence_ID values are rejected", validated.stdout)

    reused = json.loads(json.dumps(pristine))
    reused["next_number"] = 1
    save_registry(root, reused)
    validated = evidence(root, "validate")
    check(validated.returncode == 1 and "reuse an Evidence_ID" in validated.stdout,
          "next_number reuse of an Evidence_ID is rejected", validated.stdout)

    broken = json.loads(json.dumps(pristine))
    broken["evidence"][0]["Execution"]["Git_Commit"] = "0" * 40
    save_registry(root, broken)
    validated = evidence(root, "validate")
    check(validated.returncode == 1 and "commit does not exist" in validated.stdout,
          "unknown execution Git commit is rejected", validated.stdout)

    disagree = json.loads(json.dumps(pristine))
    disagree["evidence"][0]["Execution"]["Result"] = "FAIL"
    save_registry(root, disagree)
    validated = evidence(root, "validate")
    check(validated.returncode == 1 and "disagree" in validated.stdout,
          "Status/Execution.Result disagreement is rejected", validated.stdout)

    history = json.loads(json.dumps(pristine))
    history["evidence"][0]["History"][0]["event"] = "MODIFIED"
    save_registry(root, history)
    validated = evidence(root, "validate")
    check(validated.returncode == 1 and "first history event must be CREATED" in validated.stdout,
          "history must start with CREATED", validated.stdout)

    missing_baseline = json.loads(json.dumps(pristine))
    missing_baseline["evidence"][0]["Configuration_Baseline"] = "BL-999"
    save_registry(root, missing_baseline)
    validated = evidence(root, "validate")
    check(validated.returncode == 1 and "baseline does not exist" in validated.stdout,
          "unknown configuration baseline is rejected", validated.stdout)
    save_registry(root, pristine)
    validated = evidence(root, "validate")
    check(validated.returncode == 0, "registry restored to a valid state", validated.stdout)


def test_revision_and_cancellation_rules(root):
    extra = REQUIREMENT.format(prefix="BEH", seq=1, rev=2, status="RELEASED").replace(
        "Upstream: ROOT", "Upstream: ROOT"
    )
    cancelled = REQUIREMENT.format(prefix="BEH", seq=2, rev=1, status="CANCELLED")
    (root / "01-requirements/software/SWE-REQUIREMENTS.md").write_text(
        "# Software Requirements\n"
        + REQUIREMENT.format(prefix="BEH", seq=1, rev=1, status="RELEASED")
        + extra + cancelled,
        encoding="utf-8",
    )
    commit_all(root, "add revision 2 and a cancelled requirement")
    evidence(root, "init", "--actor", "Tester")
    against_cancelled = evidence(
        root, "create", "--requirement-id", "BEH_SWE1_REQ_002@R1",
        "--title", "X", "--objective", "X", "--expected-result", "X", "--actor", "Tester",
    )
    check(against_cancelled.returncode == 2 and "CANCELLED" in against_cancelled.stdout,
          "evidence against a CANCELLED requirement is rejected", against_cancelled.stdout)
    result = create_pass_evidence(root, "BEH_SWE1_REQ_001@R1")
    check(result.returncode == 0, "PASS evidence recorded on revision R1", result.stdout)
    coverage = evidence(root, "coverage", "--strict")
    check(coverage.returncode == 1 and "BEH_SWE1_REQ_001@R2" in coverage.stdout,
          "evidence on R1 does not cover the active R2 revision", coverage.stdout)
    result = create_pass_evidence(root, "BEH_SWE1_REQ_001@R2")
    check(result.returncode == 0, "PASS evidence recorded on revision R2", result.stdout)
    coverage = evidence(root, "coverage", "--strict")
    check(coverage.returncode == 0, "active revision covered by its own evidence",
          coverage.stdout)
    first = evidence(root, "supersede", "EV-001", "--by", "EV-002", "--actor", "Tester",
                     "--comment", "R1 evidence replaced by R2 campaign")
    check(first.returncode == 0 and registry(root)["evidence"][0]["Status"] == "SUPERSEDED",
          "PASS evidence can be superseded by a newer PASS record", first.stdout)
    validated = evidence(root, "validate")
    check(validated.returncode == 0, "superseded registry remains valid", validated.stdout)


def test_planned_artifact_integrity(root):
    evidence(root, "init", "--actor", "Tester")
    created = evidence(
        root, "create", "--requirement-id", "BEH_SWE1_REQ_001@R1",
        "--title", "Planned report", "--objective", "Protect future proof",
        "--expected-result", "Proof preserved", "--artifact", "future.log",
        "--artifact-type", "LOG", "--actor", "Tester",
    )
    check(created.returncode == 0, "planning a future artifact is supported", created.stdout)
    before = registry(root)
    missing = evidence(root, "record-result", "EV-001", "--result", "PASS",
                       "--actor", "Tester", "--summary", "No report yet")
    check(missing.returncode == 2 and registry(root) == before,
          "PASS with a missing planned artifact is rejected without mutation", missing.stdout)
    artifact = root / "future.log"
    artifact.write_text("original proof\n", encoding="utf-8")
    recorded = evidence(root, "record-result", "EV-001", "--result", "PASS",
                        "--actor", "Tester", "--summary", "Proof collected")
    check(recorded.returncode == 0 and bool(registry(root)["evidence"][0]["Artifacts"][0].get("sha256")),
          "record-result seals artifacts that appeared after planning", recorded.stdout)
    pristine = registry(root)
    artifact.write_text("changed proof\n", encoding="utf-8")
    audited = audit(root, "--strict")
    check(audited.returncode == 1 and "SHA-256 mismatch" in audited.stdout,
          "strict audit detects tampering of a formerly planned artifact", audited.stdout)
    artifact.write_text("original proof\n", encoding="utf-8")
    unchecked = json.loads(json.dumps(pristine))
    unchecked["evidence"][0]["Artifacts"][0].pop("sha256")
    save_registry(root, unchecked)
    validated = evidence(root, "validate")
    check(validated.returncode == 1 and "requires SHA-256" in validated.stdout,
          "removing a completed artifact checksum is rejected", validated.stdout)
    save_registry(root, pristine)


def test_supersession_integrity(root):
    evidence(root, "init", "--actor", "Tester")
    create_pass_evidence(root)
    before = registry(root)
    result = evidence(root, "supersede", "EV-001", "--by", "EV-001", "--actor", "Tester")
    check(result.returncode == 2 and registry(root) == before,
          "self supersession is rejected without registry mutation", result.stdout)
    create_pass_evidence(root)
    create_pass_evidence(root)
    first = evidence(root, "supersede", "EV-001", "--by", "EV-002", "--actor", "Tester")
    second = evidence(root, "supersede", "EV-002", "--by", "EV-003", "--actor", "Tester")
    validated = evidence(root, "validate")
    check(first.returncode == second.returncode == validated.returncode == 0,
          "supersession chains ending in PASS remain valid", validated.stdout)
    pristine = registry(root)
    cyclic = json.loads(json.dumps(pristine))
    cyclic["evidence"][1]["Superseded_By"] = "EV-001"
    save_registry(root, cyclic)
    validated = evidence(root, "validate")
    check(validated.returncode == 1 and "cyclic evidence supersession" in validated.stdout,
          "registry validation rejects cyclic supersession", validated.stdout)
    broken = json.loads(json.dumps(pristine))
    broken["evidence"][2]["Status"] = "FAIL"
    broken["evidence"][2]["Execution"]["Result"] = "FAIL"
    save_registry(root, broken)
    validated = evidence(root, "validate")
    check(validated.returncode == 1 and "replacement chain must end in PASS" in validated.stdout,
          "registry validation requires supersession to terminate in PASS", validated.stdout)
    save_registry(root, pristine)


def test_artifact_symlink_boundary(root):
    evidence(root, "init", "--actor", "Tester")
    with tempfile.TemporaryDirectory(prefix="pm-evidence-external-") as external:
        target = Path(external) / "private.log"
        target.write_text("outside project\n", encoding="utf-8")
        link = root / "linked.log"
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            print("SKIP: platform does not permit creating a test symlink")
            return
        created = evidence(
            root, "create", "--requirement-id", "BEH_SWE1_REQ_001@R1",
            "--title", "Unsafe artifact", "--objective", "Boundary test",
            "--expected-result", "Rejected", "--artifact", "linked.log",
            "--actor", "Tester",
        )
        check(created.returncode == 2 and "outside the project" in created.stdout,
              "artifact symlinks cannot resolve outside the project", created.stdout)
        check(not registry(root)["evidence"], "unsafe artifact leaves registry unchanged")


def test_audit_skip_and_propagation(root):
    # Legacy project without the marker: non-strict warns, strict skips.
    legacy = audit(root)
    check(legacy.returncode == 0 and "legacy project skipped" in legacy.stdout,
          "legacy project without marker is skipped with a warning", legacy.stdout)
    legacy_strict = audit(root, "--strict")
    check(legacy_strict.returncode == 0 and "legacy project skipped" not in legacy_strict.stdout,
          "strict audit silently skips legacy projects", legacy_strict.stdout)
    # Enabled management without coverage must fail the audit.
    evidence(root, "init", "--actor", "Tester")
    commit_all(root, "enable evidence management")
    uncovered = audit(root, "--strict")
    check(uncovered.returncode == 1 and "no compatible PASS evidence" in uncovered.stdout,
          "enabled management with uncovered requirement fails the audit", uncovered.stdout)
    # And the failure must propagate through the real release gate chain.
    (root / "00-project/STATUS.md").write_text(
        "# Project Status\n\n- Current Baseline:\n\n"
        "| Gate | Status | Main Issue |\n|---|---|---|\n"
        "| G3 Release Readiness | PASS | |\n",
        encoding="utf-8",
    )
    commit_all(root, "declare G3 readiness")
    head = git(root, "rev-parse", "HEAD").stdout.strip()
    env = dict(os.environ, CI_COMMIT_SHA=head)
    gate = subprocess.run(
        [sys.executable, str(RELEASE), str(root)], cwd=root, env=env,
        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    check(gate.returncode != 0 and "verification_evidence_audit.py: FAIL" in gate.stdout,
          "evidence failure propagates to the release gate", gate.stdout[-400:])
    # Deleting the opt-in marker must not turn an enabled project into legacy.
    marker = root / "05-verification/EVIDENCE-MANAGEMENT.json"
    marker.unlink()
    commit_all(root, "remove evidence enablement marker")
    downgraded = audit(root, "--strict")
    check(downgraded.returncode == 1 and "enablement marker is missing" in downgraded.stdout,
          "removing enablement marker cannot bypass evidence coverage", downgraded.stdout)
    env["CI_COMMIT_SHA"] = git(root, "rev-parse", "HEAD").stdout.strip()
    gate = subprocess.run(
        [sys.executable, str(RELEASE), str(root)], cwd=root, env=env,
        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    check(gate.returncode != 0 and "verification_evidence_audit.py: FAIL" in gate.stdout,
          "marker downgrade failure propagates through the release gate", gate.stdout[-400:])


def main():
    suites = (
        ("positive lifecycle", test_positive_lifecycle),
        ("negative inputs", test_negative_inputs),
        ("registry tampering", test_registry_tampering),
        ("revision and cancellation rules", test_revision_and_cancellation_rules),
        ("planned artifact integrity", test_planned_artifact_integrity),
        ("supersession integrity", test_supersession_integrity),
        ("artifact symlink boundary", test_artifact_symlink_boundary),
        ("audit skip and release propagation", test_audit_skip_and_propagation),
    )
    for name, suite in suites:
        print(f"=== {name} ===")
        with tempfile.TemporaryDirectory(prefix="pm-evidence-test-") as temporary:
            root = Path(temporary)
            build_project(root)
            try:
                suite(root)
            except Exception as exc:  # noqa: BLE001 - test harness must report, not crash
                fail(f"{name} raised an unexpected exception", repr(exc))
        print()
    print(f"EVIDENCE TESTS: {PASS_COUNT} PASS, {len(FAILURES)} FAIL")
    if FAILURES:
        for failure in FAILURES:
            print(f"- {failure}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
