"""Resolve the contributor checkout separately from the installable skill."""

from dataclasses import dataclass
import os
from pathlib import Path


REQUIRED_TESTS = frozenset({
    "audit_integrity_tests.py", "change_baseline_tests.py", "domain_audit_tests.py",
    "intake_compliance_tests.py", "management_common_tests.py",
    "management_integration_tests.py", "management_risk_problem_tests.py",
    "management_security_tests.py", "migration_compat_tests.py", "milestone_tests.py",
    "project_operations_tests.py", "project_setup_tests.py", "project_state_tests.py",
    "publication_tests.py", "release_fixture_test.py", "requirements_compatibility_tests.py",
    "requirements_integrity_tests.py", "verification_evidence_tests.py",
})


@dataclass(frozen=True)
class ValidationLayout:
    source: Path
    skill: Path
    scripts: Path
    tests: Path
    tools: Path

    def environment(self):
        paths = [str(self.scripts), str(self.tests), str(self.tools)]
        if os.environ.get("PYTHONPATH"):
            paths.append(os.environ["PYTHONPATH"])
        return dict(os.environ, PM_SKILL_ROOT=str(self.skill),
                    PYTHONPATH=os.pathsep.join(paths), PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")


def resolve_layout(skill_root=None):
    source = Path(__file__).resolve().parent.parent
    configured = skill_root if skill_root is not None else os.environ.get("PM_SKILL_ROOT")
    skill = Path(configured).expanduser().resolve() if configured else source / "skills/project-manager"
    return ValidationLayout(source, skill, skill / "scripts", source / "tests", source / "tools")


def layout_errors(layout):
    errors = []
    for path in (layout.skill / "SKILL.md", layout.scripts / "bootstrap_project.py"):
        if not path.is_file():
            errors.append(f"required runtime resource missing: {path}; specify --skill-root for a private checkout")
    for name in sorted(REQUIRED_TESTS):
        if not (layout.tests / name).is_file():
            errors.append(f"required test suite missing: tests/{name}")
    return errors
