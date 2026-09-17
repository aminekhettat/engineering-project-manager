#!/usr/bin/env python3

from pathlib import Path
import argparse
import ast
import importlib.util
import json
import subprocess
import sys

from validation_paths import REQUIRED_TESTS, layout_errors, resolve_layout


LAYOUT = resolve_layout()
PM, SCRIPTS, TESTS, TOOLS = LAYOUT.skill, LAYOUT.scripts, LAYOUT.tests, LAYOUT.tools
TEMPLATES = PM / "templates"

PASS_COUNT = 0
WARNINGS = []
FAILURES = []


def passed(message):
    global PASS_COUNT
    PASS_COUNT += 1
    print(f"PASS: {message}")


def warn(message):
    WARNINGS.append(message)
    print(f"WARN: {message}")


def fail(message):
    FAILURES.append(message)
    print(f"FAIL: {message}")


def run(command, cwd=None):
    return subprocess.run(
        command,
        cwd=cwd,
        env=LAYOUT.environment(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def check_file(path, label=None):
    label = label or path.name

    if path.is_file() and path.stat().st_size > 0:
        passed(label)
        return True

    fail(f"missing or empty: {label}")
    return False


def load_python_module(path, name):
    sys.path.insert(0, str(path.parent))

    spec = importlib.util.spec_from_file_location(
        name,
        path,
    )

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return module


def check_duplicate_functions(path):
    tree = ast.parse(
        path.read_text(encoding="utf-8")
    )

    functions = {}

    for node in tree.body:
        if isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef),
        ):
            functions.setdefault(
                node.name,
                [],
            ).append(node.lineno)

    duplicates = {
        name: lines
        for name, lines in functions.items()
        if len(lines) > 1
    }

    if duplicates:
        fail(
            f"{path.name}: duplicate top-level "
            f"functions {duplicates}"
        )
    else:
        passed(
            f"{path.name}: no duplicate top-level functions"
        )


