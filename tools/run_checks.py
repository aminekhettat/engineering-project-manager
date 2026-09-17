#!/usr/bin/env python3
"""Run every contributor test and the installable runtime package checks."""

import argparse
from pathlib import Path
import re
import subprocess
import sys

from validation_paths import layout_errors, resolve_layout


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill-root", type=Path, help="Runtime skill directory (default: skills/project-manager in the public checkout)")
    parser.add_argument("--logs", type=Path, help="Optional private log directory outside the skill")
    args = parser.parse_args(argv)
    layout = resolve_layout(args.skill_root)
    scripts, skill, tests, tools = layout.scripts, layout.skill, layout.tests, layout.tools
    if sys.platform != "linux":
        print("ERROR: Full runtime validation requires Linux/POSIX file locks.", file=sys.stderr)
        return 2
    errors = layout_errors(layout)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 2
    if args.logs:
        logs = args.logs.resolve()
        if logs == skill or logs.is_relative_to(skill):
            parser.error("Keep validation logs outside the distributable skill")
        logs.mkdir(parents=True, exist_ok=True)
    test_files = sorted(set(tests.glob("*_tests.py")) | set(tests.glob("*_test.py")))
    # Syntax-check without adding bytecode caches to a standalone release.
    compile_code = "import pathlib,sys; [compile(p.read_bytes(),str(p),'exec') for d in sys.argv[1:] for p in pathlib.Path(d).glob('*.py')]"
    checks = [("compile", [sys.executable, "-B", "-c", compile_code, str(scripts), str(tests), str(tools)])]
    checks += [(path.stem, [sys.executable, str(path)]) for path in test_files]
    checks += [
        ("package", [sys.executable, str(tools / "skill_package_check.py"), str(skill)]),
        ("self_check", [sys.executable, str(tools / "project_manager_self_check.py"), "--skill-root", str(skill)]),
    ]
    failures = []
    env = layout.environment()
    for name, command in checks:
        print(f"RUN: {name}", flush=True)
        try:
            result = subprocess.run(command, cwd=layout.source, capture_output=True, text=True,
                                    env=env, timeout=240)
            output = result.stdout + result.stderr
            passed = result.returncode == 0
            if re.search(r"\bskipped=[1-9][0-9]*\b", output):
                output += "\nValidation requires every test to run; skipped tests need a supported Linux environment.\n"
                passed = False
        except subprocess.TimeoutExpired:
            output, passed = "Check exceeded its 240 second limit.\n", False
        if args.logs:
            (logs / f"{name}.log").write_text(output, encoding="utf-8")
        if not passed:
            failures.append(name)
            print(output, flush=True)
        print(f"{'PASS' if passed else 'FAIL'}: {name}", flush=True)
    print(f"CHECKS: {len(checks) - len(failures)} PASS, {len(failures)} FAIL", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
