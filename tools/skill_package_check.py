#!/usr/bin/env python3
"""Deterministic packaging checks for the Project Manager AgentSkill."""

import argparse
import configparser
import re
import subprocess
import sys
from pathlib import Path

from validation_paths import resolve_layout

REQUIRED_FRONTMATTER = {"name", "description"}
FORBIDDEN_PATTERNS = ("*.bak*", "*.legacy-*", "*.broken-*", "*.pyc")
RESOURCE_RE = re.compile(r"`((?:references|docs|scripts|templates)/[^`]+)`")


def parse_frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        raise ValueError("SKILL.md must start with YAML frontmatter")
    try:
        raw, _body = text[4:].split("\n---\n", 1)
    except ValueError as exc:
        raise ValueError("SKILL.md frontmatter is not closed") from exc
    result: dict[str, str] = {}
    for line in raw.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, sep, value = line.partition(":")
        if not sep:
            raise ValueError(f"invalid frontmatter line: {line}")
        result[key.strip()] = value.strip().strip('"\'')
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("skill", nargs="?", type=Path, help="Installable runtime directory")
    parser.add_argument("--skill-root", type=Path, help="Alternative named runtime directory argument")
    args = parser.parse_args()
    if args.skill is not None and args.skill_root is not None:
        parser.error("Use either the positional skill path or --skill-root")
    root = resolve_layout(args.skill_root if args.skill_root is not None else args.skill).skill
    errors: list[str] = []

    skill_file = root / "SKILL.md"
    if not skill_file.is_file():
        errors.append("SKILL.md missing")
        text = ""
        metadata = {}
    else:
        text = skill_file.read_text(encoding="utf-8")
        try:
            metadata = parse_frontmatter(text)
        except ValueError as exc:
            metadata = {}
            errors.append(str(exc))

    missing_keys = REQUIRED_FRONTMATTER - metadata.keys()
    if missing_keys:
        errors.append(f"frontmatter missing: {', '.join(sorted(missing_keys))}")
    if metadata.get("name") != "project-manager":
        errors.append("frontmatter name must be project-manager")
    description = metadata.get("description", "")
    if len(description) < 80 or "translation" in description.lower():
        errors.append("description must express the operational trigger, not migration work")
    if len(text.splitlines()) > 260:
        errors.append("SKILL.md exceeds the 260-line routing/procedure budget")

    references = {match.rstrip(".,:;)") for match in RESOURCE_RE.findall(text)}
    for relative in sorted(references):
        if not (root / relative).is_file():
            errors.append(f"referenced resource missing: {relative}")

    required_resources = {
        "README.md",
        "SECURITY.md",
        "LICENSE",
        "VERSION",
        "docs/MANAGEMENT-EXTENSIONS.md",
        "docs/RISK-PROBLEM-MANAGEMENT.md",
        "docs/MILESTONE-MANAGEMENT.md",
        "docs/INTAKE-COMPLIANCE.md",
        "scripts/management_common.py",
        "scripts/management_init.py",
        "scripts/management_audit.py",
        "scripts/risk_manager.py",
        "scripts/problem_manager.py",
        "scripts/milestone_manager.py",
        "scripts/intake_manager.py",
        "scripts/compliance_manager.py",
        "docs/SPICE-SCOPE.md",
        "references/project-initialization.md",
        "references/agent-delegation.md",
        "scripts/project_setup.py",
        "scripts/delegation_plan.py",
        "scripts/project_report.py",
        "references/project-manager-handbook.md",
        "references/execution-engine.md",
        "docs/REQUIREMENT-DATA-MODEL.md",
        "docs/CHANGE-BASELINE-MANAGEMENT.md",
        "docs/INDUSTRIALIZATION-ROADMAP.md",
    }
    # Source versioning keeps both files. ClawHub's MIT-0 distribution omits
    # dotfiles; its manifest is verified separately by publication_check.py.
    if metadata.get("license") != "MIT-0":
        required_resources.add(".bumpversion.cfg")
    for relative in sorted(required_resources):
        if not (root / relative).is_file():
            errors.append(f"required resource missing: {relative}")

    contributor_tools = {"run_checks.py", "project_manager_self_check.py", "skill_package_check.py",
                         "publication_check.py", "export_public_skill.py", "validation_paths.py"}
    for path in (root / "scripts").glob("*.py"):
        if path.name.endswith(("_tests.py", "_test.py")) or path.name in contributor_tools:
            errors.append(f"contributor-only resource bundled in runtime: scripts/{path.name}")
    for relative in ("tests", "tools"):
        if (root / relative).exists():
            errors.append(f"contributor-only directory bundled in runtime: {relative}")

    try:
        version = (root / "VERSION").read_text(encoding="utf-8").strip()
        if not re.fullmatch(r"\d+\.\d+\.\d+", version):
            errors.append("VERSION must contain a semantic version")
        config_path = root / ".bumpversion.cfg"
        if config_path.exists():
            config = configparser.ConfigParser()
            with config_path.open(encoding="utf-8") as stream:
                config.read_file(stream)
            if config.get("bumpversion", "current_version") != version:
                errors.append("VERSION and .bumpversion.cfg disagree")
    except (OSError, configparser.Error) as exc:
        errors.append(f"version metadata invalid: {exc}")

    requirement_template = root / "templates/REQUIREMENTS-SPECIFICATION.md"
    if requirement_template.is_file():
        template_text = requirement_template.read_text(encoding="utf-8")
        for marker in ("[<PROJECT>_<PROCESS>_REQ_<SEQ>@R<REV>]", "Text:", "[END_REQ]"):
            if marker not in template_text:
                errors.append(f"requirement template missing V1.1 marker: {marker}")
        for obsolete in ("- Source:", "- Parent:", "Verification IDs:"):
            if obsolete in template_text:
                errors.append(f"requirement template retains obsolete field: {obsolete}")

    bootstrap = root / "scripts/bootstrap_project.py"
    if bootstrap.is_file():
        bootstrap_text = bootstrap.read_text(encoding="utf-8")
        for lock_path in (
            "08-configuration/.change-requests.lock",
            "08-configuration/.baselines.lock",
            "00-project/management/.tasks.lock",
        ):
            if lock_path not in bootstrap_text:
                errors.append(f"generated .gitignore missing runtime lock: {lock_path}")

    repository = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    if repository.returncode == 0:
        top = Path(repository.stdout.strip())
        tracked_result = subprocess.run(
            ["git", "-C", str(top), "ls-files", str(root.relative_to(top))],
            text=True,
            stdout=subprocess.PIPE,
            check=True,
        )
        tracked = [top / value for value in tracked_result.stdout.splitlines()]
    else:
        tracked = [path for path in root.rglob("*") if path.is_file()]
    for path in tracked:
        relative = path.relative_to(root)
        name = relative.name
        if ("__pycache__" in relative.parts or name.endswith(".pyc") or
                ".bak" in name or ".legacy-" in name or ".broken-" in name):
            errors.append(f"historical/runtime artifact packaged: {relative}")

    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        print(f"PACKAGE CHECK: FAIL ({len(errors)} error(s))")
        return 1
    print(f"PACKAGE CHECK: PASS ({len(references)} referenced resources verified)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