def main():
    global LAYOUT, PM, SCRIPTS, TESTS, TOOLS, TEMPLATES
    parser = argparse.ArgumentParser(description="Validate the runtime with contributor fixtures and optional local smoke projects")
    parser.add_argument("--skill-root", type=Path, help="Runtime directory (default: skills/project-manager in the public checkout)")
    parser.add_argument("--projects-root", type=Path, help="Opt in to checking named smoke projects under this directory")
    args = parser.parse_args()
    LAYOUT = resolve_layout(args.skill_root)
    PM, SCRIPTS, TESTS, TOOLS = LAYOUT.skill, LAYOUT.scripts, LAYOUT.tests, LAYOUT.tools
    TEMPLATES = PM / "templates"
    errors = layout_errors(LAYOUT)
    if errors:
        for error in errors:
            fail(error)
        return 2
    print("=== PROJECT MANAGER SELF CHECK ===")
    print()

    required_scripts = [
        "bootstrap_project.py",
        "pm_common.py",
        "project_audit.py",
        "requirements_lint.py",
        "traceability_check.py",
        "release_check.py",
        "domain_audit.py",
        "project_state.py",
        "change_manager.py",
        "baseline_manager.py",
        "configuration_audit.py",
        "verification_evidence.py",
        "verification_evidence_audit.py",
        "migration_assess.py",
    ]

    for name in required_scripts:
        check_file(
            SCRIPTS / name,
            f"script: {name}",
        )

    for name in sorted(REQUIRED_TESTS):
        check_file(TESTS / name, f"test suite: {name}")
    for name in ("project_manager_self_check.py", "skill_package_check.py"):
        check_file(TOOLS / name, f"contributor tool: {name}")

    check_file(
        PM / "SKILL.md",
        "SKILL.md",
    )
    check_file(
        PM / "references/project-manager-handbook.md",
        "Project Manager handbook",
    )

    package_check = run([
        sys.executable,
        str(TOOLS / "skill_package_check.py"),
        str(PM),
    ])
    if package_check.returncode == 0:
        passed("AgentSkill package validation")
    else:
        fail("AgentSkill package validation failed: " + package_check.stdout.strip())

    release_fixture = run([
        sys.executable,
        str(TESTS / "release_fixture_test.py"),
    ])
    if release_fixture.returncode == 0:
        passed("complete release fixture")
    else:
        fail("complete release fixture failed: " + release_fixture.stdout.strip())

    requirement_compatibility = run([
        sys.executable,
        str(TESTS / "requirements_compatibility_tests.py"),
    ])
    if requirement_compatibility.returncode == 0:
        passed("requirement language compatibility")
    else:
        fail(
            "requirement language compatibility failed: "
            + requirement_compatibility.stdout.strip()
        )

    domain_behavior = run([
        sys.executable,
        str(TESTS / "domain_audit_tests.py"),
    ])
    if domain_behavior.returncode == 0:
        passed("revision-aware domain audit behavior")
    else:
        fail(
            "revision-aware domain audit behavior failed: "
            + domain_behavior.stdout.strip()
        )

    task_behavior = run([
        sys.executable,
        str(TESTS / "project_state_tests.py"),
    ])
    if task_behavior.returncode == 0:
        passed("task engine behavior and concurrency")
    else:
        fail(
            "task engine behavior and concurrency failed: "
            + task_behavior.stdout.strip()
        )

    print()
    print("=== CHANGE AND BASELINE MANAGEMENT V1.1 ===")

    for name in (
        "CHANGE-REQUEST.md",
        "BASELINE-RECORD.md",
        "CONFIGURATION-PLAN.md",
    ):
        check_file(TEMPLATES / name, f"template: {name}")
    check_file(
        PM / "docs/CHANGE-BASELINE-MANAGEMENT.md",
        "Change and Baseline Management documentation",
    )

    try:
        change_manager = load_python_module(
            SCRIPTS / "change_manager.py",
            "pm_change_manager",
        )
        baseline_manager = load_python_module(
            SCRIPTS / "baseline_manager.py",
            "pm_baseline_manager",
        )
        passed("Change and Baseline Management modules import")
        if "ANALYZED" in change_manager.STATUSES:
            passed("CR workflow contains ANALYZED")
        else:
            fail("CR workflow is missing ANALYZED")
        if "APPROVED" not in change_manager.STATUSES:
            passed("APPROVED is not a CR workflow status")
        else:
            fail("APPROVED must not be a CR workflow status")
        if {"Current_Assignee", "Current_Role"}.issubset(
            set(change_manager.render_change.__code__.co_consts)
        ):
            passed("CR rendering exposes dynamic assignment fields")
        else:
            # Field labels are formatted strings, so source inspection is the
            # stable structural check across supported Python versions.
            source = (SCRIPTS / "change_manager.py").read_text(encoding="utf-8")
            if "Current_Assignee" in source and "Current_Role" in source:
                passed("CR model exposes dynamic assignment fields")
            else:
                fail("CR model is missing dynamic assignment fields")
        if "Snapshot_Integrity_SHA256" in (
            SCRIPTS / "baseline_manager.py"
        ).read_text(encoding="utf-8") and callable(
            baseline_manager.immutable_payload
        ):
            passed("baseline immutable snapshot hash is implemented")
        else:
            fail("baseline immutable snapshot hash is missing")
    except Exception as exc:
        fail(f"Change and Baseline Management import failed: {exc}")

    bootstrap_source = (SCRIPTS / "bootstrap_project.py").read_text(encoding="utf-8")
    if all(marker in bootstrap_source for marker in (
        "CONFIGURATION-MANAGEMENT.json",
        "CHANGE-REQUESTS.json",
        "BASELINE-REGISTRY.json",
    )):
        passed("bootstrap contains configuration-management markers")
    else:
        fail("bootstrap configuration-management markers are incomplete")
    release_source = (SCRIPTS / "release_check.py").read_text(encoding="utf-8")
    if '"configuration_audit.py"' in release_source:
        passed("release gate invokes configuration audit")
    else:
        fail("release gate does not invoke configuration audit")
    change_source = (SCRIPTS / "change_manager.py").read_text(encoding="utf-8")
    if "Change_ID" in change_source and "revision" in change_source:
        passed("requirement revision creation is linked to Change Requests")
    else:
        fail("requirement revision and Change Request integration is missing")

    print()
    print("=== VERIFICATION EVIDENCE MANAGEMENT ===")

    check_file(
        PM / "docs/VERIFICATION-EVIDENCE.md",
        "Verification Evidence documentation",
    )

    try:
        evidence_engine = load_python_module(
            SCRIPTS / "verification_evidence.py",
            "pm_verification_evidence",
        )
        load_python_module(
            SCRIPTS / "verification_evidence_audit.py",
            "pm_verification_evidence_audit",
        )
        passed("Verification Evidence modules import")
        if {"PLANNED", "IN_PROGRESS", "PASS", "FAIL", "BLOCKED", "SKIPPED", "SUPERSEDED"} == evidence_engine.STATUSES:
            passed("evidence lifecycle statuses exact")
        else:
            fail(f"evidence lifecycle statuses mismatch: {sorted(evidence_engine.STATUSES)}")
        if evidence_engine.RESULTS == {"PASS", "FAIL", "BLOCKED", "SKIPPED"}:
            passed("evidence execution results exact")
        else:
            fail(f"evidence results mismatch: {sorted(evidence_engine.RESULTS)}")
        if callable(evidence_engine.validate_registry) and callable(evidence_engine.coverage):
            passed("evidence registry validation and coverage are implemented")
        else:
            fail("evidence registry validation or coverage is missing")
    except Exception as exc:
        fail(f"Verification Evidence import failed: {exc}")

    release_source = (SCRIPTS / "release_check.py").read_text(encoding="utf-8")
    if '"verification_evidence_audit.py"' in release_source:
        passed("release gate invokes verification evidence audit")
    else:
        fail("release gate does not invoke verification evidence audit")

    configuration_source = (SCRIPTS / "configuration_audit.py").read_text(encoding="utf-8")
    if "05-verification/EVIDENCE.json" in configuration_source:
        passed("release-candidate delta tolerates committed evidence records")
    else:
        fail("release-candidate delta does not recognize evidence records")

    bootstrap_source = (SCRIPTS / "bootstrap_project.py").read_text(encoding="utf-8")
    if all(marker in bootstrap_source for marker in (
        "EVIDENCE-MANAGEMENT.json",
        "EVIDENCE.json",
        "verification_evidence.py",
        "verification_evidence_audit.py",
    )):
        passed("bootstrap initializes verification evidence management")
    else:
        fail("bootstrap verification evidence initialization is incomplete")

    evidence_behavior = run([
        sys.executable,
        str(TESTS / "verification_evidence_tests.py"),
    ])
    if evidence_behavior.returncode == 0:
        passed("verification evidence behavior and tamper resistance")
    else:
        fail(
            "verification evidence tests failed: "
            + evidence_behavior.stdout.strip()
        )

    print()
    print("=== MIGRATION COMPATIBILITY ===")

    check_file(
        SCRIPTS / "migration_assess.py",
        "Migration assessment script",
    )
    check_file(
        TESTS / "migration_compat_tests.py",
        "Migration compatibility tests",
    )

    try:
        migration_module = load_python_module(
            SCRIPTS / "migration_assess.py",
            "pm_migration_assess",
        )
        passed("Migration assessment module imports")
        if callable(migration_module.assess_project):
            passed("assess_project is implemented")
        else:
            fail("assess_project is missing")
        source = (SCRIPTS / "migration_assess.py").read_text(encoding="utf-8")
        if "write_text_atomic" not in source and "write_json_atomic" not in source:
            passed("assessment script does not import write helpers")
        else:
            fail("assessment script must not import write helpers")
    except Exception as exc:
        fail(f"Migration assessment import failed: {exc}")

    migration_tests = run([
        sys.executable,
        str(TESTS / "migration_compat_tests.py"),
    ])
    if migration_tests.returncode == 0:
        passed("migration compatibility behavior and non-destructive assessment")
    else:
        fail(
            "migration compatibility tests failed: "
            + migration_tests.stdout.strip()
        )

    print()
    print("=== PYTHON COMPILATION ===")

    for path in sorted(SCRIPTS.glob("*.py")):
        try:
            compile(path.read_bytes(), str(path), "exec")
            passed(f"compile: {path.name}")
        except (OSError, SyntaxError, ValueError) as exc:
            fail(f"compile failed: {path.name}: {exc}")

    master = SCRIPTS / "bootstrap_project.py"
    print()
    print("=== PYTHON STRUCTURAL CONSISTENCY ===")

    for path in sorted(SCRIPTS.glob("*.py")):
        check_duplicate_functions(path)

    print()
    print("=== DOMAIN MODEL ===")

    try:
        domain_audit = load_python_module(
            SCRIPTS / "domain_audit.py",
            "pm_domain_audit",
        )
        passed("domain_audit import")
    except Exception as exc:
        fail(f"domain_audit import failed: {exc}")
        domain_audit = None

    expected_domains = {
        "SYS",
        "SWE",
        "HWE",
        "MLE",
        "CYBER",
        "MECH",
    }

    expected_dirs = {
        "SYS": "system",
        "SWE": "software",
        "HWE": "hardware",
        "MLE": "machine-learning",
        "CYBER": "cybersecurity",
        "MECH": "mechanical",
    }

    expected_prefixes = {
        "SYS": "SYS-REQ-",
        "SWE": "SWE-REQ-",
        "HWE": "HWE-REQ-",
        "MLE": "MLE-REQ-",
        "CYBER": "CYB-REQ-",
        "MECH": "MEC-REQ-",
    }

    if domain_audit:
        actual_domains = set(
            domain_audit.DOMAIN_CONFIG
        )

        if actual_domains == expected_domains:
            passed("DOMAIN_CONFIG exact")
        else:
            fail(
                "DOMAIN_CONFIG mismatch: "
                f"{sorted(actual_domains)}"
            )

        for domain in sorted(expected_domains):
            actual_dir = (
                domain_audit
                .DOMAIN_DIRECTORY
                .get(domain)
            )

            if actual_dir == expected_dirs[domain]:
                passed(
                    f"{domain}: directory "
                    f"{actual_dir}"
                )
            else:
                fail(
                    f"{domain}: bad directory "
                    f"{actual_dir!r}"
                )

            actual_prefix = (
                domain_audit
                .DOMAIN_CONFIG
                .get(domain, {})
                .get("prefix")
            )

            if actual_prefix == expected_prefixes[domain]:
                passed(
                    f"{domain}: prefix "
                    f"{actual_prefix}"
                )
            else:
                fail(
                    f"{domain}: bad prefix "
                    f"{actual_prefix!r}"
                )

            if domain in domain_audit.WORK_PRODUCT_NAMES:
                passed(
                    f"{domain}: work-product registry"
                )
            else:
                fail(
                    f"{domain}: missing work-product registry"
                )

    print()
    print("=== TEMPLATES ===")

    templates = [
        "ARCHITECTURE.md",
        "INTERFACE-SPECIFICATION.md",
        "DETAILED-DESIGN.md",
        "TEST-SPECIFICATION.md",
        "VERIFICATION-REPORT.md",
        "DATA-CARD.md",
        "MODEL-CARD.md",
        "CYBER-ARCHITECTURE.md",
        "CYBER-THREAT-MODEL.md",
        "CYBER-SECURITY-PLAN.md",
        "CYBER-TEST-SPECIFICATION.md",
        "CYBER-VERIFICATION-REPORT.md",
        "MECH-ARCHITECTURE.md",
        "MECH-INTERFACE-SPECIFICATION.md",
        "MECH-DETAILED-DESIGN.md",
        "MECH-ASSEMBLY-SPECIFICATION.md",
        "MECH-TEST-SPECIFICATION.md",
        "MECH-VERIFICATION-REPORT.md",
    ]

    for name in templates:
        check_file(
            TEMPLATES / name,
            f"template: {name}",
        )

    print()
    print("=== BOOTSTRAP FEATURES ===")

    bootstrap_text = (
        master.read_text(encoding="utf-8")
        if master.is_file()
        else ""
    )

    markers = [
        "DOMAIN WORK PRODUCTS AUTO-GENERATION",
        "CYBER WORK PRODUCTS AUTO-GENERATION",
        "MECH WORK PRODUCTS AUTO-GENERATION",
        "STAGE DOMAIN DESIGN WORK PRODUCTS",
    ]

    for marker in markers:
        if marker in bootstrap_text:
            passed(f"bootstrap marker: {marker}")
        else:
            warn(f"missing bootstrap marker: {marker}")

    audit_scripts = [
        "project_audit.py",
        "requirements_lint.py",
        "traceability_check.py",
        "release_check.py",
        "domain_audit.py",
    ]

    for name in audit_scripts:
        if name in bootstrap_text:
            passed(f"bootstrap references: {name}")
        else:
            fail(f"bootstrap missing reference: {name}")

    print()
    print("=== ARCHETYPES ===")

    expected_archetypes = {
        "desktop": {"SWE"},
        "mobile": {"SWE"},
        "website": {"SWE"},
        "saas": {"SWE", "CYBER"},
        "iot": {"SYS", "SWE", "HWE", "CYBER"},
        "home-automation": {
            "SYS",
            "SWE",
            "HWE",
            "CYBER",
        },
        "embedded": {"SYS", "SWE", "HWE"},
        "robot": {"SYS", "SWE", "HWE", "MECH"},
        "drone": {
            "SYS",
            "SWE",
            "HWE",
            "MECH",
            "CYBER",
        },
        "edge-ai": {
            "SYS",
            "SWE",
            "HWE",
            "MLE",
        },
        "ml": {"SWE", "MLE"},
    }

    archetypes = None

    if master.is_file():
        tree = ast.parse(bootstrap_text)

        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue

            try:
                value = ast.literal_eval(node)
            except Exception:
                continue

            if not isinstance(value, dict):
                continue

            if (
                "desktop" in value
                and "drone" in value
                and "edge-ai" in value
            ):
                archetypes = value
                break

    if archetypes is None:
        fail("archetype map not found")
    else:
        for name, expected in expected_archetypes.items():
            actual = set(
                archetypes.get(name, [])
            )

            if actual == expected:
                passed(
                    f"archetype {name}"
                )
            else:
                fail(
                    f"archetype {name}: "
                    f"{sorted(actual)}"
                )

    print()
    print("=== RELEASE GATE ===")

    release = SCRIPTS / "release_check.py"

    if release.is_file():
        text = release.read_text(
            encoding="utf-8"
        )

        if "domain_audit" in text:
            passed("release gate includes domain audit")
        else:
            fail("release gate missing domain audit")

        if "--strict" in text:
            passed("release gate uses strict mode")
        else:
            warn(
                "release gate strict marker not found"
            )

    print()
    print("=== VALIDATION PROJECTS ===")

    validation_projects = [
        (
            "edge-ai-mle-validation",
            "MLE",
        ),
        (
            "saas-cyber-validation",
            "CYBER",
        ),
        (
            "robot-mech-validation",
            "MECH",
        ),
    ]

    for project_name, domain in validation_projects:
        if args.projects_root is None:
            continue
        root = args.projects_root / project_name

        if not root.is_dir():
            # These are optional external smoke projects and are not shipped
            # with the AgentSkill. The bundled complete release fixture above
            # provides the portable gate proof used by CI.
            passed(
                f"optional validation project absent: "
                f"{project_name}"
            )
            continue

        audit = (
            root
            / "tools/project-audit/domain_audit.py"
        )

        if not audit.is_file():
            fail(
                f"{project_name}: "
                "embedded domain audit missing"
            )
            continue

        result = run([
            sys.executable,
            str(audit),
            str(root),
            "--strict",
            "--domain",
            domain,
        ])

        if result.returncode == 0:
            passed(
                f"{project_name}: "
                f"strict {domain}"
            )
        else:
            fail(
                f"{project_name}: "
                f"strict {domain} failed"
            )

        git_status = run(
            [
                "git",
                "status",
                "--porcelain",
            ],
            cwd=root,
        )

        if git_status.returncode != 0:
            warn(
                f"{project_name}: "
                "git status unavailable"
            )
        elif git_status.stdout.strip():
            warn(
                f"{project_name}: "
                "working tree dirty"
            )
        else:
            passed(
                f"{project_name}: "
                "working tree clean"
            )

        status = (
            root
            / "00-project/BOOTSTRAP-STATUS.json"
        )

        if status.is_file():
            try:
                data = json.loads(
                    status.read_text(
                        encoding="utf-8"
                    )
                )

                if (
                    data.get("state") == "COMPLETE"
                    and data.get("complete") is True
                ):
                    passed(
                        f"{project_name}: "
                        "bootstrap COMPLETE"
                    )
                else:
                    warn(
                        f"{project_name}: "
                        "bootstrap not COMPLETE"
                    )
            except Exception as exc:
                fail(
                    f"{project_name}: "
                    f"invalid status JSON: {exc}"
                )
        else:
            warn(
                f"{project_name}: "
                "BOOTSTRAP-STATUS missing"
            )

    print()
    print("=== SUMMARY ===")
    print(f"PASS = {PASS_COUNT}")
    print(f"WARN = {len(WARNINGS)}")
    print(f"FAIL = {len(FAILURES)}")

    if WARNINGS:
        print()
        print("=== WARNINGS ===")
        for message in WARNINGS:
            print("-", message)

    if FAILURES:
        print()
        print("=== FAILURES ===")
        for message in FAILURES:
            print("-", message)

    print()

    if FAILURES:
        print("SELF CHECK STATUS: FAIL")
        return 2

    if WARNINGS:
        print("SELF CHECK STATUS: PASS WITH REVIEW")
        return 1

    print("SELF CHECK STATUS: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
